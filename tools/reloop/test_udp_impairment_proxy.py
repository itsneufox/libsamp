from __future__ import annotations

import errno
import socket
import threading
import time
import unittest

try:
    from .udp_impairment_proxy import JsonLogger, UdpImpairmentProxy
except ImportError:
    from udp_impairment_proxy import JsonLogger, UdpImpairmentProxy


def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class EchoServer:
    def __init__(self, port: int) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("127.0.0.1", port))
        self.socket.settimeout(0.05)
        self.received: list[bytes] = []
        self.stopping = False
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self) -> None:
        while not self.stopping:
            try:
                payload, address = self.socket.recvfrom(65535)
            except socket.timeout:
                continue
            self.received.append(payload)
            self.socket.sendto(payload, address)

    def close(self) -> None:
        self.stopping = True
        self.thread.join(timeout=1.0)
        self.socket.close()


class UdpImpairmentProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        probes: list[socket.socket] = []
        try:
            for address in ("127.0.0.1", "127.0.0.2"):
                probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                probes.append(probe)
                probe.bind((address, 0))
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EPERM):
                raise unittest.SkipTest(
                    "AF_INET sockets are blocked by the execution sandbox"
                ) from exc
            raise
        finally:
            for probe in probes:
                probe.close()

    def run_proxy(self, proxy: UdpImpairmentProxy) -> threading.Thread:
        thread = threading.Thread(target=proxy.run, daemon=True)
        thread.start()
        return thread

    def test_forwards_both_directions_on_second_loopback_address(self) -> None:
        port = free_port()
        server = EchoServer(port)
        server.thread.start()
        proxy = UdpImpairmentProxy(
            ("127.0.0.2", port),
            ("127.0.0.1", port),
            logger=JsonLogger(None, False),
        )
        proxy_thread = self.run_proxy(proxy)
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(1.0)
        try:
            client.sendto(b"samp-raknet", ("127.0.0.2", port))
            payload, address = client.recvfrom(1024)
            self.assertEqual(payload, b"samp-raknet")
            self.assertEqual(address, ("127.0.0.2", port))
            self.assertEqual(proxy.stats.client_forwarded, 1)
            self.assertEqual(proxy.stats.server_forwarded, 1)
        finally:
            client.close()
            proxy.stop()
            proxy_thread.join(timeout=1.0)
            proxy.close()
            server.close()

    def test_deterministic_total_client_loss(self) -> None:
        port = free_port()
        server = EchoServer(port)
        server.thread.start()
        proxy = UdpImpairmentProxy(
            ("127.0.0.2", port),
            ("127.0.0.1", port),
            client_loss=1.0,
            seed=37,
            logger=JsonLogger(None, False),
        )
        proxy_thread = self.run_proxy(proxy)
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(0.15)
        try:
            client.sendto(b"drop-me", ("127.0.0.2", port))
            with self.assertRaises(socket.timeout):
                client.recvfrom(1024)
            deadline = time.monotonic() + 0.5
            while proxy.stats.client_dropped == 0 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(proxy.stats.client_dropped, 1)
            self.assertEqual(proxy.stats.client_forwarded, 0)
        finally:
            client.close()
            proxy.stop()
            proxy_thread.join(timeout=1.0)
            proxy.close()
            server.close()

    def test_server_to_client_loss_is_direction_specific(self) -> None:
        port = free_port()
        server = EchoServer(port)
        server.thread.start()
        proxy = UdpImpairmentProxy(
            ("127.0.0.2", port),
            ("127.0.0.1", port),
            client_loss=0.0,
            server_loss=1.0,
            seed=37,
            logger=JsonLogger(None, False),
        )
        proxy_thread = self.run_proxy(proxy)
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(0.2)
        try:
            client.sendto(b"one-way", ("127.0.0.2", port))
            with self.assertRaises(socket.timeout):
                client.recvfrom(1024)
            deadline = time.monotonic() + 0.5
            while proxy.stats.server_dropped == 0 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(server.received, [b"one-way"])
            self.assertEqual(proxy.stats.client_forwarded, 1)
            self.assertEqual(proxy.stats.client_dropped, 0)
            self.assertEqual(proxy.stats.server_dropped, 1)
            self.assertEqual(proxy.stats.server_forwarded, 0)
        finally:
            client.close()
            proxy.stop()
            proxy_thread.join(timeout=1.0)
            proxy.close()
            server.close()

    def test_seeded_reorder_changes_actual_delivery_order(self) -> None:
        port = free_port()
        server = EchoServer(port)
        server.thread.start()
        proxy = UdpImpairmentProxy(
            ("127.0.0.2", port),
            ("127.0.0.1", port),
            reorder_probability=0.5,
            reorder_hold_ms=100.0,
            seed=9,
            logger=JsonLogger(None, False),
        )
        proxy_thread = self.run_proxy(proxy)
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(1.0)
        try:
            # Seed 9 holds the first client datagram and forwards the second
            # immediately.  This asserts observable order, not only counters.
            client.sendto(b"first", ("127.0.0.2", port))
            client.sendto(b"second", ("127.0.0.2", port))
            first_payload, _ = client.recvfrom(1024)
            second_payload, _ = client.recvfrom(1024)
            self.assertEqual([first_payload, second_payload], [b"second", b"first"])
            self.assertGreaterEqual(proxy.stats.reordered, 1)
            self.assertEqual(proxy.stats.client_forwarded, 2)
            self.assertEqual(proxy.stats.server_forwarded, 2)
        finally:
            client.close()
            proxy.stop()
            proxy_thread.join(timeout=1.0)
            proxy.close()
            server.close()

    def test_second_client_is_counted_and_not_forwarded(self) -> None:
        port = free_port()
        server = EchoServer(port)
        server.thread.start()
        proxy = UdpImpairmentProxy(
            ("127.0.0.2", port),
            ("127.0.0.1", port),
            logger=JsonLogger(None, False),
        )
        proxy_thread = self.run_proxy(proxy)
        selected = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        foreign = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        selected.settimeout(1.0)
        foreign.settimeout(0.2)
        try:
            selected.sendto(b"selected", ("127.0.0.2", port))
            payload, _ = selected.recvfrom(1024)
            self.assertEqual(payload, b"selected")

            foreign.sendto(b"foreign", ("127.0.0.2", port))
            with self.assertRaises(socket.timeout):
                foreign.recvfrom(1024)
            deadline = time.monotonic() + 0.5
            while proxy.stats.foreign_clients == 0 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(proxy.stats.foreign_clients, 1)
            self.assertEqual(server.received, [b"selected"])
        finally:
            selected.close()
            foreign.close()
            proxy.stop()
            proxy_thread.join(timeout=1.0)
            proxy.close()
            server.close()


if __name__ == "__main__":
    unittest.main()
