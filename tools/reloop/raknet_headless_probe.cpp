#include "sampdll/net/raknet_client_adapter.h"

#include "raknet/GetTime.h"
#include "raknet/BitStream.h"
#include "raknet/PacketEnumerations.h"
#include "raknet/PacketPriority.h"
#include "raknet/PluginInterface.h"
#include "raknet/RakClientInterface.h"

#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>

namespace {

extern "C" const char *samp_raknet_knogle_auth_response(const char *challenge);

struct Options {
  const char *host = "127.0.0.1";
  const char *nickname = "HeadlessProbe";
  const char *password = nullptr;
  std::uint16_t server_port = 7807U;
  std::uint16_t client_port = 0U;
  unsigned int duration_ms = 3000U;
  int expected_packet = -1;
  bool adapter_terminal_mode = false;
};

class DirectPacketObserver final : public RakNet::PluginInterface {
 public:
  std::array<std::atomic<unsigned int>, 256U> counts = {};

  void OnDirectSocketReceive(const char *data, const unsigned bits_used,
                             RakNet::PlayerID /*remote_system_id*/) override {
    if (data == nullptr || bits_used < 8U) {
      return;
    }
    const auto packet_id = static_cast<unsigned char>(data[0]);
    counts[packet_id].fetch_add(1U, std::memory_order_relaxed);
  }
};

bool parse_unsigned(const char *value, unsigned long maximum, unsigned long *out) {
  char *end = nullptr;
  unsigned long parsed = 0UL;

  if (value == nullptr || value[0] == '\0' || out == nullptr) {
    return false;
  }
  parsed = std::strtoul(value, &end, 10);
  if (end == value || end == nullptr || end[0] != '\0' || parsed > maximum) {
    return false;
  }
  *out = parsed;
  return true;
}

bool parse_options(int argc, char **argv, Options *options) {
  if (options == nullptr) {
    return false;
  }
  for (int index = 1; index < argc; ++index) {
    const char *name = argv[index];
    if (std::strcmp(name, "--help") == 0) {
      return false;
    }
    if (std::strcmp(name, "--adapter-terminal") == 0) {
      options->adapter_terminal_mode = true;
      continue;
    }
    if (index + 1 >= argc) {
      std::fprintf(stderr, "missing value for %s\n", name);
      return false;
    }
    const char *value = argv[++index];
    unsigned long parsed = 0UL;
    if (std::strcmp(name, "--host") == 0) {
      options->host = value;
    } else if (std::strcmp(name, "--port") == 0) {
      if (!parse_unsigned(value, 65535UL, &parsed) || parsed == 0UL) {
        return false;
      }
      options->server_port = static_cast<std::uint16_t>(parsed);
    } else if (std::strcmp(name, "--client-port") == 0) {
      if (!parse_unsigned(value, 65535UL, &parsed)) {
        return false;
      }
      options->client_port = static_cast<std::uint16_t>(parsed);
    } else if (std::strcmp(name, "--name") == 0) {
      options->nickname = value;
    } else if (std::strcmp(name, "--password") == 0) {
      options->password = value;
    } else if (std::strcmp(name, "--duration-ms") == 0) {
      if (!parse_unsigned(value, 600000UL, &parsed) || parsed == 0UL) {
        return false;
      }
      options->duration_ms = static_cast<unsigned int>(parsed);
    } else if (std::strcmp(name, "--expect-packet") == 0) {
      if (!parse_unsigned(value, 255UL, &parsed)) {
        return false;
      }
      options->expected_packet = static_cast<int>(parsed);
    } else {
      std::fprintf(stderr, "unknown option: %s\n", name);
      return false;
    }
  }
  return true;
}

void usage(const char *program) {
  std::fprintf(
      stderr,
      "usage: %s [--host HOST] [--port PORT] [--client-port PORT] [--name NAME]\n"
      "          [--password PASSWORD] [--duration-ms MS] [--expect-packet ID]\n"
      "          [--adapter-terminal]\n",
      program);
}

bool send_auth_response(RakNet::RakClientInterface *client, const RakNet::Packet *packet) {
  if (client == nullptr || packet == nullptr || packet->data == nullptr || packet->length <= 2U) {
    return false;
  }
  const unsigned int challenge_length = packet->data[1];
  if (challenge_length == 0U || challenge_length >= 128U || packet->length < 2U + challenge_length) {
    return false;
  }

  char challenge[128] = {};
  std::memcpy(challenge, packet->data + 2U, challenge_length);
  const char *response = samp_raknet_knogle_auth_response(challenge);
  if (response == nullptr) {
    return false;
  }
  const std::size_t response_length = std::strlen(response);
  if (response_length == 0U || response_length > 255U) {
    return false;
  }

  RakNet::BitStream outgoing;
  outgoing.Write(static_cast<unsigned char>(RakNet::ID_AUTH_KEY));
  outgoing.Write(static_cast<unsigned char>(response_length));
  outgoing.Write(response, static_cast<int>(response_length));
  return client->Send(&outgoing, RakNet::HIGH_PRIORITY, RakNet::RELIABLE, 0);
}

}  // namespace

int main(int argc, char **argv) {
  Options options;
  void *client = nullptr;
  std::array<unsigned int, 256U> packet_counts = {};
  DirectPacketObserver direct_observer;
  int ever_connected = 0;
  int auth_sent = 0;
  int expected_seen = 0;
  unsigned int drained_total = 0U;
  int unexpected_packet = -1;

  if (!parse_options(argc, argv, &options)) {
    usage(argv[0]);
    return 64;
  }
  if (std::strlen(options.nickname) >= 64U) {
    std::fprintf(stderr, "probe name must be shorter than 64 bytes\n");
    return 64;
  }
  if (samp_raknet_client_create(&client) != 0 || client == nullptr) {
    std::fprintf(stderr, "RakNet client creation failed\n");
    return 70;
  }
  if (samp_raknet_client_set_password(client, options.password) != 0) {
    std::fprintf(stderr, "RakNet password setup failed\n");
    samp_raknet_client_destroy(client);
    return 70;
  }
  auto *raw_client = static_cast<RakNet::RakClientInterface *>(client);
  raw_client->AttachPlugin(&direct_observer);
  if (samp_raknet_client_connect(client, options.host, options.server_port, options.client_port, 5) != 0) {
    std::fprintf(stderr, "RakNet connect request was rejected locally\n");
    raw_client->DetachPlugin(&direct_observer);
    samp_raknet_client_destroy(client);
    return 69;
  }

  const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(options.duration_ms);
  while (std::chrono::steady_clock::now() < deadline) {
    int packet_id = -1;
    RakNet::Packet *packet = nullptr;
    if (options.adapter_terminal_mode) {
      int connected = 0;
      int join_sent = 0;
      const int drained = samp_raknet_client_drain_packets_autojoin(
          client, 1, nullptr, &connected, &join_sent, &packet_id);
      if (drained > 0) {
        drained_total += static_cast<unsigned int>(drained);
        if (packet_id >= 0 && packet_id <= 255) {
          ++packet_counts[static_cast<std::size_t>(packet_id)];
          if (packet_id == options.expected_packet) {
            expected_seen = 1;
            break;
          } else {
            unexpected_packet = packet_id;
            break;
          }
        }
      }
    } else {
      packet = raw_client->Receive();
      if (packet != nullptr && packet->data != nullptr && packet->length > 0U) {
        unsigned int packet_offset = 0U;
        if (packet->data[0] == static_cast<unsigned char>(RakNet::ID_TIMESTAMP)) {
          packet_offset = 1U + static_cast<unsigned int>(sizeof(RakNet::RakNetTime));
        }
        if (packet_offset < packet->length) {
          packet_id = static_cast<int>(packet->data[packet_offset]);
        }
      }
    }
    if (samp_raknet_client_is_connected(client) != 0) {
      ever_connected = 1;
    }
    if (!options.adapter_terminal_mode && packet_id >= 0 && packet_id <= 255) {
      ++packet_counts[static_cast<std::size_t>(packet_id)];
      ++drained_total;
      if (packet_id == static_cast<int>(RakNet::ID_AUTH_KEY) && send_auth_response(raw_client, packet)) {
        auth_sent = 1;
      }
      if (packet_id == options.expected_packet) {
        expected_seen = 1;
      }
    }
    if (packet != nullptr) {
      raw_client->DeallocatePacket(packet);
    }
    if (packet_id < 0) {
      std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
  }

  samp_raknet_client_disconnect(client, 0U, 0U);
  raw_client->DetachPlugin(&direct_observer);
  if (!options.adapter_terminal_mode && options.expected_packet >= 0 &&
      direct_observer.counts[static_cast<std::size_t>(options.expected_packet)].load(std::memory_order_relaxed) > 0U) {
    expected_seen = 1;
  }
  samp_raknet_client_destroy(client);

  std::printf("{\"probe\":\"%s\",\"host\":\"%s\",\"port\":%u,\"duration_ms\":%u,"
              "\"drained\":%u,\"ever_connected\":%d,\"auth_sent\":%d,"
              "\"adapter_terminal_mode\":%d,\"unexpected_packet\":%d,"
              "\"packet_counts\":{",
              options.nickname, options.host, static_cast<unsigned int>(options.server_port), options.duration_ms,
              drained_total, ever_connected, auth_sent, options.adapter_terminal_mode ? 1 : 0,
              unexpected_packet);
  bool first = true;
  for (std::size_t id = 0U; id < packet_counts.size(); ++id) {
    if (packet_counts[id] == 0U) {
      continue;
    }
    std::printf("%s\"%zu\":%u", first ? "" : ",", id, packet_counts[id]);
    first = false;
  }
  std::printf("},\"direct_packet_counts\":{");
  first = true;
  for (std::size_t id = 0U; id < direct_observer.counts.size(); ++id) {
    const unsigned int count = direct_observer.counts[id].load(std::memory_order_relaxed);
    if (count == 0U) {
      continue;
    }
    std::printf("%s\"%zu\":%u", first ? "" : ",", id, count);
    first = false;
  }
  std::printf("},\"expected_packet\":%d,\"expected_seen\":%d}\n", options.expected_packet,
              options.expected_packet < 0 ? 1 : expected_seen);

  return options.expected_packet >= 0 && expected_seen == 0 ? 1 : 0;
}
