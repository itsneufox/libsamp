#ifndef SAMPDLL_NET_RAKNET_OFFLINE_STATUS_OBSERVER_H
#define SAMPDLL_NET_RAKNET_OFFLINE_STATUS_OBSERVER_H

#include <atomic>
#include <cstdint>

#include "raknet/PacketEnumerations.h"
#include "raknet/PluginInterface.h"

namespace SampDll {
namespace Net {

/*
 * PROBE_TRACE + INFERRED:
 * The vendored RakPeer invokes OnDirectSocketReceive for the two-byte offline
 * server-full and banned replies, but does not add either reply to its packet
 * producer.  Keep this sidecar limited to those proven direct-only replies;
 * connection-attempt-failed, connection-lost, and invalid-password already
 * reach RakClient::Receive through RakPeer's normal producer/reliability path.
 *
 * TODO_VERIFY the original 0.3.7 client UI text and retry cadence separately.
 */
class RakNetOfflineStatusObserver final : public RakNet::PluginInterface {
 public:
  RakNetOfflineStatusObserver() { Reset(); }

  void Reset() {
    expected_remote_valid_.store(false, std::memory_order_release);
    pending_packet_id_.store(kNoPacket, std::memory_order_release);
  }

  void OnDirectSocketSend(const char *data, const unsigned bits_used,
                          RakNet::PlayerID remote_system_id) override {
    if (data == nullptr || bits_used < 16U || bits_used > 24U ||
        static_cast<unsigned char>(data[0]) !=
            static_cast<unsigned char>(RakNet::ID_OPEN_CONNECTION_REQUEST)) {
      return;
    }

    expected_remote_valid_.store(false, std::memory_order_relaxed);
    expected_remote_address_.store(remote_system_id.binaryAddress, std::memory_order_relaxed);
    expected_remote_port_.store(remote_system_id.port, std::memory_order_relaxed);
    expected_remote_valid_.store(true, std::memory_order_release);
  }

  void OnDirectSocketReceive(const char *data, const unsigned bits_used,
                             RakNet::PlayerID remote_system_id) override {
    if (data == nullptr || bits_used != 16U ||
        static_cast<unsigned char>(data[1]) != 0U ||
        !expected_remote_valid_.load(std::memory_order_acquire) ||
        expected_remote_address_.load(std::memory_order_relaxed) !=
            remote_system_id.binaryAddress ||
        expected_remote_port_.load(std::memory_order_relaxed) !=
            remote_system_id.port) {
      return;
    }

    const unsigned char packet_id = static_cast<unsigned char>(data[0]);
    if (packet_id == static_cast<unsigned char>(RakNet::ID_NO_FREE_INCOMING_CONNECTIONS) ||
        packet_id == static_cast<unsigned char>(RakNet::ID_CONNECTION_BANNED)) {
      pending_packet_id_.store(static_cast<int>(packet_id), std::memory_order_release);
    }
  }

  int Consume() {
    return pending_packet_id_.exchange(kNoPacket, std::memory_order_acq_rel);
  }

 private:
  static constexpr int kNoPacket = -1;

  std::atomic<unsigned int> expected_remote_address_;
  std::atomic<unsigned int> expected_remote_port_;
  std::atomic<bool> expected_remote_valid_;
  std::atomic<int> pending_packet_id_;
};

}  // namespace Net
}  // namespace SampDll

#endif
