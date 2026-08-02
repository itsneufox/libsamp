#include "samp_probe_ui_latches.h"

#include <stdint.h>
#include <string.h>

#if defined(__GNUC__) && defined(__i386__)
#define PROBE_UL_THISCALL __attribute__((thiscall))
#else
#define PROBE_UL_THISCALL
#endif

/*
 * STATIC_037 + TODO_VERIFY:
 * The SA-MP RVAs, code guards, and object offsets in this file were recovered
 * from original 0.3.7-R5
 * SHA256=b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2.
 * GTA absolute addresses are accepted only for the exact 1.0-US image
 * SHA256=a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26.
 * Runtime meaning remains TODO_VERIFY until an original-client trace exists.
 * See docs/re/ui_latch_memory_probe_r5_20260728.md.
 */
#define PROBE_UL_R5_TIMESTAMP 0x6372c39eu
#define PROBE_UL_R5_ENTRY_RVA 0x000cbc90u
#define PROBE_UL_R5_IMAGE_SIZE 0x0027e000u
#define PROBE_UL_R5_PREFERRED_BASE 0x10000000u
#define PROBE_UL_R5_SHA256                                                   \
  "b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2"

#define PROBE_UL_GTA_TIMESTAMP 0x427101cau
#define PROBE_UL_GTA_ENTRY_RVA 0x00424570u
#define PROBE_UL_GTA_IMAGE_SIZE 0x01177000u
#define PROBE_UL_GTA_CHECKSUM 0x00dc5beau
#define PROBE_UL_GTA_PREFERRED_BASE 0x00400000u
#define PROBE_UL_GTA_SHA256                                                  \
  "a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26"

#define PROBE_UL_CHAT_MODE_TOGGLE_RVA 0x000612c0u
#define PROBE_UL_CHAT_OPEN_RVA 0x00069480u
#define PROBE_UL_CHAT_CLOSE_RVA 0x00069580u
#define PROBE_UL_SCOREBOARD_HIDE_RVA 0x0006e9e0u
#define PROBE_UL_SCOREBOARD_SHOW_RVA 0x0006f3d0u
#define PROBE_UL_CURSOR_RESTORE_RVA 0x000a05d0u
#define PROBE_UL_CURSOR_MODE_RVA 0x000a06f0u
#define PROBE_UL_MENU_QUERY_RVA 0x000a0920u
#define PROBE_UL_REMOTE_PROCESS_RVA 0x000166b0u

#define PROBE_UL_SCOREBOARD_PTR_RVA 0x0026eb4cu
#define PROBE_UL_CHAT_DISPLAY_PTR_RVA 0x0026eb80u
#define PROBE_UL_CHAT_PTR_RVA 0x0026eb84u
#define PROBE_UL_GAME_PTR_RVA 0x0026ebacu

#define PROBE_UL_SCOREBOARD_VISIBLE_OFFSET 0x00000000u
#define PROBE_UL_CHAT_DISPLAY_MODE_OFFSET 0x00000008u
#define PROBE_UL_CHAT_DISPLAY_DIRTY_OFFSET 0x000063dau
#define PROBE_UL_CHAT_ACTIVE_OFFSET 0x000014e0u
#define PROBE_UL_GAME_CURSOR_MODE_OFFSET 0x00000061u
#define PROBE_UL_GAME_CURSOR_RESTORE_OFFSET 0x00000065u

#define PROBE_UL_REMOTE_SYNC_STATE_OFFSET 0x0000010au
#define PROBE_UL_REMOTE_LAST_SYNC_TICK_OFFSET 0x000001b9u
#define PROBE_UL_REMOTE_AFK_STATE_OFFSET 0x000001c5u
#define PROBE_UL_REMOTE_PED_WRAPPER_OFFSET 0x000001ddu

#define PROBE_UL_GTA_INPUT_GATE_ADDR 0x00541df5u
#define PROBE_UL_GTA_MOUSE_GATE_ADDR 0x006194a0u
#define PROBE_UL_GTA_FRAME_COUNTER_ADDR 0x00b7cb4cu
#define PROBE_UL_GTA_PAUSE_RAW_ADDR 0x00b7cb49u
#define PROBE_UL_GTA_FRONTEND_RAW_ADDR 0x00ba67a4u

#define PROBE_UL_TRACE_RING_SIZE 256u
#define PROBE_UL_REMOTE_TRACKER_SIZE 128u
#define PROBE_UL_REMOTE_HEARTBEAT_MS 1000u

enum probe_ul_event_kind {
  PROBE_UL_EVENT_CHAT_MODE_TOGGLE = 1,
  PROBE_UL_EVENT_CHAT_OPEN = 2,
  PROBE_UL_EVENT_CHAT_CLOSE = 3,
  PROBE_UL_EVENT_SCOREBOARD_HIDE = 4,
  PROBE_UL_EVENT_SCOREBOARD_SHOW = 5,
  PROBE_UL_EVENT_CURSOR_RESTORE = 6,
  PROBE_UL_EVENT_CURSOR_MODE = 7,
  PROBE_UL_EVENT_MENU_EDGE = 8,
  PROBE_UL_EVENT_REMOTE_AFK = 9
};

enum probe_ul_reason {
  PROBE_UL_REASON_CALL = 0x01,
  PROBE_UL_REASON_BASELINE = 0x02,
  PROBE_UL_REASON_STATE_EDGE = 0x04,
  PROBE_UL_REASON_HEARTBEAT = 0x08,
  PROBE_UL_REASON_INPUT_EDGE = 0x10
};

enum probe_ul_hook_index {
  PROBE_UL_HOOK_CHAT_MODE_TOGGLE = 0,
  PROBE_UL_HOOK_CHAT_OPEN,
  PROBE_UL_HOOK_CHAT_CLOSE,
  PROBE_UL_HOOK_SCOREBOARD_HIDE,
  PROBE_UL_HOOK_SCOREBOARD_SHOW,
  PROBE_UL_HOOK_CURSOR_RESTORE,
  PROBE_UL_HOOK_CURSOR_MODE,
  PROBE_UL_HOOK_MENU_QUERY,
  PROBE_UL_HOOK_REMOTE_PROCESS
};

typedef struct probe_ul_ui_state {
  DWORD scoreboard;
  DWORD scoreboard_visible;
  DWORD chat_display;
  DWORD chat_display_mode;
  DWORD chat_display_dirty;
  DWORD chat;
  DWORD chat_active;
  DWORD game;
  DWORD cursor_mode_raw;
  DWORD cursor_restore_raw;
  DWORD frontend_raw;
  DWORD input_gate_head;
  DWORD foreground_window;
  DWORD focus_window;
  DWORD capture_window;
  DWORD cursor_flags;
  BYTE frontend_a;
  BYTE frontend_b;
  BYTE frontend_c;
  BYTE pause_raw_b7cb49;
  BYTE input_gate_tail;
  BYTE mouse_gate_byte;
} probe_ul_ui_state;

typedef struct probe_ul_remote_state {
  DWORD afk_state;
  DWORD last_sync_tick;
  DWORD ped_wrapper;
  BYTE sync_state;
} probe_ul_remote_state;

typedef struct probe_ul_trace {
  volatile LONG committed_seq;
  LONG ring_seq;
  LONG event_seq;
  DWORD tick;
  DWORD thread_id;
  DWORD gta_frame;
  DWORD caller;
  DWORD caller_rva;
  DWORD hook_rva;
  DWORD object;
  DWORD arg0;
  DWORD arg1;
  DWORD result;
  DWORD value_before;
  DWORD value_after;
  DWORD aux_before;
  DWORD aux_after;
  DWORD elapsed_before;
  DWORD elapsed_after;
  BYTE kind;
  BYTE reason;
  BYTE before_ui_valid;
  BYTE after_ui_valid;
  probe_ul_remote_state remote_before;
  probe_ul_remote_state remote_after;
  probe_ul_ui_state before_ui;
  probe_ul_ui_state after_ui;
} probe_ul_trace;

typedef struct probe_ul_remote_tracker {
  DWORD object;
  DWORD last_emit_tick;
  DWORD afk_state;
  BYTE sync_state;
  BYTE used;
} probe_ul_remote_tracker;

typedef struct probe_ul_hook {
  const char *name;
  DWORD rva;
  const BYTE *expected;
  BYTE length;
  void *replacement;
  void *trampoline;
  BYTE saved[16];
  volatile LONG installed;
} probe_ul_hook;

typedef void(PROBE_UL_THISCALL *probe_ul_this_void_fn)(void *self);
typedef void(PROBE_UL_THISCALL *probe_ul_this_arg_fn)(void *self, DWORD arg0);
typedef void(PROBE_UL_THISCALL *probe_ul_cursor_mode_fn)(void *self,
                                                        DWORD mode,
                                                        DWORD delayed_restore);
typedef int(PROBE_UL_THISCALL *probe_ul_this_int_fn)(void *self);

static void PROBE_UL_THISCALL hook_ul_chat_mode_toggle(void *self);
static void PROBE_UL_THISCALL hook_ul_chat_open(void *self);
static void PROBE_UL_THISCALL hook_ul_chat_close(void *self);
static void PROBE_UL_THISCALL hook_ul_scoreboard_hide(void *self, DWORD arg0);
static void PROBE_UL_THISCALL hook_ul_scoreboard_show(void *self);
static void PROBE_UL_THISCALL hook_ul_cursor_restore(void *self);
static void PROBE_UL_THISCALL hook_ul_cursor_mode(void *self, DWORD mode,
                                                  DWORD delayed_restore);
static int PROBE_UL_THISCALL hook_ul_menu_query(void *self);
static void PROBE_UL_THISCALL hook_ul_remote_process(void *self);

static const BYTE g_ul_chat_mode_entry[] = {0x8b, 0x41, 0x08, 0x85, 0xc0};
static const BYTE g_ul_chat_open_entry[] = {
    0x83, 0xec, 0x10, 0x56, 0x8b, 0xf1};
static const BYTE g_ul_chat_close_entry[] = {
    0x56, 0x8b, 0xf1, 0x8b, 0x86, 0xe0, 0x14, 0x00, 0x00};
static const BYTE g_ul_scoreboard_hide_entry[] = {
    0x56, 0x8b, 0xf1, 0x83, 0x3e, 0x00};
static const BYTE g_ul_scoreboard_show_entry[] = {
    0x56, 0x8b, 0xf1, 0x83, 0x3e, 0x00};
static const BYTE g_ul_cursor_restore_entry[] = {
    0x56, 0x8b, 0xf1, 0x8b, 0x46, 0x61, 0x57};
static const BYTE g_ul_cursor_mode_entry[] = {
    0x55, 0x8b, 0xec, 0x8b, 0x45, 0x08};
static const BYTE g_ul_menu_query_entry[] = {
    0x8b, 0x0d, 0xa4, 0x67, 0xba, 0x00};
static const BYTE g_ul_remote_process_entry[] = {
    0x81, 0xec, 0x90, 0x00, 0x00, 0x00};

static probe_ul_hook g_ul_hooks[] = {
    {"CChatWindow::CycleMode", PROBE_UL_CHAT_MODE_TOGGLE_RVA,
     g_ul_chat_mode_entry, (BYTE)sizeof(g_ul_chat_mode_entry),
     (void *)hook_ul_chat_mode_toggle, NULL, {0}, 0},
    {"CChat::Open", PROBE_UL_CHAT_OPEN_RVA, g_ul_chat_open_entry,
     (BYTE)sizeof(g_ul_chat_open_entry), (void *)hook_ul_chat_open,
     NULL, {0}, 0},
    {"CChat::Close", PROBE_UL_CHAT_CLOSE_RVA, g_ul_chat_close_entry,
     (BYTE)sizeof(g_ul_chat_close_entry), (void *)hook_ul_chat_close,
     NULL, {0}, 0},
    {"CScoreboard::Hide", PROBE_UL_SCOREBOARD_HIDE_RVA,
     g_ul_scoreboard_hide_entry, (BYTE)sizeof(g_ul_scoreboard_hide_entry),
     (void *)hook_ul_scoreboard_hide, NULL, {0}, 0},
    {"CScoreboard::Show", PROBE_UL_SCOREBOARD_SHOW_RVA,
     g_ul_scoreboard_show_entry, (BYTE)sizeof(g_ul_scoreboard_show_entry),
     (void *)hook_ul_scoreboard_show, NULL, {0}, 0},
    {"CGame::RestoreInput", PROBE_UL_CURSOR_RESTORE_RVA,
     g_ul_cursor_restore_entry, (BYTE)sizeof(g_ul_cursor_restore_entry),
     (void *)hook_ul_cursor_restore, NULL, {0}, 0},
    {"CGame::SetCursorMode", PROBE_UL_CURSOR_MODE_RVA,
     g_ul_cursor_mode_entry, (BYTE)sizeof(g_ul_cursor_mode_entry),
     (void *)hook_ul_cursor_mode, NULL, {0}, 0},
    {"CGame::IsMenuActive", PROBE_UL_MENU_QUERY_RVA,
     g_ul_menu_query_entry, (BYTE)sizeof(g_ul_menu_query_entry),
     (void *)hook_ul_menu_query, NULL, {0}, 0},
    {"CRemotePlayer::Process", PROBE_UL_REMOTE_PROCESS_RVA,
     g_ul_remote_process_entry, (BYTE)sizeof(g_ul_remote_process_entry),
     (void *)hook_ul_remote_process, NULL, {0}, 0},
};

static uintptr_t g_ul_samp_base;
static DWORD g_ul_samp_size;
static volatile LONG g_ul_install_state;
static probe_ul_trace g_ul_trace_ring[PROBE_UL_TRACE_RING_SIZE];
static volatile LONG g_ul_trace_write_seq;
static LONG g_ul_trace_flushed_seq;
static LONG g_ul_trace_overflow_count;
static volatile LONG g_ul_event_seq;
static volatile LONG g_ul_last_menu_plus_one;
static probe_ul_remote_tracker
    g_ul_remote_trackers[PROBE_UL_REMOTE_TRACKER_SIZE];
static volatile LONG g_ul_remote_tracker_overflow;
static LONG g_ul_remote_tracker_overflow_flushed;

static int ul_memory_is_readable(uintptr_t address, size_t size) {
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

static DWORD ul_read_u32(uintptr_t address, DWORD fallback) {
  DWORD value;
  if (!ul_memory_is_readable(address, sizeof(value))) {
    return fallback;
  }
  memcpy(&value, (const void *)address, sizeof(value));
  return value;
}

static BYTE ul_read_u8(uintptr_t address, BYTE fallback) {
  BYTE value;
  if (!ul_memory_is_readable(address, sizeof(value))) {
    return fallback;
  }
  memcpy(&value, (const void *)address, sizeof(value));
  return value;
}

static DWORD ul_load_u32(uintptr_t address) {
  DWORD value;
  memcpy(&value, (const void *)address, sizeof(value));
  return value;
}

static BYTE ul_load_u8(uintptr_t address) {
  BYTE value;
  memcpy(&value, (const void *)address, sizeof(value));
  return value;
}

static int ul_pe_identity_matches(HMODULE module, DWORD timestamp,
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
  if (!ul_memory_is_readable((uintptr_t)dos, sizeof(*dos)) ||
      dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0 ||
      (DWORD)dos->e_lfanew >
          image_size - (DWORD)sizeof(IMAGE_NT_HEADERS)) {
    return 0;
  }
  nt = (PIMAGE_NT_HEADERS)((BYTE *)module + dos->e_lfanew);
  if (!ul_memory_is_readable((uintptr_t)nt, sizeof(*nt)) ||
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

static DWORD ul_caller_rva(void *caller) {
  uintptr_t address = (uintptr_t)caller;
  if (address < g_ul_samp_base ||
      address >= g_ul_samp_base + g_ul_samp_size) {
    return 0xffffffffu;
  }
  return (DWORD)(address - g_ul_samp_base);
}

static void ul_capture_ui_state(probe_ul_ui_state *state) {
  DWORD object;
  CURSORINFO cursor_info;
  memset(state, 0, sizeof(*state));

  state->scoreboard =
      ul_read_u32(g_ul_samp_base + PROBE_UL_SCOREBOARD_PTR_RVA, 0u);
  object = state->scoreboard;
  state->scoreboard_visible =
      ul_read_u32((uintptr_t)object + PROBE_UL_SCOREBOARD_VISIBLE_OFFSET,
                  0xffffffffu);

  state->chat_display =
      ul_read_u32(g_ul_samp_base + PROBE_UL_CHAT_DISPLAY_PTR_RVA, 0u);
  object = state->chat_display;
  state->chat_display_mode =
      ul_read_u32((uintptr_t)object + PROBE_UL_CHAT_DISPLAY_MODE_OFFSET,
                  0xffffffffu);
  state->chat_display_dirty =
      ul_read_u32((uintptr_t)object + PROBE_UL_CHAT_DISPLAY_DIRTY_OFFSET,
                  0xffffffffu);

  state->chat = ul_read_u32(g_ul_samp_base + PROBE_UL_CHAT_PTR_RVA, 0u);
  object = state->chat;
  state->chat_active =
      ul_read_u32((uintptr_t)object + PROBE_UL_CHAT_ACTIVE_OFFSET,
                  0xffffffffu);

  state->game = ul_read_u32(g_ul_samp_base + PROBE_UL_GAME_PTR_RVA, 0u);
  object = state->game;
  state->cursor_mode_raw =
      ul_read_u32((uintptr_t)object + PROBE_UL_GAME_CURSOR_MODE_OFFSET,
                  0xffffffffu);
  state->cursor_restore_raw =
      ul_read_u32((uintptr_t)object + PROBE_UL_GAME_CURSOR_RESTORE_OFFSET,
                  0xffffffffu);

  state->frontend_raw = ul_load_u32(PROBE_UL_GTA_FRONTEND_RAW_ADDR);
  state->frontend_a = ul_load_u8(PROBE_UL_GTA_FRONTEND_RAW_ADDR);
  state->frontend_b = ul_load_u8(PROBE_UL_GTA_FRONTEND_RAW_ADDR + 1u);
  state->frontend_c = ul_load_u8(PROBE_UL_GTA_FRONTEND_RAW_ADDR + 2u);
  state->pause_raw_b7cb49 = ul_load_u8(PROBE_UL_GTA_PAUSE_RAW_ADDR);
  state->input_gate_head = ul_load_u32(PROBE_UL_GTA_INPUT_GATE_ADDR);
  state->input_gate_tail = ul_load_u8(PROBE_UL_GTA_INPUT_GATE_ADDR + 4u);
  state->mouse_gate_byte = ul_load_u8(PROBE_UL_GTA_MOUSE_GATE_ADDR);
  state->foreground_window = (DWORD)(uintptr_t)GetForegroundWindow();
  state->focus_window = (DWORD)(uintptr_t)GetFocus();
  state->capture_window = (DWORD)(uintptr_t)GetCapture();
  memset(&cursor_info, 0, sizeof(cursor_info));
  cursor_info.cbSize = sizeof(cursor_info);
  state->cursor_flags =
      GetCursorInfo(&cursor_info) ? cursor_info.flags : 0xffffffffu;
}

static void ul_capture_remote(void *self, probe_ul_remote_state *state,
                              DWORD now) {
  uintptr_t object = (uintptr_t)self;
  memset(state, 0, sizeof(*state));
  state->sync_state =
      ul_read_u8(object + PROBE_UL_REMOTE_SYNC_STATE_OFFSET, 0xffu);
  state->last_sync_tick =
      ul_read_u32(object + PROBE_UL_REMOTE_LAST_SYNC_TICK_OFFSET, now);
  state->afk_state =
      ul_read_u32(object + PROBE_UL_REMOTE_AFK_STATE_OFFSET, 0xffffffffu);
  state->ped_wrapper =
      ul_read_u32(object + PROBE_UL_REMOTE_PED_WRAPPER_OFFSET, 0u);
}

static void ul_begin_trace(probe_ul_trace *trace, BYTE kind, BYTE reason,
                           DWORD hook_rva, void *self, DWORD arg0,
                           DWORD arg1, void *caller) {
  memset(trace, 0, sizeof(*trace));
  trace->event_seq = InterlockedIncrement(&g_ul_event_seq);
  trace->tick = GetTickCount();
  trace->thread_id = GetCurrentThreadId();
  trace->gta_frame = ul_load_u32(PROBE_UL_GTA_FRAME_COUNTER_ADDR);
  trace->caller = (DWORD)(uintptr_t)caller;
  trace->caller_rva = ul_caller_rva(caller);
  trace->hook_rva = hook_rva;
  trace->object = (DWORD)(uintptr_t)self;
  trace->arg0 = arg0;
  trace->arg1 = arg1;
  trace->kind = kind;
  trace->reason = reason;
}

static void ul_publish_trace(probe_ul_trace *trace) {
  LONG ring_seq;
  probe_ul_trace *slot;
  if (trace == NULL) {
    return;
  }
  ring_seq = InterlockedIncrement(&g_ul_trace_write_seq);
  trace->ring_seq = ring_seq;
  trace->committed_seq = 0;
  slot = &g_ul_trace_ring[
      ((DWORD)ring_seq - 1u) % PROBE_UL_TRACE_RING_SIZE];
  InterlockedExchange(&slot->committed_seq, 0);
  *slot = *trace;
  MemoryBarrier();
  InterlockedExchange(&slot->committed_seq, ring_seq);
}

static void ul_run_simple_void_hook(BYTE kind, DWORD hook_rva,
                                    size_t hook_index, void *self,
                                    void *caller) {
  probe_ul_trace trace;
  ul_begin_trace(&trace, kind, PROBE_UL_REASON_CALL, hook_rva, self, 0u, 0u,
                 caller);
  trace.before_ui_valid = 1u;
  ul_capture_ui_state(&trace.before_ui);
  ((probe_ul_this_void_fn)g_ul_hooks[hook_index].trampoline)(self);
  trace.after_ui_valid = 1u;
  ul_capture_ui_state(&trace.after_ui);
  ul_publish_trace(&trace);
}

static void PROBE_UL_THISCALL hook_ul_chat_mode_toggle(void *self) {
  ul_run_simple_void_hook(PROBE_UL_EVENT_CHAT_MODE_TOGGLE,
                          PROBE_UL_CHAT_MODE_TOGGLE_RVA,
                          PROBE_UL_HOOK_CHAT_MODE_TOGGLE, self,
                          __builtin_return_address(0));
}

static void PROBE_UL_THISCALL hook_ul_chat_open(void *self) {
  ul_run_simple_void_hook(PROBE_UL_EVENT_CHAT_OPEN, PROBE_UL_CHAT_OPEN_RVA,
                          PROBE_UL_HOOK_CHAT_OPEN, self,
                          __builtin_return_address(0));
}

static void PROBE_UL_THISCALL hook_ul_chat_close(void *self) {
  ul_run_simple_void_hook(PROBE_UL_EVENT_CHAT_CLOSE, PROBE_UL_CHAT_CLOSE_RVA,
                          PROBE_UL_HOOK_CHAT_CLOSE, self,
                          __builtin_return_address(0));
}

static void PROBE_UL_THISCALL hook_ul_scoreboard_hide(void *self, DWORD arg0) {
  probe_ul_trace trace;
  ul_begin_trace(&trace, PROBE_UL_EVENT_SCOREBOARD_HIDE,
                 PROBE_UL_REASON_CALL, PROBE_UL_SCOREBOARD_HIDE_RVA, self,
                 arg0, 0u, __builtin_return_address(0));
  trace.before_ui_valid = 1u;
  ul_capture_ui_state(&trace.before_ui);
  ((probe_ul_this_arg_fn)
       g_ul_hooks[PROBE_UL_HOOK_SCOREBOARD_HIDE].trampoline)(self, arg0);
  trace.after_ui_valid = 1u;
  ul_capture_ui_state(&trace.after_ui);
  ul_publish_trace(&trace);
}

static void PROBE_UL_THISCALL hook_ul_scoreboard_show(void *self) {
  ul_run_simple_void_hook(PROBE_UL_EVENT_SCOREBOARD_SHOW,
                          PROBE_UL_SCOREBOARD_SHOW_RVA,
                          PROBE_UL_HOOK_SCOREBOARD_SHOW, self,
                          __builtin_return_address(0));
}

static void PROBE_UL_THISCALL hook_ul_cursor_restore(void *self) {
  probe_ul_trace trace;
  DWORD mode_before =
      ul_read_u32((uintptr_t)self + PROBE_UL_GAME_CURSOR_MODE_OFFSET,
                  0xffffffffu);
  DWORD restore_before =
      ul_read_u32((uintptr_t)self + PROBE_UL_GAME_CURSOR_RESTORE_OFFSET,
                  0xffffffffu);
  DWORD gate_before = ul_load_u32(PROBE_UL_GTA_INPUT_GATE_ADDR);
  BYTE gate_tail_before = ul_load_u8(PROBE_UL_GTA_INPUT_GATE_ADDR + 4u);
  BYTE mouse_before = ul_load_u8(PROBE_UL_GTA_MOUSE_GATE_ADDR);
  DWORD mode_after;
  DWORD restore_after;
  DWORD gate_after;
  BYTE gate_tail_after;
  BYTE mouse_after;

  ((probe_ul_this_void_fn)
       g_ul_hooks[PROBE_UL_HOOK_CURSOR_RESTORE].trampoline)(self);
  mode_after =
      ul_read_u32((uintptr_t)self + PROBE_UL_GAME_CURSOR_MODE_OFFSET,
                  0xffffffffu);
  restore_after =
      ul_read_u32((uintptr_t)self + PROBE_UL_GAME_CURSOR_RESTORE_OFFSET,
                  0xffffffffu);
  gate_after = ul_load_u32(PROBE_UL_GTA_INPUT_GATE_ADDR);
  gate_tail_after = ul_load_u8(PROBE_UL_GTA_INPUT_GATE_ADDR + 4u);
  mouse_after = ul_load_u8(PROBE_UL_GTA_MOUSE_GATE_ADDR);
  if (mode_before == mode_after && restore_before == restore_after &&
      gate_before == gate_after && gate_tail_before == gate_tail_after &&
      mouse_before == mouse_after) {
    return;
  }

  ul_begin_trace(&trace, PROBE_UL_EVENT_CURSOR_RESTORE,
                 PROBE_UL_REASON_INPUT_EDGE, PROBE_UL_CURSOR_RESTORE_RVA,
                 self, 0u, 0u, __builtin_return_address(0));
  trace.value_before = mode_before;
  trace.value_after = mode_after;
  trace.aux_before = restore_before;
  trace.aux_after = restore_after;
  trace.after_ui_valid = 1u;
  ul_capture_ui_state(&trace.after_ui);
  /*
   * Keep the per-frame no-change path light: reconstruct the changed raw
   * pre-state from values captured before the original call, and copy only
   * the unchanged context fields from the post snapshot. This preserves an
   * exact before/after record for every field RestoreInput itself can mutate
   * without issuing the Win32 UI queries twice on every game frame.
   */
  trace.before_ui_valid = 1u;
  trace.before_ui = trace.after_ui;
  trace.before_ui.cursor_mode_raw = mode_before;
  trace.before_ui.cursor_restore_raw = restore_before;
  trace.before_ui.input_gate_head = gate_before;
  trace.before_ui.input_gate_tail = gate_tail_before;
  trace.before_ui.mouse_gate_byte = mouse_before;
  ul_publish_trace(&trace);
}

static void PROBE_UL_THISCALL hook_ul_cursor_mode(void *self, DWORD mode,
                                                  DWORD delayed_restore) {
  probe_ul_trace trace;
  ul_begin_trace(&trace, PROBE_UL_EVENT_CURSOR_MODE, PROBE_UL_REASON_CALL,
                 PROBE_UL_CURSOR_MODE_RVA, self, mode, delayed_restore,
                 __builtin_return_address(0));
  trace.before_ui_valid = 1u;
  ul_capture_ui_state(&trace.before_ui);
  ((probe_ul_cursor_mode_fn)
       g_ul_hooks[PROBE_UL_HOOK_CURSOR_MODE].trampoline)(
      self, mode, delayed_restore);
  trace.after_ui_valid = 1u;
  ul_capture_ui_state(&trace.after_ui);
  trace.value_before = trace.before_ui.cursor_mode_raw;
  trace.value_after = trace.after_ui.cursor_mode_raw;
  trace.aux_before = trace.before_ui.cursor_restore_raw;
  trace.aux_after = trace.after_ui.cursor_restore_raw;
  ul_publish_trace(&trace);
}

static int PROBE_UL_THISCALL hook_ul_menu_query(void *self) {
  probe_ul_trace trace;
  DWORD raw_before = ul_load_u32(PROBE_UL_GTA_FRONTEND_RAW_ADDR);
  int result = ((probe_ul_this_int_fn)
                    g_ul_hooks[PROBE_UL_HOOK_MENU_QUERY].trampoline)(self);
  DWORD raw_after = ul_load_u32(PROBE_UL_GTA_FRONTEND_RAW_ADDR);
  LONG encoded = (LONG)((DWORD)result + 1u);
  LONG previous = InterlockedExchange(&g_ul_last_menu_plus_one, encoded);
  if (previous == encoded) {
    return result;
  }
  ul_begin_trace(&trace, PROBE_UL_EVENT_MENU_EDGE,
                 previous == 0 ? PROBE_UL_REASON_BASELINE
                               : PROBE_UL_REASON_STATE_EDGE,
                 PROBE_UL_MENU_QUERY_RVA, self, 0u, 0u,
                 __builtin_return_address(0));
  trace.result = (DWORD)result;
  trace.value_before = raw_before;
  trace.value_after = raw_after;
  trace.aux_before =
      previous == 0 ? 0xffffffffu : (DWORD)(previous - 1);
  trace.aux_after = (DWORD)result;
  trace.after_ui_valid = 1u;
  ul_capture_ui_state(&trace.after_ui);
  ul_publish_trace(&trace);
  return result;
}

static probe_ul_remote_tracker *ul_find_remote_tracker(
    DWORD object, const probe_ul_remote_state *before, DWORD now,
    int *is_first) {
  size_t i;
  probe_ul_remote_tracker *free_slot = NULL;
  *is_first = 0;
  for (i = 0u; i < PROBE_UL_REMOTE_TRACKER_SIZE; ++i) {
    probe_ul_remote_tracker *tracker = &g_ul_remote_trackers[i];
    if (tracker->used && tracker->object == object) {
      return tracker;
    }
    if (!tracker->used && free_slot == NULL) {
      free_slot = tracker;
    }
  }
  if (free_slot == NULL) {
    InterlockedIncrement(&g_ul_remote_tracker_overflow);
    return NULL;
  }
  free_slot->object = object;
  free_slot->last_emit_tick = now;
  free_slot->afk_state = before->afk_state;
  free_slot->sync_state = before->sync_state;
  free_slot->used = 1u;
  *is_first = 1;
  return free_slot;
}

static void PROBE_UL_THISCALL hook_ul_remote_process(void *self) {
  probe_ul_trace trace;
  probe_ul_ui_state before_ui;
  probe_ul_remote_state before;
  probe_ul_remote_state after;
  probe_ul_remote_tracker *tracker;
  DWORD now = GetTickCount();
  DWORD reason = 0u;
  int is_first = 0;
  int heartbeat_due = 0;
  int capture_before_ui = 0;

  ul_capture_remote(self, &before, now);
  tracker =
      ul_find_remote_tracker((DWORD)(uintptr_t)self, &before, now, &is_first);
  if (tracker != NULL && !is_first &&
      (DWORD)(now - tracker->last_emit_tick) >=
          PROBE_UL_REMOTE_HEARTBEAT_MS) {
    heartbeat_due = 1;
  }
  capture_before_ui = is_first || heartbeat_due;
  if (capture_before_ui) {
    ul_capture_ui_state(&before_ui);
  }

  ((probe_ul_this_void_fn)
       g_ul_hooks[PROBE_UL_HOOK_REMOTE_PROCESS].trampoline)(self);
  ul_capture_remote(self, &after, GetTickCount());

  if (is_first) {
    reason |= PROBE_UL_REASON_BASELINE;
  }
  if (before.afk_state != after.afk_state ||
      before.sync_state != after.sync_state ||
      (tracker != NULL &&
       (tracker->afk_state != after.afk_state ||
        tracker->sync_state != after.sync_state))) {
    reason |= PROBE_UL_REASON_STATE_EDGE;
  }
  if (heartbeat_due) {
    reason |= PROBE_UL_REASON_HEARTBEAT;
  }
  if (reason == 0u) {
    return;
  }

  ul_begin_trace(&trace, PROBE_UL_EVENT_REMOTE_AFK, (BYTE)reason,
                 PROBE_UL_REMOTE_PROCESS_RVA, self, 0u, 0u,
                 __builtin_return_address(0));
  if (capture_before_ui) {
    trace.before_ui_valid = 1u;
    trace.before_ui = before_ui;
  }
  trace.remote_before = before;
  trace.remote_after = after;
  trace.elapsed_before = now - before.last_sync_tick;
  trace.elapsed_after = trace.tick - after.last_sync_tick;
  trace.value_before = before.afk_state;
  trace.value_after = after.afk_state;
  trace.aux_before = before.sync_state;
  trace.aux_after = after.sync_state;
  trace.after_ui_valid = 1u;
  ul_capture_ui_state(&trace.after_ui);
  ul_publish_trace(&trace);

  if (tracker != NULL) {
    tracker->last_emit_tick = trace.tick;
    tracker->afk_state = after.afk_state;
    tracker->sync_state = after.sync_state;
  }
}

static int ul_bytes_match(DWORD rva, const BYTE *bytes, size_t size) {
  return rva <= g_ul_samp_size &&
         size <= (size_t)(g_ul_samp_size - rva) &&
         ul_memory_is_readable(g_ul_samp_base + rva, size) &&
         memcmp((const void *)(g_ul_samp_base + rva), bytes, size) == 0;
}

typedef struct probe_ul_guard {
  DWORD rva;
  const BYTE *bytes;
  size_t size;
  int rebased_operand_offset;
} probe_ul_guard;

static int ul_guard_matches(const probe_ul_guard *guard) {
  BYTE expected[64];
  DWORD preferred_operand;
  DWORD rebased_operand;
  size_t offset;
  if (guard == NULL || guard->size > sizeof(expected)) {
    return 0;
  }
  memcpy(expected, guard->bytes, guard->size);
  if (guard->rebased_operand_offset >= 0) {
    offset = (size_t)guard->rebased_operand_offset;
    if (offset > guard->size || sizeof(DWORD) > guard->size - offset) {
      return 0;
    }
    memcpy(&preferred_operand, expected + offset, sizeof(preferred_operand));
    if (preferred_operand < PROBE_UL_R5_PREFERRED_BASE ||
        preferred_operand >=
            PROBE_UL_R5_PREFERRED_BASE + PROBE_UL_R5_IMAGE_SIZE) {
      return 0;
    }
    if (g_ul_samp_base >
        (uintptr_t)(0xffffffffu -
                    (preferred_operand - PROBE_UL_R5_PREFERRED_BASE))) {
      return 0;
    }
    rebased_operand =
        (DWORD)g_ul_samp_base +
        (preferred_operand - PROBE_UL_R5_PREFERRED_BASE);
    memcpy(expected + offset, &rebased_operand, sizeof(rebased_operand));
  }
  return ul_bytes_match(guard->rva, expected, guard->size);
}

static int ul_preflight(void) {
  static const BYTE chat_mode_tail[] = {
      0x75, 0x08, 0xc7, 0x41, 0x08, 0x02, 0x00, 0x00,
      0x00, 0xc3, 0x3b, 0xc2, 0x75, 0x08, 0xc7, 0x41,
      0x08, 0x00, 0x00, 0x00, 0x00, 0xc3, 0x83, 0xf8,
      0x02, 0x75, 0x03, 0x89, 0x51, 0x08, 0xc3};
  static const BYTE chat_open_tail[] = {
      0x89, 0x88, 0x22, 0x01, 0x00, 0x00, 0x5f, 0xc7,
      0x86, 0xe0, 0x14, 0x00, 0x00, 0x01, 0x00, 0x00,
      0x00, 0x5e, 0x83, 0xc4, 0x10, 0xc3};
  static const BYTE chat_close_tail[] = {
      0x8b, 0x0d, 0xac, 0xeb, 0x26, 0x10, 0x6a, 0x01,
      0x6a, 0x00, 0xe8, 0x34, 0x71, 0x03, 0x00, 0xc7,
      0x86, 0xe0, 0x14, 0x00, 0x00, 0x00, 0x00, 0x00,
      0x00, 0x5e, 0xc3};
  static const BYTE scoreboard_hide_tail[] = {
      0x8a, 0x44, 0x24, 0x08, 0x84, 0xc0, 0x74, 0x0f,
      0x8b, 0x0d, 0xac, 0xeb, 0x26, 0x10, 0x6a, 0x00,
      0x6a, 0x00, 0xe8, 0xd2, 0x1c, 0x03, 0x00, 0xc7,
      0x06, 0x00, 0x00, 0x00, 0x00, 0x5e, 0xc2, 0x04,
      0x00};
  static const BYTE scoreboard_show_tail[] = {
      0x8b, 0xce, 0xe8, 0x2a, 0xf9, 0xff, 0xff, 0x8b,
      0x0d, 0xac, 0xeb, 0x26, 0x10, 0x6a, 0x00, 0x6a,
      0x03, 0xe8, 0xdb, 0x12, 0x03, 0x00, 0xc7, 0x06,
      0x01, 0x00, 0x00, 0x00, 0x5e, 0xc3};
  static const BYTE cursor_restore_tail_a[] = {
      0x8b, 0x46, 0x65, 0x48, 0x89, 0x46, 0x65, 0x5f, 0x5e, 0xc3};
  static const BYTE cursor_restore_tail_b[] = {
      0x7e, 0x04, 0x48, 0x89, 0x46, 0x65, 0x5f, 0x5e, 0xc3};
  static const BYTE cursor_mode_tail_2[] = {
      0xc7, 0x46, 0x61, 0x02, 0x00, 0x00, 0x00,
      0x5f, 0x5e, 0x5d, 0xc2, 0x08, 0x00};
  static const BYTE cursor_mode_tail_1[] = {
      0x89, 0x7e, 0x61, 0x5f, 0x5e, 0x5d, 0xc2, 0x08, 0x00};
  static const BYTE cursor_mode_tail_3[] = {
      0xc7, 0x46, 0x61, 0x03, 0x00, 0x00, 0x00,
      0x5f, 0x5e, 0x5d, 0xc2, 0x08, 0x00};
  static const BYTE cursor_mode_tail_4[] = {
      0xc7, 0x46, 0x61, 0x04, 0x00, 0x00, 0x00,
      0x5f, 0x5e, 0x5d, 0xc2, 0x08, 0x00};
  static const BYTE cursor_mode_tail_0[] = {
      0x89, 0x7e, 0x61, 0x5f, 0x5e, 0x5d, 0xc2, 0x08, 0x00};
  static const BYTE menu_query_tail[] = {
      0x33, 0xc0, 0x85, 0xc9, 0x0f, 0x95, 0xc0, 0xc3};
  static const BYTE remote_onfoot_afk[] = {
      0x39, 0x9d, 0xc5, 0x01, 0x00, 0x00, 0x74, 0x1e,
      0x81, 0xfe, 0xb8, 0x0b, 0x00, 0x00, 0xeb, 0x0e,
      0x39, 0x9d, 0xc5, 0x01, 0x00, 0x00, 0x74, 0x0e,
      0x81, 0xfe, 0xdc, 0x05, 0x00, 0x00, 0x7c, 0x06,
      0x89, 0x9d, 0xc5, 0x01, 0x00, 0x00};
  static const BYTE remote_driver_afk[] = {
      0x39, 0x9d, 0xc5, 0x01, 0x00, 0x00, 0x74, 0x1e,
      0x81, 0xfe, 0xb8, 0x0b, 0x00, 0x00, 0xeb, 0x0e,
      0x39, 0x9d, 0xc5, 0x01, 0x00, 0x00, 0x74, 0x0e,
      0x81, 0xfe, 0xdc, 0x05, 0x00, 0x00, 0x7e, 0x06,
      0x89, 0x9d, 0xc5, 0x01, 0x00, 0x00};
  static const BYTE remote_passenger_afk[] = {
      0x39, 0x9d, 0xc5, 0x01, 0x00, 0x00, 0x74, 0x0e,
      0x81, 0xfe, 0xb8, 0x0b, 0x00, 0x00, 0x7c, 0x06,
      0x89, 0x9d, 0xc5, 0x01, 0x00, 0x00};
  static const BYTE remote_clear_afk_tail[] = {
      0x39, 0x9d, 0xc5, 0x01, 0x00, 0x00, 0x75, 0x3c,
      0x81, 0xfe, 0xdc, 0x05, 0x00, 0x00, 0x7d, 0x34,
      0x89, 0xbd, 0xc5, 0x01, 0x00, 0x00, 0x5f, 0x5e,
      0x5d, 0x5b, 0x81, 0xc4, 0x90, 0x00, 0x00, 0x00,
      0xc3};
  static const BYTE remote_final_tail[] = {
      0x5f, 0x5e, 0x5d, 0x5b, 0x81, 0xc4,
      0x90, 0x00, 0x00, 0x00, 0xc3};
  static const probe_ul_guard guards[] = {
      {0x000612d0u, chat_mode_tail, sizeof(chat_mode_tail), -1},
      {0x00069560u, chat_open_tail, sizeof(chat_open_tail), -1},
      {0x000695adu, chat_close_tail, sizeof(chat_close_tail), 2},
      {0x0006ea07u, scoreboard_hide_tail, sizeof(scoreboard_hide_tail), 10},
      {0x0006f3ffu, scoreboard_show_tail, sizeof(scoreboard_show_tail), 9},
      {0x000a06d8u, cursor_restore_tail_a, sizeof(cursor_restore_tail_a), -1},
      {0x000a06e2u, cursor_restore_tail_b, sizeof(cursor_restore_tail_b), -1},
      {0x000a0761u, cursor_mode_tail_2, sizeof(cursor_mode_tail_2), -1},
      {0x000a079eu, cursor_mode_tail_1, sizeof(cursor_mode_tail_1), -1},
      {0x000a07fau, cursor_mode_tail_3, sizeof(cursor_mode_tail_3), -1},
      {0x000a0849u, cursor_mode_tail_4, sizeof(cursor_mode_tail_4), -1},
      {0x000a087eu, cursor_mode_tail_0, sizeof(cursor_mode_tail_0), -1},
      {0x000a0926u, menu_query_tail, sizeof(menu_query_tail), -1},
      {0x00016da0u, remote_onfoot_afk, sizeof(remote_onfoot_afk), -1},
      {0x00016fe2u, remote_driver_afk, sizeof(remote_driver_afk), -1},
      {0x0001704eu, remote_passenger_afk, sizeof(remote_passenger_afk), -1},
      {0x000170d6u, remote_clear_afk_tail, sizeof(remote_clear_afk_tail), -1},
      {0x0001711au, remote_final_tail, sizeof(remote_final_tail), -1},
  };
  size_t i;
  for (i = 0u; i < sizeof(g_ul_hooks) / sizeof(g_ul_hooks[0]); ++i) {
    if (!ul_bytes_match(g_ul_hooks[i].rva, g_ul_hooks[i].expected,
                        g_ul_hooks[i].length)) {
      return 0;
    }
  }
  for (i = 0u; i < sizeof(guards) / sizeof(guards[0]); ++i) {
    if (!ul_guard_matches(&guards[i])) {
      return 0;
    }
  }
  return 1;
}

static int ul_rel32(void *from_after, void *to, LONG *relative) {
  intptr_t delta = (BYTE *)to - (BYTE *)from_after;
  if (delta < INT32_MIN || delta > INT32_MAX) {
    return 0;
  }
  *relative = (LONG)delta;
  return 1;
}

static int ul_prepare_trampoline(probe_ul_hook *hook) {
  BYTE *trampoline;
  LONG back_rel;
  uintptr_t target;
  if (hook == NULL || hook->length < 5u ||
      hook->length > sizeof(hook->saved)) {
    return 0;
  }
  target = g_ul_samp_base + hook->rva;
  trampoline = (BYTE *)VirtualAlloc(
      NULL, (SIZE_T)hook->length + 5u, MEM_COMMIT | MEM_RESERVE,
      PAGE_EXECUTE_READWRITE);
  if (trampoline == NULL) {
    return 0;
  }
  memcpy(hook->saved, (const void *)target, hook->length);
  memcpy(trampoline, hook->saved, hook->length);
  if (!ul_rel32(trampoline + hook->length + 5u,
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

static int ul_install_one(probe_ul_hook *hook) {
  uintptr_t target;
  BYTE patch[16];
  LONG replacement_rel;
  DWORD old_protect;
  DWORD ignored_protect;
  if (hook == NULL || hook->trampoline == NULL ||
      hook->length > sizeof(patch)) {
    return 0;
  }
  target = g_ul_samp_base + hook->rva;
  if (!ul_rel32((void *)(target + 5u), hook->replacement,
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
                       &ignored_protect);
  InterlockedExchange(&hook->installed, 1);
  return 1;
}

static int ul_patch_is_owned(const probe_ul_hook *hook) {
  BYTE expected[16];
  LONG relative;
  uintptr_t target;
  if (hook == NULL || hook->length > sizeof(expected)) {
    return 0;
  }
  target = g_ul_samp_base + hook->rva;
  if (!ul_rel32((void *)(target + 5u), hook->replacement, &relative)) {
    return 0;
  }
  memset(expected, 0x90, hook->length);
  expected[0] = 0xe9u;
  memcpy(expected + 1u, &relative, sizeof(relative));
  return ul_memory_is_readable(target, hook->length) &&
         memcmp((const void *)target, expected, hook->length) == 0;
}

static int ul_restore_one(probe_ul_hook *hook) {
  uintptr_t target;
  DWORD old_protect;
  DWORD ignored_protect;
  if (hook == NULL ||
      InterlockedCompareExchange(&hook->installed, 0, 0) != 1 ||
      !ul_patch_is_owned(hook)) {
    return 0;
  }
  target = g_ul_samp_base + hook->rva;
  if (!VirtualProtect((void *)target, hook->length,
                      PAGE_EXECUTE_READWRITE, &old_protect)) {
    return 0;
  }
  memcpy((void *)target, hook->saved, hook->length);
  FlushInstructionCache(GetCurrentProcess(), (const void *)target,
                        hook->length);
  (void)VirtualProtect((void *)target, hook->length, old_protect,
                       &ignored_protect);
  InterlockedExchange(&hook->installed, 0);
  return 1;
}

int probe_ui_latches_install(HMODULE samp_module, DWORD samp_size,
                             int enabled, int code_hooks_disabled,
                             probe_ui_latches_log_fn log_fn,
                             int log_summary) {
  HMODULE gta_module;
  size_t hook_count = sizeof(g_ul_hooks) / sizeof(g_ul_hooks[0]);
  size_t i;
  int installed = 0;

  if (!enabled) {
    if (log_summary && log_fn != NULL) {
      log_fn("ui_latches_hook: disabled by default; enable with "
             "SAMP_PROBE_UI_LATCHES_HOOKS=1 or "
             "samp_probe_ui_latches_hooks.flag");
    }
    return 0;
  }
  if (code_hooks_disabled) {
    if (log_summary && log_fn != NULL) {
      log_fn("ui_latches_hook: disabled by "
             "SAMP_PROBE_NO_SAMP_CODE_HOOKS");
    }
    return 0;
  }
  if (InterlockedCompareExchange(&g_ul_install_state, 0, 0) == 1) {
    return (int)hook_count;
  }
  if (InterlockedCompareExchange(&g_ul_install_state, 0, 0) < 0) {
    return 0;
  }

  g_ul_samp_base = (uintptr_t)samp_module;
  g_ul_samp_size = samp_size;
  gta_module = GetModuleHandleA(NULL);
  if (g_ul_samp_size != PROBE_UL_R5_IMAGE_SIZE ||
      !ul_pe_identity_matches(samp_module, PROBE_UL_R5_TIMESTAMP,
                              PROBE_UL_R5_ENTRY_RVA,
                              PROBE_UL_R5_IMAGE_SIZE,
                              PROBE_UL_R5_PREFERRED_BASE, 0u, 0, 0) ||
      (uintptr_t)gta_module != PROBE_UL_GTA_PREFERRED_BASE ||
      !ul_pe_identity_matches(gta_module, PROBE_UL_GTA_TIMESTAMP,
                              PROBE_UL_GTA_ENTRY_RVA,
                              PROBE_UL_GTA_IMAGE_SIZE,
                              PROBE_UL_GTA_PREFERRED_BASE,
                              PROBE_UL_GTA_CHECKSUM, 1, 1)) {
    if (log_summary && log_fn != NULL) {
      log_fn("ui_latches_hook: skip unsupported_identity installed=0 "
             "samp_base=0x%08lx samp_size=0x%08lx "
             "samp_delta=0x%08lx samp_sha256=%s "
             "gta_base=0x%08lx gta_sha256=%s "
             "evidence=STATIC_037",
             (unsigned long)g_ul_samp_base,
             (unsigned long)g_ul_samp_size,
             (unsigned long)(g_ul_samp_base -
                             PROBE_UL_R5_PREFERRED_BASE),
             PROBE_UL_R5_SHA256,
             (unsigned long)(uintptr_t)gta_module, PROBE_UL_GTA_SHA256);
    }
    InterlockedExchange(&g_ul_install_state, -1);
    return 0;
  }
  if (!ul_preflight()) {
    if (log_summary && log_fn != NULL) {
      log_fn("ui_latches_hook: skip preflight_mismatch installed=0 "
             "requested=%u evidence=STATIC_037",
             (unsigned)hook_count);
    }
    InterlockedExchange(&g_ul_install_state, -1);
    return 0;
  }

  for (i = 0u; i < hook_count; ++i) {
    if (!ul_prepare_trampoline(&g_ul_hooks[i])) {
      break;
    }
  }
  if (i != hook_count) {
    size_t j;
    for (j = 0u; j < hook_count; ++j) {
      if (g_ul_hooks[j].trampoline != NULL) {
        VirtualFree(g_ul_hooks[j].trampoline, 0u, MEM_RELEASE);
        g_ul_hooks[j].trampoline = NULL;
      }
    }
    if (log_summary && log_fn != NULL) {
      log_fn("ui_latches_hook: trampoline_allocation_failed "
             "prepared=%u requested=%u installed=0",
             (unsigned)i, (unsigned)hook_count);
    }
    InterlockedExchange(&g_ul_install_state, -1);
    return 0;
  }

  for (i = 0u; i < hook_count; ++i) {
    if (!ul_install_one(&g_ul_hooks[i])) {
      break;
    }
    ++installed;
  }
  if ((size_t)installed != hook_count) {
    while (installed > 0) {
      --installed;
      (void)ul_restore_one(&g_ul_hooks[installed]);
    }
    if (log_summary && log_fn != NULL) {
      log_fn("ui_latches_hook: incomplete_install installed=0 "
             "requested=%u run_invalid=1",
             (unsigned)hook_count);
    }
    InterlockedExchange(&g_ul_install_state, -1);
    return 0;
  }

  InterlockedExchange(&g_ul_install_state, 1);
  if (log_summary && log_fn != NULL) {
    log_fn("ui_latches_hook: summary installed=%u requested=%u "
           "rvas=0x612c0,0x69480,0x69580,0x6e9e0,0x6f3d0,"
           "0xa05d0,0xa06f0,0xa0920,0x166b0 "
           "samp_base=0x%08lx samp_delta=0x%08lx "
           "samp_sha256=%s gta_sha256=%s "
           "guard=identity,samp_relocation_normalized,gta_preferred_base,"
           "entry_bytes,critical_bytes,tails,all_or_nothing "
           "evidence=STATIC_037,TODO_VERIFY",
           (unsigned)hook_count, (unsigned)hook_count,
           (unsigned long)g_ul_samp_base,
           (unsigned long)(g_ul_samp_base - PROBE_UL_R5_PREFERRED_BASE),
           PROBE_UL_R5_SHA256, PROBE_UL_GTA_SHA256);
  }
  return (int)hook_count;
}

static const char *ul_event_name(BYTE kind) {
  switch (kind) {
  case PROBE_UL_EVENT_CHAT_MODE_TOGGLE:
    return "chat_mode_toggle";
  case PROBE_UL_EVENT_CHAT_OPEN:
    return "chat_open";
  case PROBE_UL_EVENT_CHAT_CLOSE:
    return "chat_close";
  case PROBE_UL_EVENT_SCOREBOARD_HIDE:
    return "scoreboard_hide";
  case PROBE_UL_EVENT_SCOREBOARD_SHOW:
    return "scoreboard_show";
  case PROBE_UL_EVENT_CURSOR_RESTORE:
    return "cursor_restore";
  case PROBE_UL_EVENT_CURSOR_MODE:
    return "cursor_mode";
  case PROBE_UL_EVENT_MENU_EDGE:
    return "menu_edge";
  case PROBE_UL_EVENT_REMOTE_AFK:
    return "remote_afk";
  default:
    return "unknown";
  }
}

static void ul_log_ui_state(probe_ui_latches_log_fn log_fn,
                            const probe_ul_trace *trace, const char *phase,
                            const probe_ul_ui_state *state) {
  log_fn(
      "ui_latch_state_r5: seq=%ld event=%ld phase=%s "
      "scoreboard=0x%08lx scoreboard_visible=0x%08lx "
      "chat_display=0x%08lx chat_mode=0x%08lx chat_dirty=0x%08lx "
      "chat=0x%08lx chat_active=0x%08lx game=0x%08lx "
      "cursor_mode_raw=0x%08lx cursor_restore_raw=0x%08lx "
      "frontend_raw=0x%08lx frontend_bytes=%02x,%02x,%02x "
      "pause_raw_b7cb49=%02x input_gate=%08lx,%02x "
      "mouse_gate=%02x foreground=0x%08lx focus=0x%08lx "
      "capture=0x%08lx cursor_flags=0x%08lx "
      "evidence=STATIC_037,WIN32_API,TODO_VERIFY",
      (long)trace->ring_seq, (long)trace->event_seq, phase,
      (unsigned long)state->scoreboard,
      (unsigned long)state->scoreboard_visible,
      (unsigned long)state->chat_display,
      (unsigned long)state->chat_display_mode,
      (unsigned long)state->chat_display_dirty,
      (unsigned long)state->chat, (unsigned long)state->chat_active,
      (unsigned long)state->game,
      (unsigned long)state->cursor_mode_raw,
      (unsigned long)state->cursor_restore_raw,
      (unsigned long)state->frontend_raw, (unsigned)state->frontend_a,
      (unsigned)state->frontend_b, (unsigned)state->frontend_c,
      (unsigned)state->pause_raw_b7cb49,
      (unsigned long)state->input_gate_head,
      (unsigned)state->input_gate_tail,
      (unsigned)state->mouse_gate_byte,
      (unsigned long)state->foreground_window,
      (unsigned long)state->focus_window,
      (unsigned long)state->capture_window,
      (unsigned long)state->cursor_flags);
}

void probe_ui_latches_flush(probe_ui_latches_log_fn log_fn) {
  LONG write_seq;
  LONG pending;
  LONG tracker_overflow;
  if (log_fn == NULL) {
    return;
  }

  tracker_overflow =
      InterlockedCompareExchange(&g_ul_remote_tracker_overflow, 0, 0);
  if (tracker_overflow != g_ul_remote_tracker_overflow_flushed) {
    log_fn("ui_latches_r5: remote_tracker_overflow total=%ld capacity=%u "
           "heartbeat_suppressed=1",
           (long)tracker_overflow, (unsigned)PROBE_UL_REMOTE_TRACKER_SIZE);
    g_ul_remote_tracker_overflow_flushed = tracker_overflow;
  }

  write_seq = InterlockedCompareExchange(&g_ul_trace_write_seq, 0, 0);
  pending = write_seq - g_ul_trace_flushed_seq;
  if (pending > (LONG)PROBE_UL_TRACE_RING_SIZE) {
    LONG skipped = pending - (LONG)PROBE_UL_TRACE_RING_SIZE;
    g_ul_trace_flushed_seq += skipped;
    g_ul_trace_overflow_count += skipped;
    log_fn("ui_latches_r5: overflow skipped=%ld total_skipped=%ld ring=%u",
           (long)skipped, (long)g_ul_trace_overflow_count,
           (unsigned)PROBE_UL_TRACE_RING_SIZE);
  }
  while (g_ul_trace_flushed_seq < write_seq) {
    LONG next_seq = g_ul_trace_flushed_seq + 1;
    probe_ul_trace *slot =
        &g_ul_trace_ring[
            ((DWORD)next_seq - 1u) % PROBE_UL_TRACE_RING_SIZE];
    probe_ul_trace trace;
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
    log_fn(
        "ui_latches_r5: seq=%ld event=%ld tick=%lu thread=%lu frame=%lu "
        "kind=%s reason=0x%02x caller=0x%08lx caller_rva=0x%08lx "
        "hook_rva=0x%08lx object=0x%08lx arg0=0x%08lx arg1=0x%08lx "
        "result=0x%08lx value=%08lx->%08lx aux=%08lx->%08lx "
        "remote_sync=%02x->%02x remote_afk=%08lx->%08lx "
        "remote_last_sync=%08lx->%08lx elapsed=%lu->%lu "
        "remote_ped=0x%08lx->0x%08lx "
        "evidence=STATIC_037,TODO_VERIFY",
        (long)trace.ring_seq, (long)trace.event_seq,
        (unsigned long)trace.tick, (unsigned long)trace.thread_id,
        (unsigned long)trace.gta_frame, ul_event_name(trace.kind),
        (unsigned)trace.reason, (unsigned long)trace.caller,
        (unsigned long)trace.caller_rva,
        (unsigned long)trace.hook_rva, (unsigned long)trace.object,
        (unsigned long)trace.arg0, (unsigned long)trace.arg1,
        (unsigned long)trace.result, (unsigned long)trace.value_before,
        (unsigned long)trace.value_after,
        (unsigned long)trace.aux_before,
        (unsigned long)trace.aux_after,
        (unsigned)trace.remote_before.sync_state,
        (unsigned)trace.remote_after.sync_state,
        (unsigned long)trace.remote_before.afk_state,
        (unsigned long)trace.remote_after.afk_state,
        (unsigned long)trace.remote_before.last_sync_tick,
        (unsigned long)trace.remote_after.last_sync_tick,
        (unsigned long)trace.elapsed_before,
        (unsigned long)trace.elapsed_after,
        (unsigned long)trace.remote_before.ped_wrapper,
        (unsigned long)trace.remote_after.ped_wrapper);
    if (trace.before_ui_valid) {
      ul_log_ui_state(log_fn, &trace, "pre", &trace.before_ui);
    }
    if (trace.after_ui_valid) {
      ul_log_ui_state(log_fn, &trace, "post", &trace.after_ui);
    }
    g_ul_trace_flushed_seq = next_seq;
  }
}

void probe_ui_latches_uninstall(probe_ui_latches_log_fn log_fn) {
  size_t hook_count = sizeof(g_ul_hooks) / sizeof(g_ul_hooks[0]);
  size_t i;
  int restored = 0;
  if (InterlockedCompareExchange(&g_ul_install_state, 0, 0) != 1) {
    return;
  }
  for (i = hook_count; i > 0u; --i) {
    restored += ul_restore_one(&g_ul_hooks[i - 1u]);
  }
  if (log_fn != NULL) {
    log_fn("ui_latches_hook: restore restored=%d requested=%u "
           "gateway_lifetime=process",
           restored, (unsigned)hook_count);
  }
  InterlockedExchange(&g_ul_install_state,
                      restored == (int)hook_count ? 0 : -1);
}
