# InitGame / PlayerInit Trace Note - 2026-06-10

## Result

`RPC 139` from the current open.mp bare run is an open.mp `PlayerInit`
layout, not the sequential 0.3.7 server layout used by the fallback decoder.

## Evidence

`PROBE_TRACE`:

* Prefix GTA run, `samp_net_trace.log`, 2026-06-10 00:22 CEST:
  `rpc-in id=139 name=ScrInitGame bits=2243 bytes=281 first=20 00 04 84 38 00 04 62 10 0c 00 00 00 01 00 80 80 00 00 06 05 37 89 01 9e 00 00 00 00 03 c0 00`
* The old decoder produced implausible state:
  `local_player=33796`, `tags=0`, `markers=0`, `nametag_dist=0.000`,
  bad gravity/send-rate values.

`OPENMP_REF`:

* `/home/chairman/Projects/omp-ipv6/open.mp/Shared/NetCode/core.hpp`
  `NetCode::RPC::PlayerInit` writes:
  zone/CJ/interior/chat flags, chat radius, stunt, name-tag distance,
  enter/LOS/manual-vehicle flags, spawn count, player id, name-tag flag,
  marker mode, time/weather/gravity, lan/death/instagib, rates, server name,
  vehicle models, vehicle-friendly-fire.

Manual decode of the current trace prefix with that layout gives:

* `spawns=12`
* `player=1`
* `tags=true`
* `markers=1`
* `time=12`
* `weather=10`
* `gravity=0.0080000004`
* `nametag_dist=70.0`

`STATIC_037`:

* Local 0.3.7 cross-check keeps the sequential fallback alive: the first
  fallback field is the NetGame spawn-count `int`, followed by player id and
  the classic InitGame flags.

## Expected Next Trace

After the decoder fix, the replacement DLL should log:

```text
rpc-state id=139 init_game layout=openmp spawns=12 local_player=1 tags=1 markers=1 ... gravity=0.008000 ... nametag_dist=70.000
```

The runtime line should then apply the same values instead of clamping/falling
back from shifted garbage.
