# RPC 48, RPC 98, and RPC 167 runtime parity

Reference DLL:

- SA-MP 0.3.7-R5 `samp.dll`
- SHA256 `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`

## RPC 48 — SetPlayerVirtualWorld

`STATIC_037`: the registered handler at `samp.dll+0x1DCC0` reads one signed
32-bit virtual-world value. It resolves the local player and calls the setter
at `samp.dll+0x17D10`.

The setter only changes state when the new world differs:

- `CLocalPlayer+0x217` receives the new signed 32-bit world;
- `CLocalPlayer+0x220` is cleared;
- `CLocalPlayer+0x221` is cleared.

The flag identities are corroborated by their R5 consumers:

- `samp.dll+0xD920` tests `+0x220` before active-player processing and sets it
  after the local death path. This is the local wasted/death latch.
- `samp.dll+0xB60E` chooses active-player processing only while `+0x221` is
  clear. `samp.dll+0xE570` and the class-selection RPC path set it. This is the
  wants-another-class latch.

There is no direct GTA streaming call in the RPC 48 handler or setter.
Compatibility code must therefore preserve the state transition and let the
normal player/object/vehicle stream RPCs drive entity membership.

Replacement mapping:

- the adapter retains the signed value plus a monotonic sequence;
- only a changed value clears its class-selection-after-death request state;
- the game-thread consumer mirrors that transition into the replacement's
  local death and F4/class-selection latches;
- no speculative GTA streaming or entity mutation is performed.

## RPC 98 — SetVehicleTireStatus

`STATIC_037`: the handler at `samp.dll+0x18B70` reads a 16-bit vehicle ID and
one 8-bit damage mask, resolves the streamed vehicle, and calls the setter at
`samp.dll+0xB7940`.

The setter recognizes only exact automobile and bike subtypes. Its mask order
is reversed relative to ascending field addresses:

- automobile bits `0..3` write bytes `+0x5A8, +0x5A7, +0x5A6, +0x5A5`;
- bike bits `0..1` write bytes `+0x65D, +0x65C`.

Other vehicle subtypes are intentionally unchanged. A zero mask writes zeroes,
so damage from an earlier update cannot remain stale. The replacement stores
the mask in the vehicle slot for both immediate updates and later stream-in.

## RPC 167 — DisableRemoteVehicleCollisions

`STATIC_037`: the handler at `samp.dll+0x17DE0` reads one bit and stores it in
`CNetGame+0x232`.

R5 installs the following guarded GTA hooks:

- the call at GTA `0x41AF80`, whose stock target is
  `CCollision::CheckCameraCollisionVehicles` at `0x41A990`;
- vehicle `ProcessEntityCollision` vtable entries for automobile, helicopter,
  plane, quad, bike, BMX, monster truck, and boat.

When the flag is enabled, the camera wrapper returns false without calling the
stock camera/vehicle collision test. The entity wrappers return zero only when
the other entity is a vehicle model in the inclusive `400..611` range and both
physical entities have a non-null collision-list pointer at `+0x460`.
All other calls retain their exact stock target.

The replacement hook is restricted to the validated GTA SA 1.0 US executable,
checks each original call/vtable target before writing, and restores only
entries which still point at the replacement wrapper.

RPC state is reset on GMX, reconnect, and connection loss. The guarded hooks
remain installed but transparent while the flag is clear, matching their
process-lifetime role; their original call displacement and vtable entries are
restored during normal DLL shutdown/rollback.

## Remaining runtime proof

- `TODO_VERIFY`: exercise RPC 48 during alive, wasted, and F4 class-selection
  states and compare subsequent RPC 52/53/class-request ordering.
- `TODO_VERIFY`: compare two occupied vehicles plus a camera-near-vehicle case
  with RPC 167 disabled/enabled.
- `TODO_VERIFY`: exercise RPC 98 masks `0x00`, every single bit, and the full
  mask on one automobile and one bike while observing both clients.
- `TODO_VERIFY`: verify the RPC 167 state clears after GMX/disconnect while
  the transparent hooks stay installed, and verify every hook is restored on
  normal DLL shutdown.
