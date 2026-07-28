#include "sampdll/net/raknet_client_adapter.h"

#include "raknet_client_adapter_test.h"

#include "raknet/GetTime.h"
#include "raknet/PacketEnumerations.h"

#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

namespace {

template <typename Payload>
std::vector<unsigned char> make_packet(unsigned char packet_id,
                                       std::uint16_t player_id,
                                       const Payload &payload) {
  std::vector<unsigned char> packet(3U + sizeof(payload), 0U);
  packet[0] = packet_id;
  std::memcpy(packet.data() + 1U, &player_id, sizeof(player_id));
  std::memcpy(packet.data() + 3U, &payload, sizeof(payload));
  return packet;
}

std::vector<unsigned char>
timestamp_wrap(const std::vector<unsigned char> &packet) {
  std::vector<unsigned char> wrapped(
      1U + sizeof(RakNet::RakNetTime) + packet.size(), 0U);
  const RakNet::RakNetTime timestamp = 0x12345678U;
  wrapped[0] = RakNet::ID_TIMESTAMP;
  std::memcpy(wrapped.data() + 1U, &timestamp, sizeof(timestamp));
  std::memcpy(wrapped.data() + 1U + sizeof(timestamp), packet.data(),
              packet.size());
  return wrapped;
}

void expect_float(float actual, float expected) {
  assert(std::fabs(actual - expected) < 0.00001f);
}

} // namespace

int main() {
  void *client = nullptr;
  samp_raknet_rpc_probe_snapshot snapshot{};

  static_assert(sizeof(samp_raknet_unoccupied_sync) == 67U);
  static_assert(sizeof(samp_raknet_trailer_sync) == 54U);
  static_assert(sizeof(samp_raknet_passenger_sync) == 24U);

  assert(samp_raknet_test_remote_movement_drain_should_yield(0U, 0U) == 0);
  assert(samp_raknet_test_remote_movement_drain_should_yield(
             0U, SAMP_RAKNET_REMOTE_PLAYER_SYNC_RING - 1U) == 0);
  assert(samp_raknet_test_remote_movement_drain_should_yield(
             0U, SAMP_RAKNET_REMOTE_PLAYER_SYNC_RING) == 1);
  assert(samp_raknet_test_remote_movement_drain_should_yield(
             900U, 900U + SAMP_RAKNET_REMOTE_PLAYER_SYNC_RING) == 1);
  assert(samp_raknet_test_remote_movement_drain_should_yield(
             0xFFFFFFFEU, 1U) == 0);
  assert(samp_raknet_test_remote_movement_drain_should_yield(
             0xFFFFFF80U, 1U) == 1);

  assert(samp_raknet_client_create(&client) == 0);
  assert(client != nullptr);

  samp_raknet_unoccupied_sync unoccupied{};
  unoccupied.vehicle_id = 601U;
  unoccupied.seat_id = 3U;
  unoccupied.roll[0] = 0.25f;
  unoccupied.roll[1] = -0.5f;
  unoccupied.roll[2] = 0.75f;
  unoccupied.rotation[0] = -0.125f;
  unoccupied.rotation[1] = 0.625f;
  unoccupied.rotation[2] = 1.0f;
  unoccupied.position[0] = 123.5f;
  unoccupied.position[1] = -456.25f;
  unoccupied.position[2] = 78.75f;
  unoccupied.move_speed[0] = 1.25f;
  unoccupied.move_speed[1] = -2.5f;
  unoccupied.move_speed[2] = 3.75f;
  unoccupied.turn_speed[0] = -0.75f;
  unoccupied.turn_speed[1] = 0.5f;
  unoccupied.turn_speed[2] = 0.25f;
  unoccupied.vehicle_health = 777.5f;
  const auto packet209 = make_packet(209U, 321U, unoccupied);
  assert(packet209.size() == 70U);
  assert(samp_raknet_test_ingest_remote_edge_sync(
             packet209.data(), static_cast<unsigned int>(packet209.size())) ==
         1);

  samp_raknet_trailer_sync trailer{};
  trailer.vehicle_id = 602U;
  trailer.position[0] = -10.5f;
  trailer.position[1] = 20.25f;
  trailer.position[2] = 30.75f;
  trailer.quaternion[0] = 0.5f;
  trailer.quaternion[1] = -0.25f;
  trailer.quaternion[2] = 0.75f;
  trailer.quaternion[3] = -0.125f;
  trailer.move_speed[0] = 4.0f;
  trailer.move_speed[1] = -5.0f;
  trailer.move_speed[2] = 6.0f;
  trailer.turn_speed[0] = -0.4f;
  trailer.turn_speed[1] = 0.5f;
  trailer.turn_speed[2] = -0.6f;
  const auto packet210 = make_packet(210U, 322U, trailer);
  assert(packet210.size() == 57U);
  assert(samp_raknet_test_ingest_remote_edge_sync(
             packet210.data(), static_cast<unsigned int>(packet210.size())) ==
         1);

  samp_raknet_passenger_sync passenger{};
  passenger.vehicle_id = 603U;
  passenger.seat_flags = static_cast<std::uint8_t>(4U | 0x40U | 0x80U);
  passenger.additional_key_weapon = static_cast<std::uint8_t>((2U << 6U) | 31U);
  passenger.health = 87U;
  passenger.armour = 43U;
  passenger.left_right_keys = 0x1122U;
  passenger.up_down_keys = 0x3344U;
  passenger.keys = 0x5566U;
  passenger.position[0] = 101.25f;
  passenger.position[1] = -202.5f;
  passenger.position[2] = 303.75f;
  const auto packet211 = make_packet(211U, 323U, passenger);
  assert(packet211.size() == 27U);
  const auto timestamped211 = timestamp_wrap(packet211);
  assert(samp_raknet_test_ingest_remote_edge_sync(
             timestamped211.data(),
             static_cast<unsigned int>(timestamped211.size())) == 1);

  assert(samp_raknet_client_get_rpc_probe_snapshot(client, &snapshot) == 0);
  assert((snapshot.flags & SAMP_RAKNET_RPC_FLAG_REMOTE_PLAYER_SYNC) != 0U);
  assert(snapshot.remote_unoccupied_sync_count == 1U);
  assert(snapshot.remote_trailer_sync_count == 1U);
  assert(snapshot.remote_passenger_sync_count == 1U);
  assert(snapshot.remote_movement_sync_count == 3U);
  assert(snapshot.remote_unoccupied_syncs[0].player_id == 321U);
  assert(snapshot.remote_unoccupied_syncs[0].sync.vehicle_id == 601U);
  expect_float(snapshot.remote_unoccupied_syncs[0].sync.position[1], -456.25f);
  expect_float(snapshot.remote_unoccupied_syncs[0].sync.vehicle_health, 777.5f);
  assert(snapshot.remote_trailer_syncs[0].player_id == 322U);
  assert(snapshot.remote_trailer_syncs[0].sync.vehicle_id == 602U);
  expect_float(snapshot.remote_trailer_syncs[0].sync.quaternion[2], 0.75f);
  assert(snapshot.remote_passenger_syncs[0].player_id == 323U);
  assert(snapshot.remote_passenger_syncs[0].sync.seat_flags ==
         passenger.seat_flags);
  assert(snapshot.remote_passenger_syncs[0].sync.additional_key_weapon ==
         passenger.additional_key_weapon);
  assert(snapshot.remote_movement_syncs[0].type ==
         SAMP_RAKNET_REMOTE_MOVEMENT_UNOCCUPIED);
  assert(snapshot.remote_movement_syncs[0].state.unoccupied.player_id == 321U);
  assert(snapshot.remote_movement_syncs[1].type ==
         SAMP_RAKNET_REMOTE_MOVEMENT_TRAILER);
  assert(snapshot.remote_movement_syncs[1].state.trailer.player_id == 322U);
  assert(snapshot.remote_movement_syncs[2].type ==
         SAMP_RAKNET_REMOTE_MOVEMENT_PASSENGER);
  assert(snapshot.remote_movement_syncs[2].state.passenger.player_id == 323U);

  auto truncated = packet209;
  truncated.pop_back();
  assert(samp_raknet_test_ingest_remote_edge_sync(
             truncated.data(), static_cast<unsigned int>(truncated.size())) ==
         0);
  auto wrong_id = packet209;
  wrong_id[0] = 208U;
  assert(samp_raknet_test_ingest_remote_edge_sync(
             wrong_id.data(), static_cast<unsigned int>(wrong_id.size())) == 0);
  auto trailing = packet210;
  trailing.push_back(0xA5U);
  assert(samp_raknet_test_ingest_remote_edge_sync(
             trailing.data(), static_cast<unsigned int>(trailing.size())) == 1);

  for (std::uint16_t i = 0U; i < SAMP_RAKNET_REMOTE_PLAYER_SYNC_RING + 1U;
       ++i) {
    passenger.vehicle_id = static_cast<std::uint16_t>(700U + i);
    const auto packet =
        make_packet(211U, static_cast<std::uint16_t>(400U + i), passenger);
    assert(samp_raknet_test_ingest_remote_edge_sync(
               packet.data(), static_cast<unsigned int>(packet.size())) == 1);
  }
  assert(samp_raknet_client_get_rpc_probe_snapshot(client, &snapshot) == 0);
  assert(snapshot.remote_passenger_sync_count ==
         SAMP_RAKNET_REMOTE_PLAYER_SYNC_RING);
  assert(snapshot.remote_movement_sync_count ==
         SAMP_RAKNET_REMOTE_PLAYER_SYNC_RING);
  for (std::uint32_t i = 1U; i < snapshot.remote_movement_sync_count; ++i) {
    assert(snapshot.remote_movement_syncs[i].seq ==
           snapshot.remote_movement_syncs[i - 1U].seq + 1U);
  }
  assert(snapshot.remote_movement_syncs[0].state.passenger.player_id == 401U);
  const auto &last_movement =
      snapshot.remote_movement_syncs[snapshot.remote_movement_sync_count - 1U];
  const auto expected_last_player =
      static_cast<std::uint16_t>(400U + SAMP_RAKNET_REMOTE_PLAYER_SYNC_RING);
  if (last_movement.state.passenger.player_id != expected_last_player) {
    std::fprintf(stderr, "last movement: seq=%u type=%u player=%u count=%u\n",
                 last_movement.seq, last_movement.type,
                 last_movement.state.passenger.player_id,
                 snapshot.remote_movement_sync_count);
    return 1;
  }

  assert(samp_raknet_client_destroy(client) == 0);
  client = nullptr;
  assert(samp_raknet_client_create(&client) == 0);
  assert(samp_raknet_client_get_rpc_probe_snapshot(client, &snapshot) == 0);
  assert(snapshot.remote_unoccupied_sync_count == 0U);
  assert(snapshot.remote_trailer_sync_count == 0U);
  assert(snapshot.remote_passenger_sync_count == 0U);
  assert(snapshot.remote_movement_sync_count == 0U);
  assert((snapshot.flags & SAMP_RAKNET_RPC_FLAG_REMOTE_PLAYER_SYNC) == 0U);
  assert(samp_raknet_client_destroy(client) == 0);
  return 0;
}
