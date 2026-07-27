#include "sampdll/net/raknet_client_adapter.h"

#include "raknet/PacketEnumerations.h"
#include "raknet_offline_status_observer.h"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <thread>

namespace {

int assert_true(bool condition, const char *message) {
  if (!condition) {
    std::fprintf(stderr, "FAIL: %s\n", message);
    return 1;
  }
  return 0;
}

class OneShotOfflineReplyServer {
 public:
  ~OneShotOfflineReplyServer() {
    Join();
    if (socket_ >= 0) {
      close(socket_);
    }
  }

  bool Start(unsigned char packet_id) {
    socket_ = socket(AF_INET, SOCK_DGRAM, 0);
    if (socket_ < 0) {
      return false;
    }

    const timeval timeout = {2, 0};
    if (setsockopt(socket_, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) != 0) {
      return false;
    }

    sockaddr_in address = {};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = 0;
    if (bind(socket_, reinterpret_cast<const sockaddr *>(&address), sizeof(address)) != 0) {
      return false;
    }

    socklen_t address_size = sizeof(address);
    if (getsockname(socket_, reinterpret_cast<sockaddr *>(&address), &address_size) != 0) {
      return false;
    }
    port_ = ntohs(address.sin_port);
    packet_id_ = packet_id;
    worker_ = std::thread(&OneShotOfflineReplyServer::Run, this);
    return true;
  }

  void Join() {
    if (worker_.joinable()) {
      worker_.join();
    }
  }

  std::uint16_t port() const { return port_; }
  bool received_request() const { return received_request_; }
  bool sent_reply() const { return sent_reply_; }

 private:
  void Run() {
    unsigned char request[64] = {};
    sockaddr_in client_address = {};
    socklen_t client_address_size = sizeof(client_address);
    const ssize_t received =
        recvfrom(socket_, request, sizeof(request), 0,
                 reinterpret_cast<sockaddr *>(&client_address), &client_address_size);
    if (received <= 0) {
      return;
    }
    received_request_ = true;

    const unsigned char reply[2] = {packet_id_, 0U};
    sent_reply_ =
        sendto(socket_, reply, sizeof(reply), 0,
               reinterpret_cast<const sockaddr *>(&client_address), client_address_size) ==
        static_cast<ssize_t>(sizeof(reply));
  }

  int socket_ = -1;
  std::uint16_t port_ = 0U;
  unsigned char packet_id_ = 0U;
  bool received_request_ = false;
  bool sent_reply_ = false;
  std::thread worker_;
};

bool localhost_udp_available() {
  const int probe = socket(AF_INET, SOCK_DGRAM, 0);
  if (probe < 0) {
    return false;
  }

  sockaddr_in address = {};
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  address.sin_port = 0;
  const bool available =
      bind(probe, reinterpret_cast<const sockaddr *>(&address), sizeof(address)) == 0;
  close(probe);
  return available;
}

int test_observer_filter() {
  int failed = 0;
  SampDll::Net::RakNetOfflineStatusObserver observer;
  const RakNet::PlayerID expected = {0x01020304U, 7777U};
  const RakNet::PlayerID foreign = {0x01020305U, 7777U};
  const char open_request[3] = {
      static_cast<char>(RakNet::ID_OPEN_CONNECTION_REQUEST), 0, 0};
  const char server_full[2] = {
      static_cast<char>(RakNet::ID_NO_FREE_INCOMING_CONNECTIONS), 0};
  const char banned[2] = {static_cast<char>(RakNet::ID_CONNECTION_BANNED), 0};

  observer.OnDirectSocketReceive(server_full, 16U, expected);
  failed += assert_true(observer.Consume() == -1,
                        "status is rejected before an outbound target is learned");

  observer.OnDirectSocketSend(open_request, 24U, expected);
  observer.OnDirectSocketReceive(server_full, 16U, foreign);
  failed += assert_true(observer.Consume() == -1,
                        "status from a foreign endpoint is rejected");

  const char malformed_server_full[2] = {
      static_cast<char>(RakNet::ID_NO_FREE_INCOMING_CONNECTIONS), 1};
  observer.OnDirectSocketReceive(malformed_server_full, 16U, expected);
  observer.OnDirectSocketReceive(server_full, 8U, expected);
  failed += assert_true(observer.Consume() == -1,
                        "non-padded or non-two-byte status is rejected");

  observer.OnDirectSocketReceive(server_full, 16U, expected);
  failed += assert_true(
      observer.Consume() == static_cast<int>(RakNet::ID_NO_FREE_INCOMING_CONNECTIONS),
      "server-full status from the intended endpoint is queued once");
  failed += assert_true(observer.Consume() == -1,
                        "consuming a direct status clears the pending slot");

  observer.OnDirectSocketReceive(banned, 16U, expected);
  failed += assert_true(
      observer.Consume() == static_cast<int>(RakNet::ID_CONNECTION_BANNED),
      "banned status from the intended endpoint is queued");

  const unsigned char receive_path_ids[] = {
      static_cast<unsigned char>(RakNet::ID_CONNECTION_ATTEMPT_FAILED),
      static_cast<unsigned char>(RakNet::ID_CONNECTION_LOST),
      static_cast<unsigned char>(RakNet::ID_INVALID_PASSWORD),
  };
  for (unsigned char packet_id : receive_path_ids) {
    const char packet[2] = {static_cast<char>(packet_id), 0};
    observer.OnDirectSocketReceive(packet, 16U, expected);
    failed += assert_true(observer.Consume() == -1,
                          "normal Receive-path terminal status is not duplicated");
  }

  return failed;
}

int test_adapter_delivery(unsigned char packet_id) {
  int failed = 0;
  OneShotOfflineReplyServer server;
  void *client = nullptr;

  if (!server.Start(packet_id)) {
    return assert_true(false, "one-shot UDP reply server starts");
  }
  if (samp_raknet_client_create(&client) != 0 || client == nullptr) {
    server.Join();
    return assert_true(false, "RakNet adapter client is created");
  }
  if (samp_raknet_client_connect(client, "127.0.0.1", server.port(), 0U, 5) != 0) {
    samp_raknet_client_destroy(client);
    server.Join();
    return assert_true(false, "RakNet adapter connection attempt starts");
  }

  server.Join();
  if (packet_id == static_cast<unsigned char>(RakNet::ID_NO_FREE_INCOMING_CONNECTIONS) ||
      packet_id == static_cast<unsigned char>(RakNet::ID_CONNECTION_BANNED)) {
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
    failed += assert_true(
        samp_raknet_client_drain_packets(client, 8) == 0,
        "status-less drain leaves a direct transport status pending");
  }

  bool observed = false;
  const auto deadline =
      std::chrono::steady_clock::now() + std::chrono::milliseconds(2500);
  while (std::chrono::steady_clock::now() < deadline && !observed) {
    int connected = 0;
    int join_sent = 0;
    int last_packet_id = -1;
    const int drained = samp_raknet_client_drain_packets_autojoin(
        client, 8, nullptr, &connected, &join_sent, &last_packet_id);
    if (drained > 0 && last_packet_id == static_cast<int>(packet_id)) {
      observed = true;
      break;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
  }

  samp_raknet_client_disconnect(client, 0U, 0U);
  samp_raknet_client_destroy(client);

  failed += assert_true(server.received_request(),
                        "one-shot server receives the RakNet open request");
  failed += assert_true(server.sent_reply(),
                        "one-shot server sends the selected offline reply");
  failed += assert_true(observed,
                        "adapter drain exposes the selected transport status");
  return failed;
}

}  // namespace

int main() {
  int failed = 0;

  failed += test_observer_filter();
  if (!localhost_udp_available()) {
    std::fprintf(stdout,
                 "SKIP: localhost UDP unavailable; direct observer checks passed\n");
    return failed == 0 ? 0 : 1;
  }
  failed += test_adapter_delivery(
      static_cast<unsigned char>(RakNet::ID_CONNECTION_ATTEMPT_FAILED));
  failed += test_adapter_delivery(
      static_cast<unsigned char>(RakNet::ID_NO_FREE_INCOMING_CONNECTIONS));
  failed +=
      test_adapter_delivery(static_cast<unsigned char>(RakNet::ID_CONNECTION_BANNED));

  if (failed != 0) {
    std::fprintf(stderr, "%d checks failed\n", failed);
    return 1;
  }

  std::fprintf(stdout, "All RakNet offline status delivery checks passed\n");
  return 0;
}
