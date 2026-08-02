# RPC73 GameText replacement fixture

This deliberately narrow open.mp laboratory component sends two fixed raw
SA-MP RPC 73 (`ScrDisplayGameText`) payloads to one eligible test player:

1. style 5, duration 5000 ms, text `RPC73_STYLE5_FIRST`;
2. 350 ms later, style 3, duration 5000 ms, text
   `RPC73_STYLE3_SECOND`.

Enter exactly `/rpc73replace` to start the one-shot sequence. The command
accepts no arguments. Bots, non-0.3.7 clients, non-legacy transports,
uninitialised players, and repeated triggers on the same connection are
rejected.

This is not a general raw-RPC tool. The RPC ID, styles, durations, texts,
payload bytes, delay, ordering channel, and sequence are compiled in. Do not
install this fixture on a public or production server.

## Fixed payloads

RPC 73 serialises a little-endian `int32` style, `int32` display time,
`int32` byte length, and the raw text bytes.

| Phase | Style | Time | Length | Payload bytes |
| --- | ---: | ---: | ---: | --- |
| `first` | 5 | 5000 | 18 | `05 00 00 00 88 13 00 00 12 00 00 00 52 50 43 37 33 5f 53 54 59 4c 45 35 5f 46 49 52 53 54` |
| `replacement` | 3 | 5000 | 19 | `03 00 00 00 88 13 00 00 13 00 00 00 52 50 43 37 33 5f 53 54 59 4c 45 33 5f 53 45 43 4f 4e 44` |

Both calls use `OrderingChannel_SyncRPC` and `dispatchEvents=false`.
Consequently the component sends the raw RPC directly through LegacyNetwork;
open.mp outgoing hooks and the Fixes component's GameText-to-TextDraw path do
not rewrite the vectors.

## Evidence

`STATIC_037`: for original SA-MP 0.3.7-R5 DLL SHA256
`b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`,
RPC 73 starts at `samp.dll+0x198F0` and calls
`CGame::DisplayGameText` at `samp.dll+0xA0CE0` from
`samp.dll+0x199C8`. The accepted-message path executes GTA opcode
`0x00BE` (`text_clear_all`) through the descriptor at
`samp.dll+0xEC724` before it displays the new text. See
[`../../docs/re/scoreboard_gametext_render_semantics_r5_20260728.md`](../../docs/re/scoreboard_gametext_render_semantics_r5_20260728.md).

`OPENMP_REF`: the component targets local open.mp SDK commit
`3ee7bc4ab20c22359c34c08c38f93815b44bffd5`. Relevant API contracts:

- `SDK/include/player.hpp`: `PlayerTextEventHandler`,
  `PlayerConnectEventHandler`, `IPlayer::sendRPC`;
- `SDK/include/network.hpp`: the `Span<uint8_t>` length passed to `sendRPC`
  is a bit count;
- `SDK/include/Server/Components/Timers/timers.hpp`:
  `ITimersComponent::create` and `TimerTimeOutHandler`.

The matching local LegacyNetwork implementation creates a bitstream with the
exact supplied bit count and uses reliable-ordered delivery for
`OrderingChannel_SyncRPC`.

## Build

The local test server is an i386 ELF binary. Build with:

```sh
tools/openmp_rpc73_gametext_fixture/build.sh
```

The output is:

```text
tools/openmp_rpc73_gametext_fixture/build/rpc73_gametext_fixture.so
```

To select another local SDK checkout:

```sh
OMP_SDK_DIR=/home/chairman/Projects/LastBedStanding/deps/omp-sdk \
  tools/openmp_rpc73_gametext_fixture/build.sh
```

The build wrapper verifies that the result is an ELF32 i386 shared object and
prints its SHA256. It does not install or load the component.

## Controlled load and trigger

Stop the isolated test server, copy only this component, and restart:

```sh
cp tools/openmp_rpc73_gametext_fixture/build/rpc73_gametext_fixture.so \
  omp-server-bare/components/rpc73_gametext_fixture.so
cd omp-server-bare
./omp-server
```

The normal `Timers.so` component must be present. Connect the replacement
0.3.7 client and enter:

```text
/rpc73replace
```

The server log must contain one `phase=first` line and, about 350 ms later,
one `phase=replacement` line, both with `sent=1`. A matching replacement
client runtime trace should contain this transition:

```text
game_text: clear_all ... cleared=0 reason=replace_before_show
game_text: show ... style=5 ...
game_text: clear_all ... cleared=1 reason=replace_before_show
game_text: show ... style=3 ...
```

For the existing deterministic UI runner, the optional control-client trigger
can be enabled without changing the ordinary scenario:

```sh
SAMP_RELOOP_RPC73_REPLACE=1 \
  python3 tools/reloop/reloop.py run --client replacement --group ui \
    --delay 1000 --no-build --no-deploy --interaction
```

Reconnect before another run. To return the test server to its prior
component set, stop it and remove only
`omp-server-bare/components/rpc73_gametext_fixture.so`.
