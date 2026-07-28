# SA-MP 0.3.7-R5 custom ModelInfo static map

Date: 2026-07-28

## Scope and binary identity

This note isolates the original R5 custom-object, ModelInfo, and downloadable
model support. It does not describe the replacement implementation as proof of
R5 behavior and it does not enable any runtime patch.

Evidence binaries:

| Binary | SHA-256 | Ghidra MD5 |
|---|---|---|
| original `samp.dll` (0.3.7-R5) | `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2` | `5ba5f0be7af99dfd03fb39e88a970a2b` |
| GTA SA US 1.0 executable used by the reference prefix | `a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26` | `170b3a9108687b26da2d8901c6948a18` |

All SA-MP addresses below are RVAs. GTA addresses are VAs for the exact
executable hash above.

## Main correction

`STATIC_037`: R5 reserves **20,000** `CAtomicModelInfo` objects. The previously
observed value **15,417 is the populated count**, not the capacity.

`OBSERVED_037 + PROBE_TRACE`: the original startup run moved the GTA
`CAtomicModelInfo` count at `0x00AAE950` from 13,984 to 15,417 while registering
the 1,433 `objs` rows from the stock `SAMP.ide`.

The original architecture has three distinct pieces:

1. A 20,000-entry positive-ID `CAtomicModelInfo` arena used by the normal GTA
   ModelInfo registration path.
2. A 65,535-entry relocated `CModelInfo::ms_modelInfoPtrs` arena whose origin is
   centred to support signed IDs.
3. Heap-cloned ModelInfos and per-file TXD/DFF/COL loading for downloadable
   models. This is separate from the built-in positive-ID `SAMP.ide` catalog.

## Initialization order

`STATIC_037`:

1. `samp.dll+0xC3AB9` calls `samp.dll+0xA08E0`.
2. `samp.dll+0xA08E0` first calls the pre-game patch installer at
   `samp.dll+0xAAEB0`.
3. The relevant order inside `samp.dll+0xAAEB0` is:
   - `samp.dll+0xAAA80`
   - `samp.dll+0xAA9C0`
   - `samp.dll+0xAAD60`
   - `samp.dll+0xAAA10`
   - `samp.dll+0xAA590`
4. Later, custom-model manager initialization at `samp.dll+0xBD60`, guarded by
   byte field `this+0x8`, calls:
   - `samp.dll+0xA7A00` to relocate `ms_modelInfoPtrs`;
   - `samp.dll+0xA7D90` to install the custom COL callback.

`STATIC_037`: `samp.dll+0xAAA80` is not a ModelInfo or TXD store. It clears
20,000 eight-byte entries at `samp.dll+0x1A2618` and redirects GTA world-sector
linked-list operands formerly based at `0x00B7D0B8`. It must not be cited as
evidence for custom-model streaming.

## Static storage layout

All four regions below are inside the writable `.data` virtual block of
`samp.dll`; none is heap-allocated.

| Purpose | Start RVA | End RVA, exclusive | Count / stride |
|---|---:|---:|---:|
| relocated ModelInfo pointer storage | `+0x1625B0` | `+0x1A25AC` | 65,535 / `0x4` |
| world-sector store, not ModelInfo | `+0x1A2618` | `+0x1C9718` | 20,000 / `0x8` |
| `CPedModelInfo` store | `+0x1C9718` | `+0x1CEBD4` | 319 / `0x44` |
| `CAtomicModelInfo` store | `+0x1CEBD8` | `+0x26AFD8` | 20,000 / `0x20` |

Related globals:

| RVA | Meaning |
|---:|---|
| `+0x114B08` | holds effective pointer-array origin VA `samp.dll+0x1825AC` |
| `+0x1A25AC` | relocation-active flag, set to 1 by `+0xA7970` |
| `+0x1A25B0` | current destination model ID used by the custom atomic/COL path |

The effective pointer origin is exactly 32,767 DWORDs after the storage base:

```text
storage index 0       -> signed model ID -32767
storage index 32767   -> signed model ID 0
storage index 65534   -> signed model ID +32767
```

The physical arena therefore permits `-32767..+32767`. The post-relocation
accessor itself performs no range check, so callers still have to preserve this
invariant.

## AtomicModelInfo store relocation

Initializer: `samp.dll+0xAAA10`.

`STATIC_037`:

- It iterates exactly 20,000 times.
- Each `0x20`-byte entry gets GTA vtable `0x0085BBF0` at offset zero.
- The remaining seven DWORDs are cleared.
- The working pointer starts at `samp.dll+0x1CEBDC` and terminates when it
  reaches `samp.dll+0x26AFDC`; the object region itself ends at
  `samp.dll+0x26AFD8`.
- It then makes 14 GTA operand DWORDs writable and replaces
  `0x00AAE954`, the old first-object address, with
  `samp.dll+0x1CEBD8`.
- It does **not** relocate or overwrite the count at `0x00AAE950`.
- It does not call the GTA constructor. Construction is the direct vtable plus
  zero-fill sequence above.

The exact operand addresses are:

```text
0x004C63F2
0x004C662D
0x004C6822
0x004C6829
0x004C6877
0x004C6881
0x004C6890
0x004C68A5
0x004C68F3
0x004C6932
0x004C6971
0x004C69B0
0x004C69EF
0x004C6A2E
```

`STATIC_037`: R5 itself does not guard these 14 writes beyond choosing its GTA
version path. On the exact US 1.0 executable hash above, Ghidra verified all 14
operand DWORDs are `0x00AAE954` before the patch.

This differs materially from the current replacement's dormant OLA-derived
35-site recipe. The 14 sites above are the complete R5 list. The other 21 sites
in that recipe, including `0x4C63E1`, `0x4C6621`, and `0x4C68AC`, are not
patched by R5 and must not be treated as `STATIC_037` evidence. A raw
little-endian address scan of the R5 image found every one of the 14 listed
targets exactly once and each of those 21 extra targets zero times.

## `ms_modelInfoPtrs` relocation

Initializer: `samp.dll+0xA7A00`.

`STATIC_037`:

1. Clear 65,535 DWORDs starting at `samp.dll+0x1625B0`.
2. Copy exactly 20,000 DWORDs from GTA `0x00A9B0C8` to the effective origin
   held at `samp.dll+0x114B08`.
3. Call patch engine `samp.dll+0xA7970`.
4. Install the negative-ID guard through `samp.dll+0xA6FF0`.

### Patch engine

`samp.dll+0xA7970` consumes 707 packed five-byte records:

| Executable variant | Table RVA | Records |
|---|---:|---:|
| build flag 1 / exact US 1.0 reference | `+0x114B10` | 707 |
| build flag 2 | `+0x1158E0` | 707 |

Each record contains:

```text
DWORD GTA instruction VA
BYTE  expected opcode
```

R5 first compares the live opcode. A match produces one four-byte operand
write:

| Opcode | Operand offset |
|---:|---:|
| `8B`, `89`, `39` | instruction `+3` |
| `BE`, `BF` | instruction `+1` |

After the loop, `samp.dll+0x1A25AC` is set to one.

`STATIC_037`: an opcode mismatch only skips that individual write. R5 still
sets the relocation-active flag and returns success after the loop; it does not
count matches or roll back a partial patch. A replacement should validate the
entire set before performing its first write.

`STATIC_037`, corroborated against the exact GTA executable:

- all 707 US1 opcodes match;
- all 707 original operands equal `0x00A9B0C8`;
- opcode distribution is 692 × `8B`, 10 × `89`, 2 × `BE`, 2 × `BF`,
  and 1 × `39`;
- 679 sites are in the primary `.text` section and 28 are in the
  `.HOODLUM` section;
- target range is `0x0040122A..0x0157045D`.

R5's runtime guard is only the one-byte opcode. A safe replacement should also
require the exact GTA hash or the complete expected instruction/operand bytes,
restore page protection, and flush the instruction cache.

`STATIC_037`: R5's write helper at `samp.dll+0xAA4C0` changes each target range
to `PAGE_EXECUTE_READWRITE` (`0x40`) and discards the previous protection
without restoring it.

### Accessor behavior

Accessor: `samp.dll+0xA7A40`.

- Before relocation: negative IDs and IDs greater than 20,000 return null;
  IDs `0..20000` inclusive index the vanilla table. The inclusive upper bound
  is what the binary implements even though only 20,000 entries are copied.
- After relocation: the accessor directly returns
  `origin[signed_model_id]`, without a bounds check.

### Negative-ID guard

`samp.dll+0xA6FF0` replaces the six bytes at GTA `0x004087EA`
(`56 57 8D 7C AD 00`) with a detour to `samp.dll+0xA5E90`.

`STATIC_037`: the trampoline returns early when signed model ID register `EBP`
is negative. Otherwise it replays `push esi; push edi; lea edi,[ebp+ebp*4]`
and resumes at GTA `0x004087F0`.

## Ped and TXD support paired with the model expansion

### Ped ModelInfos

`samp.dll+0xAA9C0` creates 319 static `0x44`-byte `CPedModelInfo` entries at
`samp.dll+0x1C9718`, using vtable `0x0085BDC0`, and replaces the operand DWORD
at GTA `0x004C67AD`:

```text
old: 0x00B478FC
new: samp.dll+0x1C9718
```

The exact GTA operand guard was verified.

### TXD capacity

`samp.dll+0xAA590` is a broad pre-game limit patch group. One directly relevant
write changes the immediate operand at GTA `0x00731F60` from 5,000
(`0x1388`) to 20,000 (`0x4E20`) in the CTxdStore initialization path. The
exact four-byte operand was verified.

`STATIC_037`: the write of `0x4E20` at GTA `0x0055105F` is a separate GTA pool
limit in the same broad patch group and is not evidence for ModelInfo pointer
capacity.

## Downloadable model registration

These helpers operate on the relocated signed pointer table. They are distinct
from the startup `SAMP.ide` positive-ID population.

### Cloning

`samp.dll+0xA7A80`:

- allocates a zeroed `0x44`-byte block;
- resolves the source ID through `+0xA7A40`;
- validates through `samp.dll+0xB3DD0` and accepts source IDs `0..30000`
  whose ModelInfo vtable is `0x0085BDC0`;
- copies 17 DWORDs and installs the clone in the destination pointer slot;
- does not first test whether the destination slot is already populated.

`samp.dll+0xA7AD0`:

- first returns an existing destination slot unchanged;
- otherwise allocates a zeroed `0x20`-byte block;
- resolves and validates the source ModelInfo;
- validates through `samp.dll+0xB44E0` and accepts five atomic-family vtables:
  `0x0085BBF0`, `0x0085BC30`, `0x0085BC70`, `0x0085BCB0`,
  `0x0085BCF0`;
- copies eight DWORDs and installs the clone in the destination pointer slot.

`samp.dll+0xA7B30` frees the pointer in a signed model slot and writes null back
to the slot. No direct call or address reference to this helper was found in
the R5 image, so its actual lifecycle use remains `TODO_VERIFY`.

`STATIC_037`: both clone helpers allocate before source validation. Their
failure branches neither free that allocation nor check the allocator result
before a successful copy. The ped helper can also replace a non-null
destination without freeing it. These are original failure-path semantics, not
safe implementation guidance: the replacement must retain allocation checks
and should not intentionally reproduce a leak.

### TXD, DFF, and COL

`samp.dll+0xA7B60`:

1. finds a TXD slot by name through `+0xB3880` / GTA `0x731850`;
2. if absent, adds the slot through `+0xB38A0` / GTA `0x731C80`,
   verifies the TXD file, and loads it through `+0xB38C0` /
   GTA `0x7320B0`;
3. writes the TXD index to ModelInfo offset `+0xA` through
   `samp.dll+0xB4660`;
4. calls the wrappers for `PushCurrentTxd` and `SetCurrentTxd`.

The helper does not itself call the `AddRef` wrapper at `samp.dll+0xB38F0`.
The exact ref-count ownership across the subsequent GTA model loader is
therefore still `TODO_VERIFY`.

`STATIC_037`: an already named TXD slot is bound directly, without reloading
the file. For a new name, the slot is added before file validation; validation
failure returns false without removing that new slot. The return value of the
subsequent TXD-load wrapper is not tested.

`samp.dll+0xA7BD0` clones a ped ModelInfo, binds/loads its TXD, loads the DFF,
and installs the resulting clump.

`samp.dll+0xA7C30` clones an atomic-family ModelInfo, stores the destination ID
at `samp.dll+0x1A25B0`, binds/loads its TXD, loads the DFF, and installs the
resulting atomic.

`samp.dll+0xA7CC0`:

- rejects a COL buffer larger than `0x40000` bytes;
- requires `COL3`;
- loads the collision object and associates it with the destination ID held at
  `samp.dll+0x1A25B0`.

The COL callback is registered by `samp.dll+0xA7D90`.

The high-level file paths are constructed by:

- `samp.dll+0xC650` for downloadable ped models;
- `samp.dll+0xC770` for downloadable atomic models.

Both use `%s\0x%X.dff` and `%s\0x%X.txd` cache paths and then call the helpers
above.

## Ownership and cleanup

`STATIC_037`:

- The relocated pointer array, positive-ID AtomicModelInfo store, and ped
  ModelInfo store are process-lifetime `samp.dll` storage.
- No reverse write restoring the 707 `ms_modelInfoPtrs` operands, the 14
  AtomicModelInfo operands, or the ped-store operand was found.
- No global-store teardown was identified.
- `samp.dll+0xD1E0` is a release tick over custom-model records. When its two
  activity bytes are set and the countdown at record `+0x5A` reaches zero, it
  calls `samp.dll+0xB2040`.
- `samp.dll+0xB2040` resolves the ModelInfo, remembers its TXD index, calls GTA
  `0x004C4D50` on the ModelInfo, queries the TXD reference count through the
  wrapper for GTA `0x731AA0`, and, when it reaches zero, calls the wrappers for
  GTA `0x731E90` and `0x731CD0`.
- That path shuts down the GTA-side model/TXD resources, but it does not call
  `samp.dll+0xA7B30` and does not clear the relocated ModelInfo pointer slot.
- The ped/atomic high-level loaders likewise return false after TXD or DFF
  failure without calling `+0xA7B30`; a clone already installed in the pointer
  slot remains installed.

`TODO_VERIFY`: whether another indirect path frees cloned ModelInfos, whether a
GMX retains or recreates them, and whether DLL unload restores code operands
must be established dynamically. Static evidence is insufficient to claim any
of those behaviors.

## Consequences for the replacement

1. Do not enable the current 35-site native AtomicModelInfo relocation as an R5
   parity implementation. Its extra 21 sites are not in the original patch.
   Its heap allocation and per-entry GTA-constructor calls also differ from
   R5's process-lifetime static arena and direct vtable-plus-zero
   initialization.
2. Treat the following as one initialization unit:
   - 20,000-entry AtomicModelInfo store;
   - exact 14 store-base operands;
   - 65,535-slot signed pointer arena;
   - exact 707 opcode-guarded pointer operands;
   - negative-ID guard;
   - 319-entry ped store;
   - 20,000-slot TXD capacity.
3. Preserve `0x00AAE950` as the live AtomicModelInfo count. Capacity 20,000 and
   observed populated count 15,417 are not interchangeable.
4. Keep all over-vanilla registration disabled unless every byte guard for the
   exact GTA build passes before any write. Partial patch application is unsafe.
5. Do not use `samp.dll+0xAAA80` or its 20,000-entry world-sector store as a
   ModelInfo/TXD implementation clue.

## Reproducible Ghidra export

The focused exporter is
`tools/ghidra/InspectCustomModelInfo.java`. It emits only bounded instruction,
reference, scalar, region, patch-record, string, and guard metadata; it does
not emit decompiler pseudocode.

Local generated output:

```text
analysis/generated/ghidra_custom_modelinfo_20260728/samp/
analysis/generated/ghidra_custom_modelinfo_20260728/gta_us1/
```

The generated directory is intentionally ignored. Important artifact checks:

```text
patch_tables.tsv:
  SHA-256 a98179152fb95c042ede3bbb9dbbc2e600f11ef8b33bc717d1035ee865452dfd
  707 US1 pointer records + 707 variant-2 records + 14 atomic operands

gta_patch_guards.tsv:
  SHA-256 ff00f9cbafa71e78695b265c6e8a8915d7e3ae9bdd4862233dfca6745639e759
  707/707 US1 pointer opcode and operand matches
  14/14 AtomicModelInfo operand matches

gta_fixed_guards.tsv:
  SHA-256 2f6e32d9e9628b3748125c261517ed9c55d391e08232375da90bfdd2edb20979
  negative-ID hook, ped-store operand, and TXD-capacity operand all match
```

The variant-2 table is `STATIC_037` from the R5 DLL but was not validated
against a matching variant-2 GTA executable in this pass.

## Next safe live probe

Run a passive, read-only original-R5 Windows probe on the exact hashes above:

1. At entry and return of `samp.dll+0xAAA10`, record:
   - all 14 live operand DWORDs;
   - AtomicModelInfo slots 0, 13,983, 13,984, 15,416, and 19,999;
   - count `0x00AAE950`.
2. At entry and return of `samp.dll+0xA7A00`, record:
   - all 707 patched operands;
   - relocation flag `samp.dll+0x1A25AC`;
   - pointer slots for IDs `-32767`, `-1`, `0`, `13983`, `13984`,
     `15416`, `15417`, `19999`, and `32767`.
3. Break/log, without modifying behavior, at GTA `0x004C6620` while
   `SAMP.ide` is registered. For each call, record the requested model ID,
   count before/after, returned pointer, pointer-table slot, TXD index, and
   streaming entry. Confirm:
   `returned == atomic_store_base + count_before * 0x20`.
4. Exercise one downloadable negative atomic model and log
   `+0xA7AD0`, `+0xA7B60`, `+0xA7C30`, the COL callback, `+0xD1E0`, and
   `+0xB2040`, including TXD ref counts and the destination pointer slot before
   and after release.
5. Take the same snapshots after disconnect, GMX, reconnect, and normal process
   detach. This resolves the remaining ownership question without speculative
   writes or forced unloading.

No live probe or replacement deployment was performed as part of this static
analysis pass.
