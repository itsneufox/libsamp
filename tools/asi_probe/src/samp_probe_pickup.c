#include "samp_probe_pickup.h"

#include <stdint.h>
#include <string.h>

#if defined(__GNUC__) && defined(__i386__)
#define PROBE_PICKUP_THISCALL __attribute__((thiscall))
#else
#define PROBE_PICKUP_THISCALL
#endif

/*
 * STATIC_037 + TODO_VERIFY:
 * The two methods, pool layout, process gate, and byte guards below come from
 * original SA-MP 0.3.7-R5
 * SHA256=b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2.
 * Hook-side code publishes only to a bounded ring. Runtime semantics remain
 * TODO_VERIFY until a controlled original run exercises each pickup type.
 * See docs/re/pickup_memory_probe_r5_20260728.md.
 */
#define PROBE_PICKUP_R5_TIMESTAMP 0x6372c39eu
#define PROBE_PICKUP_R5_ENTRY_RVA 0x000cbc90u
#define PROBE_PICKUP_R5_IMAGE_SIZE 0x0027e000u
#define PROBE_PICKUP_R5_PREFERRED_BASE 0x10000000u
#define PROBE_PICKUP_R5_SHA256                                             \
  "b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2"

#define PROBE_PICKUP_GTA_TIMESTAMP 0x427101cau
#define PROBE_PICKUP_GTA_ENTRY_RVA 0x00424570u
#define PROBE_PICKUP_GTA_IMAGE_SIZE 0x01177000u
#define PROBE_PICKUP_GTA_CHECKSUM 0x00dc5beau
#define PROBE_PICKUP_GTA_PREFERRED_BASE 0x00400000u
#define PROBE_PICKUP_GTA_SHA256                                            \
  "a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26"

#define PROBE_PICKUP_PICKED_UP_RVA 0x00013440u
#define PROBE_PICKUP_PROCESS_RVA 0x00013520u
#define PROBE_PICKUP_PROCESS_GATE_RVA 0x00118a10u
#define PROBE_PICKUP_NETGAME_PTR_RVA 0x0026eb94u
#define PROBE_PICKUP_NETGAME_POOLS_OFFSET 0x000003deu
#define PROBE_PICKUP_POOLS_PICKUP_OFFSET 0x00000008u

#define PROBE_PICKUP_COUNT_OFFSET 0x00000000u
#define PROBE_PICKUP_HANDLE_OFFSET 0x00000004u
#define PROBE_PICKUP_RAW_GTA_INDEX_OFFSET 0x00004004u
#define PROBE_PICKUP_TIMER_OFFSET 0x00008004u
#define PROBE_PICKUP_DROPPED_OFFSET 0x0000c004u
#define PROBE_PICKUP_DROPPED_STRIDE 3u
#define PROBE_PICKUP_DROPPED_PLAYER_OFFSET 1u
#define PROBE_PICKUP_DATA_OFFSET 0x0000f004u
#define PROBE_PICKUP_DATA_STRIDE 0x14u
#define PROBE_PICKUP_DATA_MODEL_OFFSET 0x00u
#define PROBE_PICKUP_DATA_TYPE_OFFSET 0x04u
#define PROBE_PICKUP_DATA_POS_OFFSET 0x08u
#define PROBE_PICKUP_CAPACITY 4096u

#define PROBE_PICKUP_GTA_FRAME_COUNTER_ADDR 0x00b7cb4cu
#define PROBE_PICKUP_SAMPLE_SLOTS 8u
#define PROBE_PICKUP_TRACE_RING_SIZE 256u

#define PROBE_PICKUP_EVENT_PICKED_UP 1u
#define PROBE_PICKUP_EVENT_PROCESS 2u
#define PROBE_PICKUP_EVENT_RPC_131 3u
#define PROBE_PICKUP_EVENT_RPC_97 4u

#define PROBE_PICKUP_RPC_PICKED_UP 131u
#define PROBE_PICKUP_RPC_WEAPON_PICKED_UP 97u

typedef void(PROBE_PICKUP_THISCALL *probe_pickup_void_fn)(void *self);
typedef void(PROBE_PICKUP_THISCALL *probe_pickup_raw_fn)(void *self,
                                                         DWORD raw_index);

typedef struct probe_pickup_slot_state {
  DWORD valid_mask;
  DWORD slot;
  DWORD handle;
  DWORD raw_gta_index;
  DWORD timer;
  DWORD from_player;
  DWORD model;
  DWORD type;
  DWORD pos_bits[3];
  BYTE dropped;
} probe_pickup_slot_state;

typedef struct probe_pickup_pool_state {
  DWORD valid_mask;
  DWORD count;
  DWORD active_count;
  DWORD captured_count;
  probe_pickup_slot_state slots[PROBE_PICKUP_SAMPLE_SLOTS];
} probe_pickup_pool_state;

typedef struct probe_pickup_trace {
  volatile LONG committed_seq;
  LONG ring_seq;
  LONG event_seq;
  DWORD tick;
  DWORD thread_id;
  DWORD gta_frame;
  DWORD caller_rva;
  DWORD hook_rva;
  DWORD pool;
  DWORD raw_argument;
  DWORD process_ordinal;
  DWORD process_gate_before;
  DWORD process_gate_after;
  DWORD process_tick_delta;
  DWORD process_frame_delta;
  DWORD rpc_id;
  DWORD rpc_bits;
  DWORD rpc_payload;
  DWORD rpc_payload_valid;
  DWORD rpc_priority;
  DWORD rpc_reliability;
  DWORD rpc_channel;
  DWORD rpc_result;
  BYTE kind;
  probe_pickup_pool_state before;
  probe_pickup_pool_state after;
} probe_pickup_trace;

typedef struct probe_pickup_hook {
  const char *name;
  DWORD rva;
  const BYTE *expected;
  BYTE length;
  void *replacement;
  void *trampoline;
  BYTE saved[16];
  volatile LONG installed;
} probe_pickup_hook;

static uintptr_t g_pickup_samp_base;
static DWORD g_pickup_samp_size;
static volatile LONG g_pickup_install_state;
static probe_pickup_trace
    g_pickup_trace_ring[PROBE_PICKUP_TRACE_RING_SIZE];
static volatile LONG g_pickup_trace_write_seq;
static LONG g_pickup_trace_flushed_seq;
static LONG g_pickup_trace_overflow_count;
static volatile LONG g_pickup_event_seq;
static volatile LONG g_pickup_process_ordinal;
static volatile LONG g_pickup_last_process_tick;
static volatile LONG g_pickup_last_process_frame;

static const BYTE g_pickup_picked_up_entry[] = {
    0x64, 0xa1, 0x00, 0x00, 0x00, 0x00};
static const BYTE g_pickup_process_entry[] = {
    0x64, 0xa1, 0x00, 0x00, 0x00, 0x00};

static void PROBE_PICKUP_THISCALL hook_pickup_picked_up(void *self,
                                                        DWORD raw_index);
static void PROBE_PICKUP_THISCALL hook_pickup_process(void *self);

static probe_pickup_hook g_pickup_hooks[] = {
    {"CPickupPool::PickedUp", PROBE_PICKUP_PICKED_UP_RVA,
     g_pickup_picked_up_entry, (BYTE)sizeof(g_pickup_picked_up_entry),
     (void *)hook_pickup_picked_up, NULL, {0}, 0},
    {"CPickupPool::Process", PROBE_PICKUP_PROCESS_RVA,
     g_pickup_process_entry, (BYTE)sizeof(g_pickup_process_entry),
     (void *)hook_pickup_process, NULL, {0}, 0},
};

static int pickup_memory_is_readable(uintptr_t address, size_t size) {
  uintptr_t cursor;
  uintptr_t end;

  if (address == 0u || size == 0u || address > UINTPTR_MAX - size) {
    return 0;
  }
  cursor = address;
  end = address + size;
  while (cursor < end) {
    MEMORY_BASIC_INFORMATION mbi;
    uintptr_t region_end;
    DWORD protect;
    if (VirtualQuery((const void *)cursor, &mbi, sizeof(mbi)) != sizeof(mbi) ||
        mbi.State != MEM_COMMIT) {
      return 0;
    }
    protect = mbi.Protect & 0xffu;
    if ((mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS)) != 0u ||
        protect == PAGE_NOACCESS) {
      return 0;
    }
    region_end = (uintptr_t)mbi.BaseAddress + mbi.RegionSize;
    if (region_end <= cursor) {
      return 0;
    }
    cursor = region_end < end ? region_end : end;
  }
  return 1;
}

static DWORD pickup_read_u32(uintptr_t address, DWORD fallback) {
  DWORD value;
  if (!pickup_memory_is_readable(address, sizeof(value))) {
    return fallback;
  }
  memcpy(&value, (const void *)address, sizeof(value));
  return value;
}

static WORD pickup_read_u16(uintptr_t address, WORD fallback) {
  WORD value;
  if (!pickup_memory_is_readable(address, sizeof(value))) {
    return fallback;
  }
  memcpy(&value, (const void *)address, sizeof(value));
  return value;
}

static BYTE pickup_read_u8(uintptr_t address, BYTE fallback) {
  BYTE value;
  if (!pickup_memory_is_readable(address, sizeof(value))) {
    return fallback;
  }
  memcpy(&value, (const void *)address, sizeof(value));
  return value;
}

static int pickup_pe_identity_matches(HMODULE module, DWORD timestamp,
                                      DWORD entry_rva, DWORD image_size,
                                      DWORD preferred_base, DWORD checksum,
                                      int check_checksum,
                                      int require_relocs_stripped) {
  PIMAGE_DOS_HEADER dos;
  PIMAGE_NT_HEADERS nt;
  if (module == NULL || image_size < sizeof(IMAGE_NT_HEADERS)) {
    return 0;
  }
  dos = (PIMAGE_DOS_HEADER)module;
  if (!pickup_memory_is_readable((uintptr_t)dos, sizeof(*dos)) ||
      dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0 ||
      (DWORD)dos->e_lfanew >
          image_size - (DWORD)sizeof(IMAGE_NT_HEADERS)) {
    return 0;
  }
  nt = (PIMAGE_NT_HEADERS)((BYTE *)module + dos->e_lfanew);
  if (!pickup_memory_is_readable((uintptr_t)nt, sizeof(*nt)) ||
      nt->Signature != IMAGE_NT_SIGNATURE ||
      nt->FileHeader.Machine != IMAGE_FILE_MACHINE_I386 ||
      nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR32_MAGIC ||
      nt->OptionalHeader.NumberOfRvaAndSizes <=
          IMAGE_DIRECTORY_ENTRY_BASERELOC) {
    return 0;
  }
  return nt->FileHeader.TimeDateStamp == timestamp &&
         nt->OptionalHeader.ImageBase == preferred_base &&
         nt->OptionalHeader.AddressOfEntryPoint == entry_rva &&
         nt->OptionalHeader.SizeOfImage == image_size &&
         (!check_checksum || nt->OptionalHeader.CheckSum == checksum) &&
         (require_relocs_stripped
              ? (nt->FileHeader.Characteristics &
                 IMAGE_FILE_RELOCS_STRIPPED) != 0
              : ((nt->FileHeader.Characteristics &
                  IMAGE_FILE_RELOCS_STRIPPED) == 0 &&
                 nt->OptionalHeader
                         .DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC]
                         .VirtualAddress != 0u &&
                 nt->OptionalHeader
                         .DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC]
                         .Size != 0u));
}

static DWORD pickup_caller_rva(void *caller) {
  uintptr_t value = (uintptr_t)caller;
  if (g_pickup_samp_base == 0u || value < g_pickup_samp_base ||
      value >= g_pickup_samp_base + g_pickup_samp_size) {
    return 0xffffffffu;
  }
  return (DWORD)(value - g_pickup_samp_base);
}

static void pickup_capture_slot(uintptr_t pool, DWORD slot,
                                probe_pickup_slot_state *state) {
  uintptr_t handle;
  uintptr_t raw_index;
  uintptr_t timer;
  uintptr_t dropped;
  uintptr_t data;
  memset(state, 0, sizeof(*state));
  state->slot = slot;
  state->raw_gta_index = 0xffffffffu;
  state->from_player = 0xffffu;
  if (pool == 0u || slot >= PROBE_PICKUP_CAPACITY) {
    return;
  }
  handle = pool + PROBE_PICKUP_HANDLE_OFFSET + slot * sizeof(DWORD);
  raw_index =
      pool + PROBE_PICKUP_RAW_GTA_INDEX_OFFSET + slot * sizeof(DWORD);
  timer = pool + PROBE_PICKUP_TIMER_OFFSET + slot * sizeof(DWORD);
  dropped = pool + PROBE_PICKUP_DROPPED_OFFSET +
            slot * PROBE_PICKUP_DROPPED_STRIDE;
  data = pool + PROBE_PICKUP_DATA_OFFSET +
         slot * PROBE_PICKUP_DATA_STRIDE;
  if (pickup_memory_is_readable(handle, sizeof(DWORD))) {
    state->handle = pickup_read_u32(handle, 0u);
    state->valid_mask |= 0x01u;
  }
  if (pickup_memory_is_readable(raw_index, sizeof(DWORD))) {
    state->raw_gta_index = pickup_read_u32(raw_index, 0xffffffffu);
    state->valid_mask |= 0x02u;
  }
  if (pickup_memory_is_readable(timer, sizeof(DWORD))) {
    state->timer = pickup_read_u32(timer, 0u);
    state->valid_mask |= 0x04u;
  }
  if (pickup_memory_is_readable(dropped, PROBE_PICKUP_DROPPED_STRIDE)) {
    state->dropped = pickup_read_u8(dropped, 0xffu);
    state->from_player =
        pickup_read_u16(dropped + PROBE_PICKUP_DROPPED_PLAYER_OFFSET,
                        0xffffu);
    state->valid_mask |= 0x08u;
  } else {
    state->dropped = 0xffu;
  }
  if (pickup_memory_is_readable(data, PROBE_PICKUP_DATA_STRIDE)) {
    state->model =
        pickup_read_u32(data + PROBE_PICKUP_DATA_MODEL_OFFSET, 0xffffffffu);
    state->type =
        pickup_read_u32(data + PROBE_PICKUP_DATA_TYPE_OFFSET, 0xffffffffu);
    state->pos_bits[0] =
        pickup_read_u32(data + PROBE_PICKUP_DATA_POS_OFFSET, 0xffffffffu);
    state->pos_bits[1] = pickup_read_u32(
        data + PROBE_PICKUP_DATA_POS_OFFSET + 4u, 0xffffffffu);
    state->pos_bits[2] = pickup_read_u32(
        data + PROBE_PICKUP_DATA_POS_OFFSET + 8u, 0xffffffffu);
    state->valid_mask |= 0x10u;
  } else {
    state->model = 0xffffffffu;
    state->type = 0xffffffffu;
    state->pos_bits[0] = 0xffffffffu;
    state->pos_bits[1] = 0xffffffffu;
    state->pos_bits[2] = 0xffffffffu;
  }
}

static int pickup_state_has_slot(const probe_pickup_pool_state *state,
                                 DWORD slot) {
  DWORD i;
  for (i = 0u; i < state->captured_count; ++i) {
    if (state->slots[i].slot == slot) {
      return 1;
    }
  }
  return 0;
}

static void pickup_add_slot(uintptr_t pool, DWORD slot,
                            probe_pickup_pool_state *state) {
  if (slot >= PROBE_PICKUP_CAPACITY ||
      state->captured_count >= PROBE_PICKUP_SAMPLE_SLOTS ||
      pickup_state_has_slot(state, slot)) {
    return;
  }
  pickup_capture_slot(pool, slot, &state->slots[state->captured_count]);
  ++state->captured_count;
}

static void pickup_capture_pool(uintptr_t pool, DWORD focus_slot,
                                DWORD focus_raw,
                                probe_pickup_pool_state *state) {
  const DWORD *handles;
  const DWORD *raw_indices;
  DWORD i;
  memset(state, 0, sizeof(*state));
  if (pool == 0u ||
      !pickup_memory_is_readable(
          pool + PROBE_PICKUP_HANDLE_OFFSET,
          PROBE_PICKUP_CAPACITY * sizeof(DWORD)) ||
      !pickup_memory_is_readable(
          pool + PROBE_PICKUP_RAW_GTA_INDEX_OFFSET,
          PROBE_PICKUP_CAPACITY * sizeof(DWORD))) {
    return;
  }
  state->valid_mask = 0x01u;
  state->count =
      pickup_read_u32(pool + PROBE_PICKUP_COUNT_OFFSET, 0xffffffffu);
  handles = (const DWORD *)(pool + PROBE_PICKUP_HANDLE_OFFSET);
  raw_indices =
      (const DWORD *)(pool + PROBE_PICKUP_RAW_GTA_INDEX_OFFSET);

  if (focus_slot < PROBE_PICKUP_CAPACITY && handles[focus_slot] != 0u) {
    pickup_add_slot(pool, focus_slot, state);
  }
  if (focus_raw != 0xffffffffu) {
    for (i = 0u; i < PROBE_PICKUP_CAPACITY; ++i) {
      if (handles[i] != 0u && raw_indices[i] == focus_raw) {
        pickup_add_slot(pool, i, state);
        break;
      }
    }
  }
  for (i = 0u; i < PROBE_PICKUP_CAPACITY; ++i) {
    if (handles[i] == 0u) {
      continue;
    }
    ++state->active_count;
    pickup_add_slot(pool, i, state);
  }
}

static uintptr_t pickup_resolve_pool(void) {
  DWORD netgame;
  DWORD pools;
  netgame = pickup_read_u32(
      g_pickup_samp_base + PROBE_PICKUP_NETGAME_PTR_RVA, 0u);
  if (netgame == 0u) {
    return 0u;
  }
  pools = pickup_read_u32(
      (uintptr_t)netgame + PROBE_PICKUP_NETGAME_POOLS_OFFSET, 0u);
  if (pools == 0u) {
    return 0u;
  }
  return (uintptr_t)pickup_read_u32(
      (uintptr_t)pools + PROBE_PICKUP_POOLS_PICKUP_OFFSET, 0u);
}

static void pickup_begin_trace(probe_pickup_trace *trace, BYTE kind,
                               DWORD hook_rva, DWORD pool,
                               DWORD raw_argument, DWORD caller_rva) {
  memset(trace, 0, sizeof(*trace));
  trace->event_seq = InterlockedIncrement(&g_pickup_event_seq);
  trace->tick = GetTickCount();
  trace->thread_id = GetCurrentThreadId();
  trace->gta_frame =
      pickup_read_u32(PROBE_PICKUP_GTA_FRAME_COUNTER_ADDR, 0xffffffffu);
  trace->caller_rva = caller_rva;
  trace->hook_rva = hook_rva;
  trace->pool = pool;
  trace->raw_argument = raw_argument;
  trace->kind = kind;
}

static void pickup_publish_trace(probe_pickup_trace *trace) {
  probe_pickup_trace *slot;
  LONG ring_seq;
  ring_seq = InterlockedIncrement(&g_pickup_trace_write_seq);
  trace->ring_seq = ring_seq;
  trace->committed_seq = 0;
  slot = &g_pickup_trace_ring[
      ((DWORD)ring_seq - 1u) % PROBE_PICKUP_TRACE_RING_SIZE];
  InterlockedExchange(&slot->committed_seq, 0);
  *slot = *trace;
  MemoryBarrier();
  InterlockedExchange(&slot->committed_seq, ring_seq);
}

static void PROBE_PICKUP_THISCALL hook_pickup_picked_up(void *self,
                                                        DWORD raw_index) {
  probe_pickup_trace trace;
  pickup_begin_trace(&trace, PROBE_PICKUP_EVENT_PICKED_UP,
                     PROBE_PICKUP_PICKED_UP_RVA, (DWORD)(uintptr_t)self,
                     raw_index,
                     pickup_caller_rva(__builtin_return_address(0)));
  trace.process_ordinal =
      (DWORD)InterlockedCompareExchange(&g_pickup_process_ordinal, 0, 0);
  trace.process_gate_before = pickup_read_u32(
      g_pickup_samp_base + PROBE_PICKUP_PROCESS_GATE_RVA, 0xffffffffu);
  pickup_capture_pool((uintptr_t)self, 0xffffffffu, raw_index,
                      &trace.before);
  ((probe_pickup_raw_fn)g_pickup_hooks[0].trampoline)(self, raw_index);
  trace.process_gate_after = pickup_read_u32(
      g_pickup_samp_base + PROBE_PICKUP_PROCESS_GATE_RVA, 0xffffffffu);
  pickup_capture_pool((uintptr_t)self, 0xffffffffu, raw_index,
                      &trace.after);
  pickup_publish_trace(&trace);
}

static void PROBE_PICKUP_THISCALL hook_pickup_process(void *self) {
  probe_pickup_trace trace;
  LONG previous_tick;
  LONG previous_frame;
  pickup_begin_trace(&trace, PROBE_PICKUP_EVENT_PROCESS,
                     PROBE_PICKUP_PROCESS_RVA, (DWORD)(uintptr_t)self,
                     0xffffffffu,
                     pickup_caller_rva(__builtin_return_address(0)));
  trace.process_ordinal =
      (DWORD)InterlockedIncrement(&g_pickup_process_ordinal);
  previous_tick =
      InterlockedExchange(&g_pickup_last_process_tick, (LONG)trace.tick);
  previous_frame =
      InterlockedExchange(&g_pickup_last_process_frame,
                          (LONG)trace.gta_frame);
  if (previous_tick != 0) {
    trace.process_tick_delta = trace.tick - (DWORD)previous_tick;
  }
  if (previous_frame != 0 && trace.gta_frame != 0xffffffffu) {
    trace.process_frame_delta = trace.gta_frame - (DWORD)previous_frame;
  }
  trace.process_gate_before = pickup_read_u32(
      g_pickup_samp_base + PROBE_PICKUP_PROCESS_GATE_RVA, 0xffffffffu);
  pickup_capture_pool((uintptr_t)self, 0xffffffffu, 0xffffffffu,
                      &trace.before);
  ((probe_pickup_void_fn)g_pickup_hooks[1].trampoline)(self);
  trace.process_gate_after = pickup_read_u32(
      g_pickup_samp_base + PROBE_PICKUP_PROCESS_GATE_RVA, 0xffffffffu);
  pickup_capture_pool((uintptr_t)self, 0xffffffffu, 0xffffffffu,
                      &trace.after);
  pickup_publish_trace(&trace);
}

void probe_pickup_observe_rpc(BYTE rpc_id, const BYTE *payload, int bits,
                              int priority, int reliability,
                              char ordering_channel, DWORD caller_rva,
                              BYTE result) {
  probe_pickup_trace trace;
  DWORD focus_slot = 0xffffffffu;
  uintptr_t pool;
  if (InterlockedCompareExchange(&g_pickup_install_state, 0, 0) != 1 ||
      (rpc_id != PROBE_PICKUP_RPC_PICKED_UP &&
       rpc_id != PROBE_PICKUP_RPC_WEAPON_PICKED_UP)) {
    return;
  }
  pool = pickup_resolve_pool();
  pickup_begin_trace(
      &trace,
      rpc_id == PROBE_PICKUP_RPC_PICKED_UP ? PROBE_PICKUP_EVENT_RPC_131
                                           : PROBE_PICKUP_EVENT_RPC_97,
      0u, (DWORD)pool, 0xffffffffu, caller_rva);
  trace.process_ordinal =
      (DWORD)InterlockedCompareExchange(&g_pickup_process_ordinal, 0, 0);
  trace.process_gate_before = pickup_read_u32(
      g_pickup_samp_base + PROBE_PICKUP_PROCESS_GATE_RVA, 0xffffffffu);
  trace.process_gate_after = trace.process_gate_before;
  trace.rpc_id = rpc_id;
  trace.rpc_bits = bits >= 0 ? (DWORD)bits : 0xffffffffu;
  trace.rpc_priority = (DWORD)priority;
  trace.rpc_reliability = (DWORD)reliability;
  trace.rpc_channel = (DWORD)(BYTE)ordering_channel;
  trace.rpc_result = result;
  if (rpc_id == PROBE_PICKUP_RPC_PICKED_UP && bits >= 32 &&
      pickup_memory_is_readable((uintptr_t)payload, sizeof(DWORD))) {
    memcpy(&trace.rpc_payload, payload, sizeof(DWORD));
    trace.rpc_payload_valid = 1u;
    focus_slot = trace.rpc_payload;
  } else if (rpc_id == PROBE_PICKUP_RPC_WEAPON_PICKED_UP && bits >= 16 &&
             pickup_memory_is_readable((uintptr_t)payload, sizeof(WORD))) {
    WORD from_player;
    memcpy(&from_player, payload, sizeof(from_player));
    trace.rpc_payload = from_player;
    trace.rpc_payload_valid = 1u;
  }
  pickup_capture_pool(pool, focus_slot, 0xffffffffu, &trace.before);
  pickup_publish_trace(&trace);
}

static int pickup_bytes_match(DWORD rva, const BYTE *bytes, size_t size) {
  return rva <= g_pickup_samp_size &&
         size <= (size_t)(g_pickup_samp_size - rva) &&
         pickup_memory_is_readable(g_pickup_samp_base + rva, size) &&
         memcmp((const void *)(g_pickup_samp_base + rva), bytes, size) == 0;
}

static int pickup_process_gate_bytes_match(void) {
  BYTE expected[] = {
      0x83, 0x3d, 0x00, 0x00, 0x00, 0x00, 0x05, 0x7e, 0x46};
  DWORD relocated_gate =
      (DWORD)(g_pickup_samp_base + PROBE_PICKUP_PROCESS_GATE_RVA);
  memcpy(expected + 2u, &relocated_gate, sizeof(relocated_gate));
  return pickup_bytes_match(0x00008c8eu, expected, sizeof(expected));
}

static int pickup_preflight(void) {
  static const BYTE picked_up_tail[] = {
      0x8b, 0x8c, 0x24, 0x20, 0x01, 0x00, 0x00, 0x5f, 0x5e,
      0x64, 0x89, 0x0d, 0x00, 0x00, 0x00, 0x00, 0x81, 0xc4,
      0x24, 0x01, 0x00, 0x00, 0xc2, 0x04, 0x00};
  static const BYTE process_tail[] = {
      0x8b, 0x8c, 0x24, 0x2c, 0x01, 0x00, 0x00, 0x5f, 0x5e,
      0x5d, 0x5b, 0x64, 0x89, 0x0d, 0x00, 0x00, 0x00, 0x00,
      0x81, 0xc4, 0x28, 0x01, 0x00, 0x00, 0xc3};
  size_t i;
  for (i = 0u; i < sizeof(g_pickup_hooks) / sizeof(g_pickup_hooks[0]);
       ++i) {
    if (!pickup_bytes_match(g_pickup_hooks[i].rva,
                            g_pickup_hooks[i].expected,
                            g_pickup_hooks[i].length)) {
      return 0;
    }
  }
  return pickup_bytes_match(0x00013500u, picked_up_tail,
                            sizeof(picked_up_tail)) &&
         pickup_bytes_match(0x00013655u, process_tail,
                            sizeof(process_tail)) &&
         pickup_process_gate_bytes_match();
}

static int pickup_rel32(void *from_after, void *to, LONG *relative) {
  intptr_t delta = (BYTE *)to - (BYTE *)from_after;
  if (delta < INT32_MIN || delta > INT32_MAX) {
    return 0;
  }
  *relative = (LONG)delta;
  return 1;
}

static int pickup_prepare_trampoline(probe_pickup_hook *hook) {
  BYTE *trampoline;
  LONG back_rel;
  uintptr_t target;
  if (hook == NULL || hook->length < 5u ||
      hook->length > sizeof(hook->saved)) {
    return 0;
  }
  target = g_pickup_samp_base + hook->rva;
  trampoline = (BYTE *)VirtualAlloc(
      NULL, (SIZE_T)hook->length + 5u, MEM_COMMIT | MEM_RESERVE,
      PAGE_EXECUTE_READWRITE);
  if (trampoline == NULL) {
    return 0;
  }
  memcpy(hook->saved, (const void *)target, hook->length);
  memcpy(trampoline, hook->saved, hook->length);
  if (!pickup_rel32(trampoline + hook->length + 5u,
                    (void *)(target + hook->length), &back_rel)) {
    VirtualFree(trampoline, 0u, MEM_RELEASE);
    return 0;
  }
  trampoline[hook->length] = 0xe9u;
  memcpy(trampoline + hook->length + 1u, &back_rel, sizeof(back_rel));
  FlushInstructionCache(GetCurrentProcess(), trampoline,
                        (SIZE_T)hook->length + 5u);
  hook->trampoline = trampoline;
  return 1;
}

static int pickup_install_one(probe_pickup_hook *hook) {
  uintptr_t target;
  BYTE patch[16];
  LONG replacement_rel;
  DWORD old_protect;
  DWORD restore_protect;
  if (hook == NULL || hook->trampoline == NULL ||
      hook->length > sizeof(patch)) {
    return 0;
  }
  target = g_pickup_samp_base + hook->rva;
  if (!pickup_memory_is_readable(target, hook->length) ||
      memcmp((const void *)target, hook->saved, hook->length) != 0 ||
      !pickup_rel32((void *)(target + 5u), hook->replacement,
                    &replacement_rel)) {
    return 0;
  }
  memset(patch, 0x90, hook->length);
  patch[0] = 0xe9u;
  memcpy(patch + 1u, &replacement_rel, sizeof(replacement_rel));
  if (!VirtualProtect((void *)target, hook->length,
                      PAGE_EXECUTE_READWRITE, &old_protect)) {
    return 0;
  }
  memcpy((void *)target, patch, hook->length);
  FlushInstructionCache(GetCurrentProcess(), (const void *)target,
                        hook->length);
  (void)VirtualProtect((void *)target, hook->length, old_protect,
                       &restore_protect);
  InterlockedExchange(&hook->installed, 1);
  return 1;
}

static int pickup_patch_is_owned(const probe_pickup_hook *hook) {
  BYTE expected[16];
  LONG relative;
  uintptr_t target;
  if (hook == NULL || hook->length > sizeof(expected)) {
    return 0;
  }
  target = g_pickup_samp_base + hook->rva;
  if (!pickup_rel32((void *)(target + 5u), hook->replacement, &relative)) {
    return 0;
  }
  memset(expected, 0x90, hook->length);
  expected[0] = 0xe9u;
  memcpy(expected + 1u, &relative, sizeof(relative));
  return pickup_memory_is_readable(target, hook->length) &&
         memcmp((const void *)target, expected, hook->length) == 0;
}

static int pickup_restore_one(probe_pickup_hook *hook) {
  uintptr_t target;
  DWORD old_protect;
  DWORD restore_protect;
  if (hook == NULL ||
      InterlockedCompareExchange(&hook->installed, 0, 0) != 1 ||
      !pickup_patch_is_owned(hook)) {
    return 0;
  }
  target = g_pickup_samp_base + hook->rva;
  if (!VirtualProtect((void *)target, hook->length,
                      PAGE_EXECUTE_READWRITE, &old_protect)) {
    return 0;
  }
  memcpy((void *)target, hook->saved, hook->length);
  FlushInstructionCache(GetCurrentProcess(), (const void *)target,
                        hook->length);
  (void)VirtualProtect((void *)target, hook->length, old_protect,
                       &restore_protect);
  InterlockedExchange(&hook->installed, 0);
  return 1;
}

int probe_pickup_install(HMODULE samp_module, DWORD samp_size, int enabled,
                         int code_hooks_disabled,
                         probe_pickup_log_fn log_fn, int log_summary) {
  HMODULE gta_module;
  size_t hook_count = sizeof(g_pickup_hooks) / sizeof(g_pickup_hooks[0]);
  size_t i;
  int installed = 0;

  if (!enabled) {
    if (log_summary && log_fn != NULL) {
      log_fn("pickup_hook: disabled by default; enable with "
             "SAMP_PROBE_PICKUP_HOOKS=1 or samp_probe_pickup_hooks.flag");
    }
    return 0;
  }
  if (code_hooks_disabled) {
    if (log_summary && log_fn != NULL) {
      log_fn("pickup_hook: disabled by SAMP_PROBE_NO_SAMP_CODE_HOOKS");
    }
    return 0;
  }
  if (InterlockedCompareExchange(&g_pickup_install_state, 0, 0) == 1) {
    return (int)hook_count;
  }
  if (InterlockedCompareExchange(&g_pickup_install_state, 0, 0) < 0) {
    return 0;
  }

  g_pickup_samp_base = (uintptr_t)samp_module;
  g_pickup_samp_size = samp_size;
  gta_module = GetModuleHandleA(NULL);
  if (g_pickup_samp_size != PROBE_PICKUP_R5_IMAGE_SIZE ||
      !pickup_pe_identity_matches(
          samp_module, PROBE_PICKUP_R5_TIMESTAMP,
          PROBE_PICKUP_R5_ENTRY_RVA, PROBE_PICKUP_R5_IMAGE_SIZE,
          PROBE_PICKUP_R5_PREFERRED_BASE, 0u, 0, 0) ||
      (uintptr_t)gta_module != PROBE_PICKUP_GTA_PREFERRED_BASE ||
      !pickup_pe_identity_matches(
          gta_module, PROBE_PICKUP_GTA_TIMESTAMP,
          PROBE_PICKUP_GTA_ENTRY_RVA, PROBE_PICKUP_GTA_IMAGE_SIZE,
          PROBE_PICKUP_GTA_PREFERRED_BASE, PROBE_PICKUP_GTA_CHECKSUM,
          1, 1)) {
    if (log_summary && log_fn != NULL) {
      log_fn("pickup_hook: skip unsupported_identity installed=0 "
             "samp_base=0x%08lx samp_size=0x%08lx samp_sha256=%s "
             "gta_base=0x%08lx gta_sha256=%s evidence=STATIC_037",
             (unsigned long)g_pickup_samp_base,
             (unsigned long)g_pickup_samp_size, PROBE_PICKUP_R5_SHA256,
             (unsigned long)(uintptr_t)gta_module,
             PROBE_PICKUP_GTA_SHA256);
    }
    InterlockedExchange(&g_pickup_install_state, -1);
    return 0;
  }
  if (!pickup_preflight()) {
    if (log_summary && log_fn != NULL) {
      log_fn("pickup_hook: skip preflight_mismatch installed=0 requested=%u "
             "evidence=STATIC_037",
             (unsigned)hook_count);
    }
    InterlockedExchange(&g_pickup_install_state, -1);
    return 0;
  }
  for (i = 0u; i < hook_count; ++i) {
    if (!pickup_prepare_trampoline(&g_pickup_hooks[i])) {
      break;
    }
  }
  if (i != hook_count) {
    size_t j;
    for (j = 0u; j < hook_count; ++j) {
      if (g_pickup_hooks[j].trampoline != NULL) {
        VirtualFree(g_pickup_hooks[j].trampoline, 0u, MEM_RELEASE);
        g_pickup_hooks[j].trampoline = NULL;
      }
    }
    if (log_summary && log_fn != NULL) {
      log_fn("pickup_hook: trampoline_allocation_failed prepared=%u "
             "requested=%u installed=0",
             (unsigned)i, (unsigned)hook_count);
    }
    InterlockedExchange(&g_pickup_install_state, -1);
    return 0;
  }
  for (i = 0u; i < hook_count; ++i) {
    if (!pickup_install_one(&g_pickup_hooks[i])) {
      break;
    }
    ++installed;
  }
  if ((size_t)installed != hook_count) {
    while (installed > 0) {
      --installed;
      (void)pickup_restore_one(&g_pickup_hooks[installed]);
    }
    if (log_summary && log_fn != NULL) {
      log_fn("pickup_hook: incomplete_install installed=0 requested=%u "
             "run_invalid=1",
             (unsigned)hook_count);
    }
    InterlockedExchange(&g_pickup_install_state, -1);
    return 0;
  }
  InterlockedExchange(&g_pickup_install_state, 1);
  if (log_summary && log_fn != NULL) {
    log_fn("pickup_hook: summary installed=%u requested=%u "
           "rvas=0x13440,0x13520 process_gate_rva=0x118a10 "
           "pool_layout=handle:0x4,raw_gta_index:0x4004,timer:0x8004,"
           "dropped:0xc004,type:0xf008 "
           "samp_base=0x%08lx samp_sha256=%s gta_sha256=%s "
           "guard=identity,gta_preferred_base,entry_bytes,tails,"
           "all_or_nothing evidence=STATIC_037,TODO_VERIFY",
           (unsigned)hook_count, (unsigned)hook_count,
           (unsigned long)g_pickup_samp_base, PROBE_PICKUP_R5_SHA256,
           PROBE_PICKUP_GTA_SHA256);
  }
  return (int)hook_count;
}

int probe_pickup_is_active(void) {
  return InterlockedCompareExchange(&g_pickup_install_state, 0, 0) == 1;
}

static const char *pickup_event_name(BYTE kind) {
  switch (kind) {
  case PROBE_PICKUP_EVENT_PICKED_UP:
    return "picked_up";
  case PROBE_PICKUP_EVENT_PROCESS:
    return "process";
  case PROBE_PICKUP_EVENT_RPC_131:
    return "rpc_131";
  case PROBE_PICKUP_EVENT_RPC_97:
    return "rpc_97";
  default:
    return "unknown";
  }
}

static void pickup_log_pool(probe_pickup_log_fn log_fn,
                            const probe_pickup_trace *trace,
                            const char *phase,
                            const probe_pickup_pool_state *state) {
  DWORD i;
  log_fn("pickup_pool_r5: seq=%ld event=%ld phase=%s valid=0x%08lx "
         "pool=0x%08lx count=%lu active=%lu captured=%lu",
         (long)trace->ring_seq, (long)trace->event_seq, phase,
         (unsigned long)state->valid_mask, (unsigned long)trace->pool,
         (unsigned long)state->count, (unsigned long)state->active_count,
         (unsigned long)state->captured_count);
  for (i = 0u; i < state->captured_count; ++i) {
    const probe_pickup_slot_state *slot = &state->slots[i];
    log_fn("pickup_slot_r5: seq=%ld event=%ld phase=%s sample=%lu "
           "valid=0x%08lx slot=%lu handle=0x%08lx raw_gta_index=%lu "
           "timer=%lu dropped=%u from_player=%lu model=%ld type=%ld "
           "pos_bits=%08lx,%08lx,%08lx",
           (long)trace->ring_seq, (long)trace->event_seq, phase,
           (unsigned long)i, (unsigned long)slot->valid_mask,
           (unsigned long)slot->slot, (unsigned long)slot->handle,
           (unsigned long)slot->raw_gta_index,
           (unsigned long)slot->timer, (unsigned)slot->dropped,
           (unsigned long)slot->from_player, (long)slot->model,
           (long)slot->type, (unsigned long)slot->pos_bits[0],
           (unsigned long)slot->pos_bits[1],
           (unsigned long)slot->pos_bits[2]);
  }
}

void probe_pickup_flush(probe_pickup_log_fn log_fn) {
  LONG write_seq;
  LONG pending;
  if (log_fn == NULL) {
    return;
  }
  write_seq = InterlockedCompareExchange(&g_pickup_trace_write_seq, 0, 0);
  pending = write_seq - g_pickup_trace_flushed_seq;
  if (pending > (LONG)PROBE_PICKUP_TRACE_RING_SIZE) {
    LONG skipped = pending - (LONG)PROBE_PICKUP_TRACE_RING_SIZE;
    g_pickup_trace_flushed_seq += skipped;
    g_pickup_trace_overflow_count += skipped;
    log_fn("pickup_r5: overflow skipped=%ld total_skipped=%ld ring=%u",
           (long)skipped, (long)g_pickup_trace_overflow_count,
           (unsigned)PROBE_PICKUP_TRACE_RING_SIZE);
  }
  while (g_pickup_trace_flushed_seq < write_seq) {
    LONG next_seq = g_pickup_trace_flushed_seq + 1;
    probe_pickup_trace *slot =
        &g_pickup_trace_ring[
            ((DWORD)next_seq - 1u) % PROBE_PICKUP_TRACE_RING_SIZE];
    probe_pickup_trace trace;
    if (InterlockedCompareExchange(&slot->committed_seq, 0, 0) !=
        next_seq) {
      break;
    }
    MemoryBarrier();
    trace = *slot;
    MemoryBarrier();
    if (InterlockedCompareExchange(&slot->committed_seq, 0, 0) !=
        next_seq) {
      continue;
    }
    log_fn("pickup_r5: seq=%ld event=%ld tick=%lu thread=%lu frame=%lu "
           "kind=%s caller_rva=0x%08lx hook_rva=0x%08lx "
           "pool=0x%08lx raw_argument=%lu process_ordinal=%lu "
           "process_gate=%lu,%lu cadence_delta=%lu_ms/%lu_frames "
           "rpc=%lu bits=%lu payload_valid=%lu payload=%lu "
           "priority=%lu reliability=%lu channel=%lu result=%lu "
           "evidence=STATIC_037,TODO_VERIFY",
           (long)trace.ring_seq, (long)trace.event_seq,
           (unsigned long)trace.tick, (unsigned long)trace.thread_id,
           (unsigned long)trace.gta_frame,
           pickup_event_name(trace.kind),
           (unsigned long)trace.caller_rva,
           (unsigned long)trace.hook_rva, (unsigned long)trace.pool,
           (unsigned long)trace.raw_argument,
           (unsigned long)trace.process_ordinal,
           (unsigned long)trace.process_gate_before,
           (unsigned long)trace.process_gate_after,
           (unsigned long)trace.process_tick_delta,
           (unsigned long)trace.process_frame_delta,
           (unsigned long)trace.rpc_id, (unsigned long)trace.rpc_bits,
           (unsigned long)trace.rpc_payload_valid,
           (unsigned long)trace.rpc_payload,
           (unsigned long)trace.rpc_priority,
           (unsigned long)trace.rpc_reliability,
           (unsigned long)trace.rpc_channel,
           (unsigned long)trace.rpc_result);
    pickup_log_pool(log_fn, &trace,
                    trace.kind == PROBE_PICKUP_EVENT_RPC_131 ||
                            trace.kind == PROBE_PICKUP_EVENT_RPC_97
                        ? "rpc"
                        : "pre",
                    &trace.before);
    if (trace.kind == PROBE_PICKUP_EVENT_PICKED_UP ||
        trace.kind == PROBE_PICKUP_EVENT_PROCESS) {
      pickup_log_pool(log_fn, &trace, "post", &trace.after);
    }
    g_pickup_trace_flushed_seq = next_seq;
  }
}

void probe_pickup_uninstall(probe_pickup_log_fn log_fn) {
  size_t hook_count = sizeof(g_pickup_hooks) / sizeof(g_pickup_hooks[0]);
  size_t i;
  int restored = 0;
  if (InterlockedCompareExchange(&g_pickup_install_state, 0, 0) != 1) {
    return;
  }
  for (i = hook_count; i > 0u; --i) {
    restored += pickup_restore_one(&g_pickup_hooks[i - 1u]);
  }
  if (log_fn != NULL) {
    log_fn("pickup_hook: restore restored=%d requested=%u "
           "gateway_lifetime=process",
           restored, (unsigned)hook_count);
  }
  InterlockedExchange(&g_pickup_install_state,
                      restored == (int)hook_count ? 0 : -1);
}
