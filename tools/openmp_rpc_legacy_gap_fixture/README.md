# Closed R5 legacy RPC-gap fixture

This isolated open.mp component sends 14 fixed vectors covering the eight
legacy inbound registrations found missing from the replacement inventory:
RPCs 48, 92, 98, 111, 125, 150, 167 and 169.

The exact full-burst command is `/rpclegacyraw`. It accepts no arguments, is
one-shot per connection, requires a 0.3.7 client over Legacy RakNet and sends
only compiled payloads on `OrderingChannel_SyncRPC` with outgoing event
dispatch disabled. Do not install it on a public server.

Two additional argument-free commands isolate the snapshot transitions:

- `/rpclegacydrunkon` sends fixed level 2500 through RPCs 92 and 150;
- `/rpclegacydrunkoff` restores fixed level 0 through RPCs 92 and 150.

Always send the off command after the on command. These commands exist because
the full burst can be consumed as one snapshot and expose only its final safe
value.

Every stateful pair is restored immediately: world 1/0, drunk visual 2500/0,
vehicle-0 whole tire mask 1/0, widescreen 1/0, drunk handling 2500/0 and remote
vehicle collision disable 1/0. RPC 125 has zero payload bits. RPC 169 sets
actor 0 invulnerable, matching the one-way R5 handler; it has no false
payload. A missing vehicle 0 or actor 0 exercises the original handler's
bounded pool-resolution return but cannot demonstrate the physical effect.

Evidence: `STATIC_037`, R5 SHA256
`b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`.
Handler RVAs and the registration inventory are documented in
[`../../docs/re/parity_sync_rpc_reloop_20260726.md`](../../docs/re/parity_sync_rpc_reloop_20260726.md).

Build with:

```sh
tools/openmp_rpc_legacy_gap_fixture/build.sh
```

The script verifies an ELF32 i386 component and prints its SHA256. Copy the
result into an isolated server's `components` directory and restart that
server before use.
