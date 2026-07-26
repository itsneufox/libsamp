# Sync, vehicle and RPC parity re-loop, 2026-07-26

## Identity and scope

This pass compared and extended the replacement against:

- SA-MP 0.3.7-R5 `samp.dll`, SHA256
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`;
- GTA San Andreas US 1.0 `gta_sa.exe`, SHA256
  `a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26`;
- the local open.mp server at `192.168.3.181:7798`;
- an original R5 pilot and the native-Windows replacement observer.

All original-DLL addresses below are RVAs. The original binary is not stored
with these generated text reports.

## Inverted remote heading

The reported left/right inversion was a real decoder defect. SA-MP's outgoing
GTA Z quaternion uses:

```text
w = cos(yaw / 2)
z = -sin(yaw / 2)
```

The replacement decoded it with the ordinary positive-Z convention. That
mirrored remote on-foot yaw, so an original player turning left appeared to
turn right on the replacement observer.

The shared conversion now uses the GTA/SA-MP sign for both remote on-foot
packet 207 and remote vehicle packet 200. A standalone test covers cardinal
headings, wraparound and the observed near-zero sample. The original pilot
sample near `355.5325` degrees decoded as `355.533` degrees after the fix.

Evidence: `OBSERVED_037 + PROBE_TRACE + OPENMP_REF`.

## Compressed-vector tail alignment

The server-to-client packet 207/200 decoders also had a low-speed edge
misalignment. open.mp writes only the magnitude when it is at or below
`1e-5`; the generic RakNet reader used by the replacement attempted to read
the normalized direction for every nonzero magnitude. A tiny speed therefore
consumed following fields as vector data.

The replacement now has an open.mp-compatible bounded vector reader. Host
tests cover zero, epsilon, ordinary and truncated inputs. Five consecutive
normal-car Windows runs completed without a vehicle/on-foot decode failure.

Evidence: `OPENMP_REF + PROBE_TRACE`.

## Remote vehicle ProcessControl

Static R5 analysis found the vehicle-side context wrapper and installer:

- remote vehicle wrapper: `samp.dll+0xA3100`;
- installer: `samp.dll+0xA645B`;
- ten GTA vehicle vtables have entry index 10 redirected through that wrapper.

The replacement added a byte- and GTA-hash-guarded equivalent context hook.
Normal-car and Rustler routes completed without exceptions and retained
remote motion/control. Exact R5 post-call matrix, velocity and per-class
repair behavior is still `TODO_VERIFY`; this pass does not claim full vehicle
physics parity.

Evidence: `STATIC_037 + PROBE_TRACE + TODO_VERIFY`.

## Complete R5 inbound-registration inventory

`InspectRpcRegistration60.java` analyzed the R5 registration routine
`samp.dll+0x1E130..+0x1E784`. It recovered 95 registration pairs. Comparing
that set with the replacement metadata found eight missing legacy entries:

| RPC | R5 handler | Recovered behavior | Replacement state |
| ---: | ---: | --- | --- |
| 48 | `+0x1DCC0` | player virtual world, `int32` | bounded decode/log; exact restream side effects open |
| 92 | `+0x18C50` | drunk visual level, `uint32`, GTA 052C | implemented and live tested at 2500/0 |
| 98 | `+0x18B70` | vehicle ID + whole tire mask | bounded decode/log |
| 111 | `+0x18AC0` | widescreen toggle byte, GTA 02A3 | implemented and live tested |
| 125 | `+0x180C0` | registered exact no-op | registered no-op |
| 150 | `+0x18D00` | drunk handling level, `uint32`, GTA 03FD | implemented and live tested at 2500/0 |
| 167 | `+0x17DE0` | one-bit remote-vehicle collision disable | bounded decode/log |
| 169 | `+0x1C170` | actor ID; set actor invulnerable | implemented through actor state |

RPC 169 now queues an ordered actor event, updates authoritative actor state,
and reaches the existing physical invulnerability application. As in R5, its
payload can only set the flag to true; a later authoritative actor state can
resynchronize it.

The same inventory proves that RPC 60 has zero registration pairs in R5.
Consequently it is intentionally classified as a local ignored legacy ID
rather than as an unimplemented original handler.

Evidence: `STATIC_037`; open.mp and 0.2x names are semantic cross-references,
not the proof of registration.

Generated reports:

- `analysis/generated/ghidra_rpc60_20260726/identity.tsv`;
- `analysis/generated/ghidra_rpc60_20260726/registration_pairs.tsv`;
- `analysis/generated/ghidra_rpc60_20260726/instructions.tsv`;
- `analysis/generated/ghidra_rpc60_20260726/summary.tsv`.

The headless analysis was run with:

```sh
JAVA_HOME=/home/chairman/Projects/sa-mp.dll-rebuild/tools/ghidra/jdk-21.0.11+10 \
XDG_CONFIG_HOME=/tmp/ghidra-config-rpc60 \
XDG_CACHE_HOME=/tmp/ghidra-cache-rpc60 \
/home/chairman/Projects/sa-mp.dll-rebuild/tools/ghidra/ghidra_12.1.2_PUBLIC/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
  /tmp/ghidra-rpc60-clean rpc60-r5-clean \
  -import samp.dll \
  -scriptPath /home/chairman/Projects/sa-mp.dll-rebuild/tools/ghidra \
  -postScript InspectRpcRegistration60.java \
    /home/chairman/Projects/sa-mp.dll-rebuild/analysis/generated/ghidra_rpc60_20260726 \
  -deleteProject
```

The exact local Ghidra installation path may differ; the generated identity
file, binary hash and RVA range are authoritative for this run.

## RPC 111 Windows validation

Replacement DLL SHA256
`4deebb0bfcf8276ab631cc17d82aee9a66b3bcdcba67755a5df7e911edcad86d`
was tested in Windows run
`20260726_173209_rpc-inventory-widescreen_cfb94391`.

The fixed UI fixture sent enable and disable:

1. inbound RPC 111, eight bits, payload `01`;
2. snapshot sequence 1, enabled 1;
3. GTA opcode 02A3 application succeeded;
4. inbound RPC 111, eight bits, payload `00`;
5. snapshot sequence 2, enabled 0;
6. GTA opcode 02A3 application succeeded.

The server fixture finished with one pass, zero failures and six visual
observations. The run produced no decode failure, exception event or dump,
and both processes were responsive at collection. Twelve screenshots and all
isolated client logs are retained under:

`artifacts/windows-runs/20260726_173209_rpc-inventory-widescreen_cfb94391/`

This is `STATIC_037 + PROBE_TRACE`. A pixel-matched R5 widescreen A/B remains
open.

## Closed original/replacement legacy-gap probe

`tools/openmp_rpc_legacy_gap_fixture/` sends 14 compiled, argument-free
vectors for RPCs 48, 92, 98, 111, 125, 150, 167 and 169. Stateful vectors
are paired with a safe restoring value. The server reported all 14 sends as
successful in both runs.

The original R5 pilot received the same burst through `/rpclegacyraw` and
remained spawned, connected and responsive. This is direct
`OBSERVED_037 + PROBE_TRACE` evidence for safe receipt of the exact payload
set; the original ASI does not yet expose decoded per-handler state.

The replacement Windows run
`20260726_180237_rpc-legacy-gap-applied_4560b378`, DLL SHA256
`7710e90aaeca7d6f96ce6b783bf90e7f37d7abcc8b0a1dbae8e4063a396d359f`,
received exactly:

- RPC 48 twice;
- RPC 92 twice;
- RPC 98 twice;
- RPC 111 twice;
- RPC 125 once;
- RPC 150 twice;
- RPC 167 twice;
- RPC 169 once.

All payloads decoded without an exception, event gap, decode failure,
disconnect or dump. RPC 169 returned through its bounded inactive-actor path
because actor 0 was not active in that client. Both Windows processes were
responsive at collection.

The all-in-one burst intentionally sends nonzero then zero, so its snapshot
consumer can coalesce to the safe final value. Two further fixed commands
split that transition. Windows run
`20260726_180709_rpc-legacy-drunk-transition_fbe97418` observed and applied:

1. RPC 92, level 2500, GTA 052C: `applied=1`;
2. RPC 150, level 2500, GTA 03FD: `applied=1`;
3. RPC 92, level 0 cleanup: `applied=1`;
4. RPC 150, level 0 cleanup: `applied=1`.

The client remained connected and both processes remained responsive, with
no dump or exception/decode-failure marker. This closes the replacement
execution-path gap for RPCs 92 and 150. Pixel- or memory-level equivalence of
the resulting GTA effects against R5 remains `TODO_VERIFY`.

Evidence: `STATIC_037 + OBSERVED_037 + PROBE_TRACE`.

## Deeper legacy-handler static report

`InspectLegacyRpcGapHandlers.java` exports bounded instructions for all eight
handlers. Ghidra's default analysis incorrectly marks RPC 167 as only its
first six-byte instruction; `InspectRpc167Linear.java` therefore also exports
that registered entry linearly, bounded to 128 instructions and the first
`RET`.

Generated reports are under:

`analysis/generated/ghidra_legacy_rpc_gap_20260726/`

They confirm:

- RPC 48 reads 32 bits and updates R5's local-player world/restream state;
- RPC 92 dispatches GTA opcode 052C;
- RPC 98 reads exactly 24 bits (`uint16` vehicle ID plus one `uint8` whole
  tire mask), checks the vehicle ID below 2000, resolves the vehicle pool and
  calls `samp.dll+0xB7940`;
- RPC 111 dispatches GTA opcode 02A3;
- RPC 125 is an exact one-byte `RET`;
- RPC 150 dispatches GTA opcode 03FD;
- RPC 167 reads one bit and stores it in the netgame collision flag at
  `+0x232`;
- RPC 169 resolves the actor and sets invulnerability.

Evidence: `STATIC_037`, original R5 SHA256
`b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`.

### RPC 98 tire-mask mapping

`InspectVehicleTireStatus.java` and generated `rpc98_tire_method.tsv` recover
the complete R5 method at `samp.dll+0xB7940..+0xB7A27`. Its vehicle-subtype
branch writes Boolean wheel states directly:

- automobile subtype 1: mask bits 0, 1, 2 and 3 map respectively to GTA
  vehicle offsets `+0x5A8`, `+0x5A7`, `+0x5A6` and `+0x5A5`;
- bike subtype 2: mask bits 0 and 1 map respectively to offsets `+0x65D` and
  `+0x65C`;
- other subtypes return without a wheel write.

This supersedes the older 0.2x per-wheel RPC shape: the R5 wire byte is the
complete tire mask, not a tire ID or a separate status pair. The closed
fixture currently targets absent vehicle 0, so it proves bounded decoding and
return behavior but not the physical wheel transition. Applying these writes
is deliberately left `TODO_VERIFY` until the fixture supplies a known-active
automobile and bike and original/replacement memory observations can be
compared.

Evidence: `STATIC_037`, original R5 SHA256
`b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`.

## RPC 48 remaining limitation

The player-state fixture changed the replacement observer from virtual world
0 to 1 and restored it, but its isolated client trace contains no RPC 48.
open.mp performed the tested world transition through its current
server/streaming behavior rather than emitting the old direct legacy RPC.
The server-side pass therefore is not evidence that the replacement's RPC 48
handler ran.

The closed raw fixture now proves receipt and bounded decoding in R5 and the
replacement. The replacement does not yet reproduce R5's internal local
world/restream flag choreography, so RPC 48 remains
`STATIC_037 + PROBE_TRACE + TODO_VERIFY` for its GTA-side effect.

## Validation

- host build: passed;
- host CTest: 11/11 passed;
- Win32 build: passed;
- final Win32 SHA256 after implementing RPCs 92 and 150:
  `7710e90aaeca7d6f96ce6b783bf90e7f37d7abcc8b0a1dbae8e4063a396d359f`;
- final native-Windows smoke:
  `20260726_174154_rpc169-inventory-final_40dd2c4f`;
- the complete vehicle/player/PVar/UI/label fixture reported 11 passes, zero
  failures and 10 observations; RPC 111 again applied both transitions, both
  processes were responsive before stop, and the isolated logs contain no
  decode-failure, event-gap or exception marker;
- strict PE report: expected structural failures remain (entrypoint, section
  count/order, import set and TLS/EH sections); runtime ABI work is not yet
  byte-identical PE layout.

## Remaining priority gaps

1. Reproduce RPC 48's local world/restream flag choreography and apply RPC
   98's recovered mask mapping against known-active automobile and bike
   fixtures.
2. Apply and A/B the RPC 167 collision flag in a controlled remote-vehicle
   overlap scenario.
3. Exercise RPC 169 with actor 0 streamed and verify the physical immunity
   transition in both clients.
4. Recover and reproduce the exact vehicle ProcessControl post-call repair
   choreography.
5. Continue original/replacement combat A/B at identical viewport and
   sub-frame capture intervals; coarse aim-pose parity is not recoil/effect
   parity.
6. Apply the same 95-entry registration-set comparison as a build-time
   regression check so a known R5 registration cannot silently disappear.
