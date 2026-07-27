#!/usr/bin/env python3
"""Deterministic, local UDP impairment proxy for SA-MP parity runs.

Bind the proxy to a second loopback address while the server keeps the same
UDP port on 127.0.0.1.  Keeping the port unchanged matters because SA-MP's
legacy socket transform includes the remote port in its wire transform.
"""

from __future__ import annotations

import argparse
import heapq
import json
import random
import selectors
import signal
import socket
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO


@dataclass
class ProxyStats:
    client_received: int = 0
    client_forwarded: int = 0
    client_dropped: int = 0
    server_received: int = 0
    server_forwarded: int = 0
    server_dropped: int = 0
    reordered: int = 0
    send_errors: int = 0
    foreign_clients: int = 0


@dataclass(order=True)
class PendingDatagram:
    due: float
    sequence: int
    direction: str
    payload: bytes


class JsonLogger:
    def __init__(self, stream: BinaryIO | None, verbose: bool) -> None:
        self.stream = stream
        self.verbose = verbose

    def event(self, name: str, *, always: bool = False, **fields: object) -> None:
        if self.stream is None or (not always and not self.verbose):
            return
        record = {
            "time_monotonic": round(time.monotonic(), 6),
            "event": name,
            **fields,
        }
        self.stream.write((json.dumps(record, sort_keys=True) + "\n").encode("utf-8"))
        self.stream.flush()


class UdpImpairmentProxy:
    """One-client UDP proxy with seeded loss, delay, jitter, and reordering."""

    def __init__(
        self,
        listen: tuple[str, int],
        upstream: tuple[str, int],
        *,
        client_loss: float = 0.0,
        server_loss: float = 0.0,
        delay_ms: float = 0.0,
        jitter_ms: float = 0.0,
        reorder_probability: float = 0.0,
        reorder_hold_ms: float = 40.0,
        seed: int = 0,
        logger: JsonLogger | None = None,
    ) -> None:
        self.listen = listen
        self.upstream_address = upstream
        self.client_loss = client_loss
        self.server_loss = server_loss
        self.delay_ms = delay_ms
        self.jitter_ms = jitter_ms
        self.reorder_probability = reorder_probability
        self.reorder_hold_ms = reorder_hold_ms
        self.random = random.Random(seed)
        self.logger = logger or JsonLogger(None, False)
        self.stats = ProxyStats()
        self.pending: list[PendingDatagram] = []
        self.sequence = 0
        self.client_address: tuple[str, int] | None = None
        self.stopping = False

        self.downstream = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.downstream.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.downstream.bind(listen)
        self.downstream.setblocking(False)

        self.upstream = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.upstream.connect(upstream)
        self.upstream.setblocking(False)

        self.selector = selectors.DefaultSelector()
        self.selector.register(self.downstream, selectors.EVENT_READ, "client_to_server")
        self.selector.register(self.upstream, selectors.EVENT_READ, "server_to_client")

    def close(self) -> None:
        self.selector.close()
        self.downstream.close()
        self.upstream.close()

    def stop(self) -> None:
        self.stopping = True

    def _schedule(self, direction: str, payload: bytes) -> None:
        loss = self.client_loss if direction == "client_to_server" else self.server_loss
        if self.random.random() < loss:
            if direction == "client_to_server":
                self.stats.client_dropped += 1
            else:
                self.stats.server_dropped += 1
            self.logger.event("drop", direction=direction, bytes=len(payload))
            return

        delay_ms = self.delay_ms
        if self.jitter_ms > 0.0:
            delay_ms += self.random.uniform(-self.jitter_ms, self.jitter_ms)
        reordered = self.random.random() < self.reorder_probability
        if reordered:
            delay_ms += self.reorder_hold_ms
            self.stats.reordered += 1
        delay_ms = max(0.0, delay_ms)

        self.sequence += 1
        heapq.heappush(
            self.pending,
            PendingDatagram(
                due=time.monotonic() + delay_ms / 1000.0,
                sequence=self.sequence,
                direction=direction,
                payload=payload,
            ),
        )
        self.logger.event(
            "schedule",
            direction=direction,
            bytes=len(payload),
            delay_ms=round(delay_ms, 3),
            reordered=reordered,
        )

    def _receive(self, source: str) -> None:
        if source == "client_to_server":
            payload, address = self.downstream.recvfrom(65535)
            if self.client_address is None:
                self.client_address = address
                self.logger.event("client_selected", always=True, address=list(address))
            elif address != self.client_address:
                self.stats.foreign_clients += 1
                self.logger.event("foreign_client", address=list(address), bytes=len(payload))
                return
            self.stats.client_received += 1
        else:
            payload = self.upstream.recv(65535)
            if self.client_address is None:
                return
            self.stats.server_received += 1
        self._schedule(source, payload)

    def _flush_due(self) -> None:
        now = time.monotonic()
        while self.pending and self.pending[0].due <= now:
            pending = heapq.heappop(self.pending)
            try:
                if pending.direction == "client_to_server":
                    self.upstream.send(pending.payload)
                    self.stats.client_forwarded += 1
                elif self.client_address is not None:
                    self.downstream.sendto(pending.payload, self.client_address)
                    self.stats.server_forwarded += 1
                self.logger.event(
                    "forward",
                    direction=pending.direction,
                    bytes=len(pending.payload),
                )
            except OSError as exc:
                self.stats.send_errors += 1
                self.logger.event(
                    "send_error",
                    always=True,
                    direction=pending.direction,
                    error=str(exc),
                )

    def run(self, duration_s: float | None = None) -> ProxyStats:
        started = time.monotonic()
        self.logger.event(
            "start",
            always=True,
            listen=list(self.listen),
            upstream=list(self.upstream_address),
            client_loss=self.client_loss,
            server_loss=self.server_loss,
            delay_ms=self.delay_ms,
            jitter_ms=self.jitter_ms,
            reorder_probability=self.reorder_probability,
            reorder_hold_ms=self.reorder_hold_ms,
        )
        while not self.stopping:
            now = time.monotonic()
            if duration_s is not None and now - started >= duration_s:
                break
            timeout = 0.1
            if self.pending:
                timeout = max(0.0, min(timeout, self.pending[0].due - now))
            if duration_s is not None:
                timeout = max(0.0, min(timeout, duration_s - (now - started)))
            for key, _events in self.selector.select(timeout):
                try:
                    self._receive(key.data)
                except BlockingIOError:
                    pass
            self._flush_due()

        self._flush_due()
        self.logger.event("stop", always=True, stats=asdict(self.stats))
        return self.stats


def endpoint(value: str) -> tuple[str, int]:
    host, separator, port = value.rpartition(":")
    if not separator or not host:
        raise argparse.ArgumentTypeError("endpoint must be HOST:PORT")
    try:
        parsed_port = int(port)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("endpoint port must be an integer") from exc
    if not 1 <= parsed_port <= 65535:
        raise argparse.ArgumentTypeError("endpoint port must be in 1..65535")
    return host, parsed_port


def probability(value: str) -> float:
    parsed = float(value)
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError("probability must be in 0..1")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen", type=endpoint, default=("127.0.0.2", 7798))
    parser.add_argument("--upstream", type=endpoint, default=("127.0.0.1", 7798))
    parser.add_argument("--loss", type=probability, default=0.0, help="loss in both directions")
    parser.add_argument("--client-loss", type=probability)
    parser.add_argument("--server-loss", type=probability)
    parser.add_argument("--delay-ms", type=float, default=0.0)
    parser.add_argument("--jitter-ms", type=float, default=0.0)
    parser.add_argument("--reorder", type=probability, default=0.0)
    parser.add_argument("--reorder-hold-ms", type=float, default=40.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--stats", type=Path)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if min(args.delay_ms, args.jitter_ms, args.reorder_hold_ms) < 0.0:
        parser.error("delay, jitter, and reorder hold must be non-negative")
    if args.duration is not None and args.duration <= 0.0:
        parser.error("duration must be positive")

    client_loss = args.loss if args.client_loss is None else args.client_loss
    server_loss = args.loss if args.server_loss is None else args.server_loss
    log_stream: BinaryIO | None = None
    if args.log is not None:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        log_stream = args.log.open("wb")
    logger = JsonLogger(log_stream, args.verbose)

    proxy = UdpImpairmentProxy(
        args.listen,
        args.upstream,
        client_loss=client_loss,
        server_loss=server_loss,
        delay_ms=args.delay_ms,
        jitter_ms=args.jitter_ms,
        reorder_probability=args.reorder,
        reorder_hold_ms=args.reorder_hold_ms,
        seed=args.seed,
        logger=logger,
    )

    def request_stop(_signum: int, _frame: object) -> None:
        proxy.stop()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        stats = proxy.run(args.duration)
    finally:
        proxy.close()
        if log_stream is not None:
            log_stream.close()

    stats_record = asdict(stats)
    if args.stats is not None:
        args.stats.parent.mkdir(parents=True, exist_ok=True)
        args.stats.write_text(json.dumps(stats_record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(stats_record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
