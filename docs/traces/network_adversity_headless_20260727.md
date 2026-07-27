# Headless network-adversity probe, 2026-07-27

## Scope and evidence boundary

This run exercises the replacement's vendored SA-MP/RakNet transport without
starting GTA, Wine, or a graphical client.

- Evidence: `PROBE_TRACE + OPENMP_REF`.
- It proves decoded transport packets and recovery through the local impairment
  proxy.
- It is **not** `OBSERVED_037`: no original 0.3.7 client was used.
- It does not prove the exact original chat text, retry cadence, or UI state for
  "Server Full". Those remain `TODO_VERIFY` with a paired original/replacement
  client run.

The open.mp configuration reference documents `max_players` as a startup
read-only setting with a minimum of one, and `max_bots` as the independent NPC
limit:

- <https://open.mp/docs/server/config.json#player-and-npc-limits>

## Probe tool

`samp_raknet_headless_probe` is built only with the host-side test targets. It
uses the same `samp_raknet_client_create`, password, and connect adapter entry
points as the replacement. It answers the SA-MP auth-key challenge, but
deliberately does not send RPC 25 `ClientJoin`; this keeps the check below the
GTA/UI layer.

Build:

```bash
cmake -S reimpl -B build-host \
  -DSAMPDLL_BUILD_TESTS=ON \
  -DSAMPDLL_ENABLE_RAKNET_KNOGLE=ON \
  -DSAMPDLL_ENABLE_SAMP_CLIENT_TRANSPORT=ON
cmake --build build-host --target samp_raknet_headless_probe -j2
```

The JSON output has two packet maps:

- `packet_counts`: packets surfaced by `RakClient::Receive`;
- `direct_packet_counts`: decoded socket datagrams observed by the RakNet
  direct-socket callback, including offline handshake errors which the current
  vendored receive path may consume.

`--expect-packet N` succeeds when either map observes `N`.

For a fixture that is deliberately expected to reject before a normal RakNet
packet is created, `--adapter-terminal` consumes through
`samp_raknet_client_drain_packets_autojoin` instead of calling
`RakClient::Receive` directly. It stops on the first unexpected normal packet,
so it must not be used against a server which may accept the probe.

## Deterministic impairment result

The isolated open.mp server ran on port 7807 with two player slots and no bot
slots. Ports 7798 and 7799 were not touched.

Server:

```bash
cd omp-server-bare
./omp-server \
  -c network.port=7807 \
  -c max_players=2 \
  -c max_bots=0 \
  -c artwork.enable=false \
  -c announce=false \
  -c logging.file=/tmp/omp-impairment-7807.log
```

Proxy:

```bash
python3 tools/reloop/udp_impairment_proxy.py \
  --listen 127.0.0.2:7807 \
  --upstream 127.0.0.1:7807 \
  --loss 0.05 \
  --delay-ms 80 \
  --jitter-ms 20 \
  --reorder 0.10 \
  --reorder-hold-ms 60 \
  --seed 37 \
  --duration 15 \
  --verbose \
  --log artifacts/runs/20260727-network-adversity-headless/udp-impairment.jsonl \
  --stats artifacts/runs/20260727-network-adversity-headless/udp-impairment-stats.json
```

Client:

```bash
build-host/samp_raknet_headless_probe \
  --host 127.0.0.2 \
  --port 7807 \
  --name ImpairedProbe \
  --duration-ms 10000 \
  --expect-packet 34
```

Observed client result:

```json
{"probe":"ImpairedProbe","host":"127.0.0.2","port":7807,"duration_ms":10000,"drained":3,"ever_connected":1,"auth_sent":1,"packet_counts":{"12":1,"34":1,"41":1},"direct_packet_counts":{"25":1,"26":1},"expected_packet":34,"expected_seen":1}
```

Observed proxy counters:

```json
{
  "client_dropped": 1,
  "client_forwarded": 9,
  "client_received": 10,
  "foreign_clients": 0,
  "reordered": 4,
  "send_errors": 0,
  "server_dropped": 0,
  "server_forwarded": 10,
  "server_received": 10
}
```

The seeded run therefore recovered through one client-to-server drop and four
held/reordered datagrams, answered auth packet 12, and reached accepted packet
34. This is end-to-end transport recovery evidence. It does not by itself
separate offline handshake retries from reliable-message resends.

## Reproducible server-full result

Use a freshly started server process so open.mp's local connection flood state
cannot carry over from an earlier aborted probe:

```bash
cd omp-server-bare
./omp-server \
  -c network.port=7807 \
  -c max_players=1 \
  -c max_bots=0 \
  -c artwork.enable=false \
  -c announce=false \
  -c logging.file=/tmp/omp-server-full-7807.log
```

The bundled `npc_trains` script attempted to create five NPCs, but open.mp
rejected all five because `max_bots=0`. Thus no NPC occupied the only incoming
legacy-network slot.

Hold the first accepted connection:

```bash
build-host/samp_raknet_headless_probe \
  --host 127.0.0.1 \
  --port 7807 \
  --name SlotHolder \
  --duration-ms 12000 \
  --expect-packet 34
```

Observed:

```json
{"probe":"SlotHolder2","host":"127.0.0.1","port":7807,"duration_ms":12000,"drained":3,"ever_connected":1,"auth_sent":1,"packet_counts":{"12":1,"34":1,"41":1},"direct_packet_counts":{"25":1,"26":1},"expected_packet":34,"expected_seen":1}
```

While that process is still running, start a second process:

```bash
build-host/samp_raknet_headless_probe \
  --host 127.0.0.1 \
  --port 7807 \
  --name RejectedProbe \
  --duration-ms 3000 \
  --expect-packet 31
```

Observed:

```json
{"probe":"RejectedProbe2","host":"127.0.0.1","port":7807,"duration_ms":3000,"drained":0,"ever_connected":0,"auth_sent":0,"packet_counts":{},"direct_packet_counts":{"26":1,"31":1},"expected_packet":31,"expected_seen":1}
```

This pre-fix observation established the replacement gap: open.mp sent decoded
`ID_NO_FREE_INCOMING_CONNECTIONS` (31), but the vendored RakNet path exposed it
only through `OnDirectSocketReceive`; `RakClient::Receive` returned no packet.

The adapter now attaches a narrow direct-offline status observer. It learns the
intended endpoint from the outgoing open-connection request and accepts only
the padded two-byte ID 31 and ID 36 replies from that endpoint. IDs 29, 33, and
37 remain on RakPeer's normal packet-producer/reliability path, avoiding a
duplicate synthetic status.

The same one-slot fixture was repeated after the adapter change:

```bash
build-host/samp_raknet_headless_probe \
  --host 127.0.0.1 \
  --port 7807 \
  --name AdapterRejected \
  --duration-ms 3000 \
  --expect-packet 31 \
  --adapter-terminal
```

Observed:

```json
{"probe":"AdapterRejected","host":"127.0.0.1","port":7807,"duration_ms":3000,"drained":1,"ever_connected":0,"auth_sent":0,"adapter_terminal_mode":1,"unexpected_packet":-1,"packet_counts":{"31":1},"direct_packet_counts":{"26":1,"31":1},"expected_packet":31,"expected_seen":1}
```

This proves ID 31 now reaches the adapter's existing `out_last_packet_id`
status surface. The already-present runtime switch handles ID 31 as
`WAIT_CONNECT`, but the exact visible text and retry cadence remain
`TODO_VERIFY` until the same scenario is recorded with original R5 and
replacement GUI clients.

## Wrong-password receive-path result

A separate server used `password=CorrectSecret`; the probe supplied
`WrongSecret` and asserted packet 37:

```json
{"probe":"WrongPasswordProbe","host":"127.0.0.1","port":7807,"duration_ms":4000,"drained":1,"ever_connected":0,"auth_sent":0,"adapter_terminal_mode":0,"unexpected_packet":-1,"packet_counts":{"37":1},"direct_packet_counts":{"25":1,"26":1},"expected_packet":37,"expected_seen":1}
```

Thus ID 37 is already a regular `RakClient::Receive` packet and is intentionally
not mirrored by the direct-offline observer. Exact original/replacement
password-field and chat behavior still require the GUI A/B scenario.

The post-change JSON records and corresponding open.mp logs are stored in
`artifacts/runs/20260727-network-adversity-headless/`.

## Unit coverage

`python3 -m unittest -v tools.reloop.test_udp_impairment_proxy` passes five
checks:

1. second-loopback forwarding in both directions;
2. deterministic total client-to-server loss;
3. direction-specific server-to-client loss;
4. seeded, observable `second`-before-`first` reordering;
5. one-client enforcement and foreign-client accounting.

Related host checks also pass:

```text
build-host/test_samp_client_transport
build-host/test_raknet_split_reassembly
build-host/test_raknet_offline_status_delivery
```

The last target binds an ephemeral localhost UDP socket and checks that ID 29
uses the normal producer path while one injected ID 31 reply and one injected
ID 36 reply are surfaced through the adapter status sidecar. Its filter checks
still run when localhost sockets are unavailable; only the live delivery
portion is then skipped.

The next parity step is a GUI A/B run that records the original R5 and
replacement message/cadence for packets 29, 31, 33, 36, and 37, followed by a
longer connected sync stream through the seeded proxy to inspect ACK/resend
counters rather than handshake recovery alone.
