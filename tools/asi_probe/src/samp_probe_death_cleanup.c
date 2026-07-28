#include "samp_probe_death_cleanup.h"

#include <stdint.h>
#include <string.h>

#if defined(__GNUC__) && defined(__i386__)
#define PROBE_DC_THISCALL __attribute__((thiscall))
#else
#define PROBE_DC_THISCALL
#endif

/*
 * STATIC_037 + TODO_VERIFY:
 * All SA-MP RVAs, entry/tail guards, and field offsets below were recovered
 * from original R5 SHA256=b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2.
 * GTA absolute addresses are restricted to 1.0 US
 * SHA256=a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26.
 * See docs/re/death_cleanup_memory_probe_r5_20260728.md.
 */
#define PROBE_DC_R5_TIMESTAMP 0x6372c39eu
#define PROBE_DC_R5_ENTRY_RVA 0x000cbc90u
#define PROBE_DC_R5_IMAGE_SIZE 0x0027e000u
#define PROBE_DC_R5_PREFERRED_BASE 0x10000000u
#define PROBE_DC_R5_SHA256                                                   \
  "b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2"

#define PROBE_DC_GTA_TIMESTAMP 0x427101cau
#define PROBE_DC_GTA_ENTRY_RVA 0x00424570u
#define PROBE_DC_GTA_IMAGE_SIZE 0x01177000u
#define PROBE_DC_GTA_CHECKSUM 0x00dc5beau
#define PROBE_DC_GTA_PREFERRED_BASE 0x00400000u
#define PROBE_DC_GTA_SHA256                                                  \
  "a559aa772fd136379155efa71f00c47aad34bbfeae6196b0fe1047d0645cbd26"

#define PROBE_DC_LOCAL_PROCESS_RVA 0x000074c0u
#define PROBE_DC_LOCAL_SPAWN_RVA 0x00003c20u
#define PROBE_DC_LOCAL_CLASS_SELECTION_RVA 0x00004080u
#define PROBE_DC_NETGAME_GMX_RESET_RVA 0x0000a540u
#define PROBE_DC_NETGAME_CONNECTION_LOST_RVA 0x0000acf0u
#define PROBE_DC_NETGAME_DESTRUCTOR_RVA 0x00009880u
#define PROBE_DC_CLEAN_QUIT_DESTRUCTOR_CALLER_RVA 0x000c507bu
#define PROBE_DC_EXITPROCESS_CALLSITE_RVA 0x000c508au
#define PROBE_DC_EXITPROCESS_CALLER_RVA 0x000c5091u
#define PROBE_DC_EXITPROCESS_IAT_RVA 0x000e5188u
#define PROBE_DC_TERMINAL_DRAIN_TIMEOUT_MS 1500u

#define PROBE_DC_NETGAME_PTR_RVA 0x0026eb94u
#define PROBE_DC_SCOREBOARD_PTR_RVA 0x0026eb4cu
#define PROBE_DC_DIALOG_PTR_RVA 0x0026eb50u
#define PROBE_DC_TEXTDRAW_SELECTOR_PTR_RVA 0x0026eb54u
#define PROBE_DC_CHAT_PTR_RVA 0x0026eb84u
#define PROBE_DC_GAME_PTR_RVA 0x0026ebacu
#define PROBE_DC_CLASS_GUI_PTR_RVA 0x0026ec2cu
#define PROBE_DC_REMOVE_BUILDING_COUNT_RVA 0x0014fd88u

#define PROBE_DC_NETGAME_STATE_OFFSET 0x000003cdu
#define PROBE_DC_NETGAME_POOLS_OFFSET 0x000003deu
#define PROBE_DC_PLAYER_POOL_LOCAL_OFFSET 0x00000026u
#define PROBE_DC_PLAYER_POOL_REMOTE_AUX_OFFSET 0x0000002au
#define PROBE_DC_PLAYER_POOL_REMOTE_WRAPPER_OFFSET 0x00001f8au
#define PROBE_DC_REMOTE_PLAYER_CAPACITY 1004u

#define PROBE_DC_LOCAL_ACTIVE_OFFSET 0x000000f0u
#define PROBE_DC_LOCAL_WASTED_OFFSET 0x000000f4u
#define PROBE_DC_LOCAL_PED_WRAPPER_OFFSET 0x00000104u
#define PROBE_DC_LOCAL_SPECTATING_OFFSET 0x00000108u
#define PROBE_DC_LOCAL_CLEARED_TO_SPAWN_OFFSET 0x00000143u
#define PROBE_DC_LOCAL_CLASS_TICK_A_OFFSET 0x00000147u
#define PROBE_DC_LOCAL_CLASS_TICK_B_OFFSET 0x0000014bu
#define PROBE_DC_LOCAL_SPAWN_INFO_OFFSET 0x0000014fu
#define PROBE_DC_LOCAL_SPAWN_INFO_SIZE 46u
#define PROBE_DC_LOCAL_HAS_SPAWN_INFO_OFFSET 0x0000017du
#define PROBE_DC_LOCAL_WANTS_CLASS_OFFSET 0x000002fau
#define PROBE_DC_LOCAL_CLASS_SELECTION_OFFSET 0x00000302u
#define PROBE_DC_LOCAL_CLASS_INPUT_OFFSET 0x00000306u
#define PROBE_DC_LOCAL_CLASS_TICK_C_OFFSET 0x0000030au
#define PROBE_DC_LOCAL_VEHICLE_OFFSET 0x00000310u
#define PROBE_DC_LOCAL_SIZE 0x00000324u

#define PROBE_DC_PLAYER_PED_GTA_PED_OFFSET 0x000002a4u
#define PROBE_DC_GTA_ENTITY_MATRIX_OFFSET 0x00000014u
#define PROBE_DC_GTA_ENTITY_RW_OBJECT_OFFSET 0x00000018u
#define PROBE_DC_GTA_ENTITY_FLAGS_OFFSET 0x0000001cu
#define PROBE_DC_GTA_ENTITY_STATUS_OFFSET 0x00000036u
#define PROBE_DC_GTA_PED_FLAGS_OFFSET 0x0000046cu
#define PROBE_DC_GTA_PED_INTELLIGENCE_OFFSET 0x0000047cu
#define PROBE_DC_GTA_PED_ACTION_OFFSET 0x00000530u
#define PROBE_DC_GTA_PED_HEALTH_OFFSET 0x00000540u
#define PROBE_DC_GTA_PED_STATE_OFFSET 0x00000598u
#define PROBE_DC_GTA_PED_MIN_CAPTURE_SIZE 0x0000059cu
#define PROBE_DC_GTA_TASK_ROOTS_OFFSET 0x00000004u
#define PROBE_DC_GTA_TASK_ROOT_COUNT 11u

#define PROBE_DC_GTA_FRAME_COUNTER_ADDR 0x00b7cb4cu
#define PROBE_DC_GTA_CAMERA_MODE_ADDR 0x00b6f1a8u
#define PROBE_DC_GTA_CAMERA_MODE2_ADDR 0x00b6f858u
#define PROBE_DC_GTA_FRONTEND_STATE_A_ADDR 0x00ba67a4u
#define PROBE_DC_GTA_FRONTEND_STATE_B_ADDR 0x00ba67a5u
#define PROBE_DC_GTA_FRONTEND_STATE_C_ADDR 0x00ba67a6u

#define PROBE_DC_POOLS_VEHICLE_OFFSET 0x00u
#define PROBE_DC_POOLS_PLAYER_OFFSET 0x04u
#define PROBE_DC_POOLS_PICKUP_OFFSET 0x08u
#define PROBE_DC_POOLS_OBJECT_OFFSET 0x0cu
#define PROBE_DC_POOLS_ACTOR_OFFSET 0x10u
#define PROBE_DC_POOLS_GANGZONE_OFFSET 0x14u
#define PROBE_DC_POOLS_TEXTDRAW_OFFSET 0x18u
#define PROBE_DC_POOLS_LABEL_OFFSET 0x1cu
#define PROBE_DC_POOLS_MENU_OFFSET 0x20u

#define PROBE_DC_VEHICLE_WRAPPERS_OFFSET 0x00001134u
#define PROBE_DC_VEHICLE_LISTED_OFFSET 0x00003074u
#define PROBE_DC_VEHICLE_CAPACITY 2000u
#define PROBE_DC_VEHICLE_WRAPPER_ENTITY_OFFSET 0x00000040u
#define PROBE_DC_VEHICLE_WRAPPER_GTA_OFFSET 0x0000004cu
#define PROBE_DC_PICKUP_HANDLE_OFFSET 0x00000004u
#define PROBE_DC_PICKUP_SERVER_ID_OFFSET 0x00004004u
#define PROBE_DC_PICKUP_TIMER_OFFSET 0x00008004u
#define PROBE_DC_PICKUP_CAPACITY 4096u
#define PROBE_DC_OBJECT_WRAPPERS_OFFSET 0x00000004u
#define PROBE_DC_OBJECT_LISTED_OFFSET 0x00000fa4u
#define PROBE_DC_OBJECT_CAPACITY 1000u
#define PROBE_DC_ACTOR_WRAPPERS_OFFSET 0x00000004u
#define PROBE_DC_ACTOR_LISTED_OFFSET 0x00000fa4u
#define PROBE_DC_ACTOR_GTA_PED_OFFSET 0x00001f44u
#define PROBE_DC_ACTOR_CAPACITY 1000u
#define PROBE_DC_GANGZONE_LISTED_OFFSET 0x00001000u
#define PROBE_DC_GANGZONE_CAPACITY 1024u
#define PROBE_DC_TEXTDRAW_LISTED_OFFSET 0x0000e800u
#define PROBE_DC_TEXTDRAW_CAPACITY 2048u
#define PROBE_DC_LABEL_LISTED_OFFSET 0x00002400u
#define PROBE_DC_LABEL_CAPACITY 2304u
#define PROBE_DC_MENU_LISTED_OFFSET 0x00000200u
#define PROBE_DC_MENU_CURRENT_OFFSET 0x00000400u
#define PROBE_DC_MENU_CAPACITY 128u

#define PROBE_DC_CHAT_ACTIVE_OFFSET 0x000014e0u
#define PROBE_DC_SCOREBOARD_VISIBLE_OFFSET 0x00000000u
#define PROBE_DC_DIALOG_ACTIVE_OFFSET 0x00000028u
#define PROBE_DC_TEXTDRAW_ACTIVE_OFFSET 0x00000024u
#define PROBE_DC_CLASS_GUI_VISIBLE_OFFSET 0x00000013u
#define PROBE_DC_GAME_INPUT_DEPTH_A_OFFSET 0x00000061u
#define PROBE_DC_GAME_INPUT_DEPTH_B_OFFSET 0x00000065u

#define PROBE_DC_TRACE_RING_SIZE 256u
#define PROBE_DC_PROCESS_HEARTBEAT_MS 1000u

#define PROBE_DC_EVENT_PROCESS 1u
#define PROBE_DC_EVENT_SPAWN 2u
#define PROBE_DC_EVENT_CLASS_SELECTION 3u
#define PROBE_DC_EVENT_GMX_RESET 4u
#define PROBE_DC_EVENT_CONNECTION_LOST 5u
#define PROBE_DC_EVENT_QUIT_DESTRUCTOR 6u

typedef int(PROBE_DC_THISCALL *probe_dc_local_int_fn)(void *self);
typedef void(PROBE_DC_THISCALL *probe_dc_local_void_fn)(void *self);
typedef void(PROBE_DC_THISCALL *probe_dc_net_void_fn)(void *self);
typedef void(PROBE_DC_THISCALL *probe_dc_net_packet_fn)(void *self,
                                                        void *packet);
typedef VOID(WINAPI *probe_dc_exit_process_fn)(UINT exit_code);

typedef struct probe_dc_local_state {
  DWORD valid_mask;
  DWORD netgame;
  DWORD netgame_state;
  DWORD pools;
  DWORD player_pool;
  DWORD local_player;
  DWORD ped_wrapper;
  DWORD gta_ped;
  DWORD active;
  DWORD wasted;
  DWORD spectating;
  DWORD cleared_to_spawn;
  DWORD has_spawn_info;
  DWORD wants_another_class;
  DWORD class_selection;
  DWORD class_input_owned;
  DWORD class_tick_a;
  DWORD class_tick_b;
  DWORD class_tick_c;
  DWORD current_vehicle;
  DWORD spawn_info_hash;
  DWORD spawn_info_head[4];
  DWORD ped_matrix;
  DWORD ped_rw_object;
  DWORD ped_entity_flags;
  DWORD ped_flags;
  DWORD ped_state;
  DWORD ped_intelligence;
  DWORD ped_health_bits;
  DWORD task_roots[PROBE_DC_GTA_TASK_ROOT_COUNT];
  DWORD scoreboard;
  DWORD scoreboard_visible;
  DWORD dialog;
  DWORD dialog_active;
  DWORD textdraw_selector;
  DWORD textdraw_active;
  DWORD chat;
  DWORD chat_active;
  DWORD class_gui;
  DWORD class_gui_visible;
  DWORD game;
  DWORD game_input_depth_a;
  DWORD game_input_depth_b;
  WORD camera_mode2;
  BYTE action;
  BYTE entity_status;
  BYTE camera_mode;
  BYTE frontend_a;
  BYTE frontend_b;
  BYTE frontend_c;
} probe_dc_local_state;

typedef struct probe_dc_cleanup_state {
  DWORD valid_mask;
  DWORD netgame;
  DWORD pools;
  DWORD pool_ptrs[9];
  DWORD vehicle_listed;
  DWORD vehicle_wrappers;
  DWORD remote_aux;
  DWORD remote_wrappers;
  DWORD pickup_handles;
  DWORD pickup_server_ids;
  DWORD pickup_timers;
  DWORD object_listed;
  DWORD object_wrappers;
  DWORD actor_listed;
  DWORD actor_wrappers;
  DWORD gangzone_listed;
  DWORD textdraw_listed;
  DWORD label_listed;
  DWORD menu_listed;
  DWORD menu_current;
  DWORD remove_building_count;
  DWORD first_vehicle_id;
  DWORD first_vehicle_wrapper;
  DWORD first_vehicle_entity;
  DWORD first_vehicle_gta;
  DWORD first_vehicle_matrix;
  DWORD first_vehicle_rw_object;
  DWORD first_vehicle_flags;
  DWORD first_object_id;
  DWORD first_object_wrapper;
  DWORD first_actor_id;
  DWORD first_actor_wrapper;
  DWORD first_actor_gta_ped;
} probe_dc_cleanup_state;

typedef struct probe_dc_trace {
  volatile LONG committed_seq;
  LONG ring_seq;
  LONG event_seq;
  DWORD tick;
  DWORD thread_id;
  DWORD gta_frame;
  DWORD caller_rva;
  DWORD hook_rva;
  DWORD object;
  DWORD argument;
  DWORD result;
  BYTE kind;
  BYTE cleanup_valid;
  probe_dc_local_state before_local;
  probe_dc_local_state after_local;
  probe_dc_cleanup_state before_cleanup;
  probe_dc_cleanup_state after_cleanup;
} probe_dc_trace;

typedef struct probe_dc_hook {
  const char *name;
  DWORD rva;
  const BYTE *expected;
  BYTE length;
  void *replacement;
  void *trampoline;
  BYTE saved[16];
  volatile LONG installed;
} probe_dc_hook;

static uintptr_t g_dc_samp_base;
static DWORD g_dc_samp_size;
static volatile LONG g_dc_install_state;
static probe_dc_trace g_dc_trace_ring[PROBE_DC_TRACE_RING_SIZE];
static volatile LONG g_dc_trace_write_seq;
static LONG g_dc_trace_flushed_seq;
static LONG g_dc_trace_overflow_count;
static volatile LONG g_dc_event_seq;
static probe_dc_local_state g_dc_last_process_state;
static DWORD g_dc_last_process_tick;
static LONG g_dc_last_process_valid;
static DWORD g_dc_spawn_runtime_operand;
static DWORD g_dc_exit_runtime_iat_operand;
static probe_dc_exit_process_fn g_dc_original_exit_process;
static HANDLE g_dc_terminal_stop_event;
static HANDLE g_dc_terminal_done_event;
static volatile LONG g_dc_exit_iat_installed;
static volatile LONG g_dc_terminal_state;
static volatile LONG g_dc_clean_quit_destructor_seq;
static DWORD g_dc_terminal_exit_code;
static DWORD g_dc_terminal_caller_rva;
static DWORD g_dc_terminal_thread_id;
static DWORD g_dc_terminal_tick;
static DWORD g_dc_terminal_netgame;
static LONG g_dc_terminal_requested_seq;

static const BYTE g_dc_process_entry[] = {
    0x83, 0xec, 0x10, 0x53, 0x55, 0x56, 0x8b, 0xf1};
static const BYTE g_dc_spawn_entry[] = {
    0x64, 0xa1, 0x00, 0x00, 0x00, 0x00, 0x6a,
    0xff, 0x68, 0x0b, 0xff, 0x0d, 0x10};
static const BYTE g_dc_class_entry[] = {
    0x56, 0x8b, 0xf1, 0x8b, 0x8e, 0x04, 0x01, 0x00, 0x00};
static const BYTE g_dc_gmx_entry[] = {
    0x53, 0x55, 0x56, 0x57, 0x33, 0xdb,
    0x33, 0xff, 0x8b, 0xf1, 0x33, 0xed};
static const BYTE g_dc_lost_entry[] = {
    0x57, 0x8b, 0xf9, 0x8b, 0x0f, 0x85, 0xc9};
static const BYTE g_dc_destructor_entry[] = {
    0x53, 0x56, 0x57, 0x8b, 0xf1, 0x8b, 0x0e};
static const BYTE g_dc_exit_callsite[] = {
    0x57, 0xff, 0x15, 0x88, 0x51, 0x0e,
    0x10, 0x61, 0x5f, 0x5e, 0x5b, 0xc3};

static int PROBE_DC_THISCALL hook_dc_local_process(void *self);
static int PROBE_DC_THISCALL hook_dc_local_spawn(void *self);
static void PROBE_DC_THISCALL hook_dc_class_selection(void *self);
static void PROBE_DC_THISCALL hook_dc_gmx_reset(void *self);
static void PROBE_DC_THISCALL hook_dc_connection_lost(void *self,
                                                       void *packet);
static void PROBE_DC_THISCALL hook_dc_destructor(void *self);
static VOID WINAPI hook_dc_exit_process(UINT exit_code);

static probe_dc_hook g_dc_hooks[] = {
    {"CLocalPlayer::Process", PROBE_DC_LOCAL_PROCESS_RVA,
     g_dc_process_entry, (BYTE)sizeof(g_dc_process_entry),
     (void *)hook_dc_local_process, NULL, {0}, 0},
    {"CLocalPlayer::Spawn", PROBE_DC_LOCAL_SPAWN_RVA,
     g_dc_spawn_entry, (BYTE)sizeof(g_dc_spawn_entry),
     (void *)hook_dc_local_spawn, NULL, {0}, 0},
    {"CLocalPlayer::HandleClassSelection",
     PROBE_DC_LOCAL_CLASS_SELECTION_RVA, g_dc_class_entry,
     (BYTE)sizeof(g_dc_class_entry), (void *)hook_dc_class_selection,
     NULL, {0}, 0},
    {"CNetGame::ShutdownForGameModeRestart",
     PROBE_DC_NETGAME_GMX_RESET_RVA, g_dc_gmx_entry,
     (BYTE)sizeof(g_dc_gmx_entry), (void *)hook_dc_gmx_reset,
     NULL, {0}, 0},
    {"CNetGame::Packet_ConnectionLost",
     PROBE_DC_NETGAME_CONNECTION_LOST_RVA, g_dc_lost_entry,
     (BYTE)sizeof(g_dc_lost_entry), (void *)hook_dc_connection_lost,
     NULL, {0}, 0},
    {"CNetGame::~CNetGame", PROBE_DC_NETGAME_DESTRUCTOR_RVA,
     g_dc_destructor_entry, (BYTE)sizeof(g_dc_destructor_entry),
     (void *)hook_dc_destructor, NULL, {0}, 0},
};

static int dc_memory_is_readable(uintptr_t address, size_t size) {
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

static DWORD dc_read_u32(uintptr_t address, DWORD fallback) {
  DWORD value;
  if (!dc_memory_is_readable(address, sizeof(value))) {
    return fallback;
  }
  memcpy(&value, (const void *)address, sizeof(value));
  return value;
}

static BYTE dc_read_u8(uintptr_t address, BYTE fallback) {
  BYTE value;
  if (!dc_memory_is_readable(address, sizeof(value))) {
    return fallback;
  }
  memcpy(&value, (const void *)address, sizeof(value));
  return value;
}

static DWORD dc_load_u32(uintptr_t address) {
  DWORD value;
  memcpy(&value, (const void *)address, sizeof(value));
  return value;
}

static BYTE dc_load_u8(uintptr_t address) {
  BYTE value;
  memcpy(&value, (const void *)address, sizeof(value));
  return value;
}

static DWORD dc_fnv1a(const BYTE *data, size_t size) {
  DWORD hash = 2166136261u;
  size_t i;
  for (i = 0u; i < size; ++i) {
    hash ^= data[i];
    hash *= 16777619u;
  }
  return hash;
}

static DWORD dc_count_u32(uintptr_t address, DWORD capacity,
                          DWORD ignored_value, int count_not_equal) {
  const DWORD *values;
  DWORD count = 0u;
  DWORD i;
  if (capacity == 0u ||
      !dc_memory_is_readable(address, (size_t)capacity * sizeof(DWORD))) {
    return 0xffffffffu;
  }
  values = (const DWORD *)address;
  for (i = 0u; i < capacity; ++i) {
    if (count_not_equal ? values[i] != ignored_value
                        : values[i] == ignored_value) {
      ++count;
    }
  }
  return count;
}

static DWORD dc_find_first_pair(uintptr_t listed_address,
                                uintptr_t pointer_address, DWORD capacity,
                                DWORD *pointer_value) {
  const DWORD *listed;
  const DWORD *pointers;
  DWORD i;
  if (pointer_value != NULL) {
    *pointer_value = 0u;
  }
  if (!dc_memory_is_readable(
          listed_address, (size_t)capacity * sizeof(DWORD)) ||
      !dc_memory_is_readable(
          pointer_address, (size_t)capacity * sizeof(DWORD))) {
    return 0xffffffffu;
  }
  listed = (const DWORD *)listed_address;
  pointers = (const DWORD *)pointer_address;
  for (i = 0u; i < capacity; ++i) {
    if (listed[i] != 0u || pointers[i] != 0u) {
      if (pointer_value != NULL) {
        *pointer_value = pointers[i];
      }
      return i;
    }
  }
  return 0xffffffffu;
}

static int dc_pe_identity_matches(HMODULE module, DWORD timestamp,
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
  if (!dc_memory_is_readable((uintptr_t)dos, sizeof(*dos)) ||
      dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0 ||
      (DWORD)dos->e_lfanew >
          image_size - (DWORD)sizeof(IMAGE_NT_HEADERS)) {
    return 0;
  }
  nt = (PIMAGE_NT_HEADERS)((BYTE *)module + dos->e_lfanew);
  if (!dc_memory_is_readable((uintptr_t)nt, sizeof(*nt)) ||
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

static DWORD dc_caller_rva(void *caller) {
  uintptr_t value = (uintptr_t)caller;
  if (g_dc_samp_base == 0u || value < g_dc_samp_base ||
      value >= g_dc_samp_base + g_dc_samp_size) {
    return 0xffffffffu;
  }
  return (DWORD)(value - g_dc_samp_base);
}

static void dc_capture_ui(probe_dc_local_state *state) {
  uintptr_t pointer;
  state->scoreboard =
      dc_load_u32(g_dc_samp_base + PROBE_DC_SCOREBOARD_PTR_RVA);
  pointer = (uintptr_t)state->scoreboard;
  state->scoreboard_visible =
      dc_read_u32(pointer + PROBE_DC_SCOREBOARD_VISIBLE_OFFSET, 0xffffffffu);

  state->dialog =
      dc_load_u32(g_dc_samp_base + PROBE_DC_DIALOG_PTR_RVA);
  pointer = (uintptr_t)state->dialog;
  state->dialog_active =
      dc_read_u32(pointer + PROBE_DC_DIALOG_ACTIVE_OFFSET, 0xffffffffu);

  state->textdraw_selector =
      dc_load_u32(g_dc_samp_base + PROBE_DC_TEXTDRAW_SELECTOR_PTR_RVA);
  pointer = (uintptr_t)state->textdraw_selector;
  state->textdraw_active =
      dc_read_u32(pointer + PROBE_DC_TEXTDRAW_ACTIVE_OFFSET, 0xffffffffu);

  state->chat = dc_load_u32(g_dc_samp_base + PROBE_DC_CHAT_PTR_RVA);
  pointer = (uintptr_t)state->chat;
  state->chat_active =
      dc_read_u32(pointer + PROBE_DC_CHAT_ACTIVE_OFFSET, 0xffffffffu);

  state->class_gui =
      dc_load_u32(g_dc_samp_base + PROBE_DC_CLASS_GUI_PTR_RVA);
  pointer = (uintptr_t)state->class_gui;
  state->class_gui_visible =
      dc_read_u8(pointer + PROBE_DC_CLASS_GUI_VISIBLE_OFFSET, 0xffu);

  state->game = dc_load_u32(g_dc_samp_base + PROBE_DC_GAME_PTR_RVA);
  pointer = (uintptr_t)state->game;
  state->game_input_depth_a =
      dc_read_u32(pointer + PROBE_DC_GAME_INPUT_DEPTH_A_OFFSET, 0xffffffffu);
  state->game_input_depth_b =
      dc_read_u32(pointer + PROBE_DC_GAME_INPUT_DEPTH_B_OFFSET, 0xffffffffu);

  state->camera_mode = dc_load_u8(PROBE_DC_GTA_CAMERA_MODE_ADDR);
  memcpy(&state->camera_mode2,
         (const void *)PROBE_DC_GTA_CAMERA_MODE2_ADDR,
         sizeof(state->camera_mode2));
  state->frontend_a = dc_load_u8(PROBE_DC_GTA_FRONTEND_STATE_A_ADDR);
  state->frontend_b = dc_load_u8(PROBE_DC_GTA_FRONTEND_STATE_B_ADDR);
  state->frontend_c = dc_load_u8(PROBE_DC_GTA_FRONTEND_STATE_C_ADDR);
}

static void dc_capture_local(DWORD local_override, DWORD netgame_override,
                             probe_dc_local_state *state) {
  uintptr_t local;
  uintptr_t wrapper;
  uintptr_t ped;
  uintptr_t intelligence;
  BYTE spawn_info[PROBE_DC_LOCAL_SPAWN_INFO_SIZE];

  memset(state, 0, sizeof(*state));
  state->camera_mode = 0xffu;
  state->camera_mode2 = 0xffffu;
  state->frontend_a = 0xffu;
  state->frontend_b = 0xffu;
  state->frontend_c = 0xffu;
  state->netgame_state = 0xffffffffu;
  state->netgame = netgame_override != 0u
                       ? netgame_override
                       : dc_load_u32(g_dc_samp_base +
                                     PROBE_DC_NETGAME_PTR_RVA);
  if (state->netgame != 0u &&
      dc_memory_is_readable((uintptr_t)state->netgame,
                            PROBE_DC_NETGAME_POOLS_OFFSET +
                                sizeof(DWORD))) {
    state->valid_mask |= 0x01u;
    state->netgame_state =
        dc_load_u32((uintptr_t)state->netgame +
                    PROBE_DC_NETGAME_STATE_OFFSET);
    state->pools =
        dc_load_u32((uintptr_t)state->netgame +
                    PROBE_DC_NETGAME_POOLS_OFFSET);
  }
  if (state->pools != 0u) {
    state->player_pool =
        dc_read_u32((uintptr_t)state->pools +
                        PROBE_DC_POOLS_PLAYER_OFFSET,
                    0u);
  }
  state->local_player = local_override;
  if (state->local_player == 0u && state->player_pool != 0u) {
    state->local_player =
        dc_read_u32((uintptr_t)state->player_pool +
                        PROBE_DC_PLAYER_POOL_LOCAL_OFFSET,
                    0u);
  }
  local = (uintptr_t)state->local_player;
  if (local != 0u && dc_memory_is_readable(local, PROBE_DC_LOCAL_SIZE)) {
    state->valid_mask |= 0x02u;
    state->active = dc_load_u32(local + PROBE_DC_LOCAL_ACTIVE_OFFSET);
    state->wasted = dc_load_u32(local + PROBE_DC_LOCAL_WASTED_OFFSET);
    state->ped_wrapper =
        dc_load_u32(local + PROBE_DC_LOCAL_PED_WRAPPER_OFFSET);
    state->spectating =
        dc_load_u32(local + PROBE_DC_LOCAL_SPECTATING_OFFSET);
    state->cleared_to_spawn =
        dc_load_u32(local + PROBE_DC_LOCAL_CLEARED_TO_SPAWN_OFFSET);
    state->has_spawn_info =
        dc_load_u32(local + PROBE_DC_LOCAL_HAS_SPAWN_INFO_OFFSET);
    state->wants_another_class =
        dc_load_u32(local + PROBE_DC_LOCAL_WANTS_CLASS_OFFSET);
    state->class_selection =
        dc_load_u32(local + PROBE_DC_LOCAL_CLASS_SELECTION_OFFSET);
    state->class_input_owned =
        dc_load_u32(local + PROBE_DC_LOCAL_CLASS_INPUT_OFFSET);
    state->class_tick_a =
        dc_load_u32(local + PROBE_DC_LOCAL_CLASS_TICK_A_OFFSET);
    state->class_tick_b =
        dc_load_u32(local + PROBE_DC_LOCAL_CLASS_TICK_B_OFFSET);
    state->class_tick_c =
        dc_load_u32(local + PROBE_DC_LOCAL_CLASS_TICK_C_OFFSET);
    state->current_vehicle =
        dc_load_u32(local + PROBE_DC_LOCAL_VEHICLE_OFFSET);
    memcpy(spawn_info,
           (const void *)(local + PROBE_DC_LOCAL_SPAWN_INFO_OFFSET),
           sizeof(spawn_info));
    state->spawn_info_hash = dc_fnv1a(spawn_info, sizeof(spawn_info));
    memcpy(state->spawn_info_head, spawn_info,
           sizeof(state->spawn_info_head));
  }

  wrapper = (uintptr_t)state->ped_wrapper;
  if (wrapper != 0u &&
      dc_memory_is_readable(
          wrapper, PROBE_DC_PLAYER_PED_GTA_PED_OFFSET + sizeof(DWORD))) {
    state->valid_mask |= 0x04u;
    state->gta_ped =
        dc_load_u32(wrapper + PROBE_DC_PLAYER_PED_GTA_PED_OFFSET);
  }
  ped = (uintptr_t)state->gta_ped;
  if (ped != 0u &&
      dc_memory_is_readable(ped, PROBE_DC_GTA_PED_MIN_CAPTURE_SIZE)) {
    state->valid_mask |= 0x08u;
    state->ped_matrix =
        dc_load_u32(ped + PROBE_DC_GTA_ENTITY_MATRIX_OFFSET);
    state->ped_rw_object =
        dc_load_u32(ped + PROBE_DC_GTA_ENTITY_RW_OBJECT_OFFSET);
    state->ped_entity_flags =
        dc_load_u32(ped + PROBE_DC_GTA_ENTITY_FLAGS_OFFSET);
    state->entity_status =
        dc_load_u8(ped + PROBE_DC_GTA_ENTITY_STATUS_OFFSET);
    state->ped_flags =
        dc_load_u32(ped + PROBE_DC_GTA_PED_FLAGS_OFFSET);
    state->ped_intelligence =
        dc_load_u32(ped + PROBE_DC_GTA_PED_INTELLIGENCE_OFFSET);
    state->action =
        dc_load_u8(ped + PROBE_DC_GTA_PED_ACTION_OFFSET);
    state->ped_health_bits =
        dc_load_u32(ped + PROBE_DC_GTA_PED_HEALTH_OFFSET);
    state->ped_state =
        dc_load_u32(ped + PROBE_DC_GTA_PED_STATE_OFFSET);
  } else {
    state->action = 0xffu;
    state->entity_status = 0xffu;
  }
  intelligence = (uintptr_t)state->ped_intelligence;
  if (intelligence != 0u &&
      dc_memory_is_readable(
          intelligence + PROBE_DC_GTA_TASK_ROOTS_OFFSET,
          sizeof(state->task_roots))) {
    memcpy(state->task_roots,
           (const void *)(intelligence + PROBE_DC_GTA_TASK_ROOTS_OFFSET),
           sizeof(state->task_roots));
    state->valid_mask |= 0x10u;
  }
  dc_capture_ui(state);
}

static void dc_capture_cleanup(DWORD netgame,
                               probe_dc_cleanup_state *state) {
  uintptr_t pools;
  uintptr_t pool;
  DWORD pointer_value;

  memset(state, 0, sizeof(*state));
  state->first_vehicle_id = 0xffffffffu;
  state->first_object_id = 0xffffffffu;
  state->first_actor_id = 0xffffffffu;
  state->vehicle_listed = 0xffffffffu;
  state->vehicle_wrappers = 0xffffffffu;
  state->remote_aux = 0xffffffffu;
  state->remote_wrappers = 0xffffffffu;
  state->pickup_handles = 0xffffffffu;
  state->pickup_server_ids = 0xffffffffu;
  state->pickup_timers = 0xffffffffu;
  state->object_listed = 0xffffffffu;
  state->object_wrappers = 0xffffffffu;
  state->actor_listed = 0xffffffffu;
  state->actor_wrappers = 0xffffffffu;
  state->gangzone_listed = 0xffffffffu;
  state->textdraw_listed = 0xffffffffu;
  state->label_listed = 0xffffffffu;
  state->menu_listed = 0xffffffffu;
  state->menu_current = 0xffffffffu;
  state->netgame = netgame;
  if (netgame == 0u ||
      !dc_memory_is_readable((uintptr_t)netgame,
                             PROBE_DC_NETGAME_POOLS_OFFSET +
                                 sizeof(DWORD))) {
    return;
  }
  state->valid_mask |= 0x01u;
  state->pools =
      dc_load_u32((uintptr_t)netgame + PROBE_DC_NETGAME_POOLS_OFFSET);
  pools = (uintptr_t)state->pools;
  if (pools == 0u || !dc_memory_is_readable(pools, 9u * sizeof(DWORD))) {
    state->remove_building_count =
        dc_read_u32(g_dc_samp_base +
                        PROBE_DC_REMOVE_BUILDING_COUNT_RVA,
                    0u);
    return;
  }
  memcpy(state->pool_ptrs, (const void *)pools, sizeof(state->pool_ptrs));
  state->valid_mask |= 0x02u;

  pool = (uintptr_t)state->pool_ptrs[0];
  if (pool != 0u) {
    state->vehicle_listed =
        dc_count_u32(pool + PROBE_DC_VEHICLE_LISTED_OFFSET,
                     PROBE_DC_VEHICLE_CAPACITY, 0u, 1);
    state->vehicle_wrappers =
        dc_count_u32(pool + PROBE_DC_VEHICLE_WRAPPERS_OFFSET,
                     PROBE_DC_VEHICLE_CAPACITY, 0u, 1);
    state->first_vehicle_id =
        dc_find_first_pair(pool + PROBE_DC_VEHICLE_LISTED_OFFSET,
                           pool + PROBE_DC_VEHICLE_WRAPPERS_OFFSET,
                           PROBE_DC_VEHICLE_CAPACITY, &pointer_value);
    state->first_vehicle_wrapper = pointer_value;
    if (pointer_value != 0u) {
      state->first_vehicle_entity =
          dc_read_u32((uintptr_t)pointer_value +
                          PROBE_DC_VEHICLE_WRAPPER_ENTITY_OFFSET,
                      0u);
      state->first_vehicle_gta =
          dc_read_u32((uintptr_t)pointer_value +
                          PROBE_DC_VEHICLE_WRAPPER_GTA_OFFSET,
                      0u);
    }
    if (state->first_vehicle_gta != 0u) {
      uintptr_t entity = (uintptr_t)state->first_vehicle_gta;
      state->first_vehicle_matrix =
          dc_read_u32(entity + PROBE_DC_GTA_ENTITY_MATRIX_OFFSET, 0u);
      state->first_vehicle_rw_object =
          dc_read_u32(entity + PROBE_DC_GTA_ENTITY_RW_OBJECT_OFFSET, 0u);
      state->first_vehicle_flags =
          dc_read_u32(entity + PROBE_DC_GTA_ENTITY_FLAGS_OFFSET, 0u);
    }
  }

  pool = (uintptr_t)state->pool_ptrs[1];
  if (pool != 0u) {
    state->remote_aux =
        dc_count_u32(pool + PROBE_DC_PLAYER_POOL_REMOTE_AUX_OFFSET,
                     PROBE_DC_REMOTE_PLAYER_CAPACITY, 0u, 1);
    state->remote_wrappers =
        dc_count_u32(pool + PROBE_DC_PLAYER_POOL_REMOTE_WRAPPER_OFFSET,
                     PROBE_DC_REMOTE_PLAYER_CAPACITY, 0u, 1);
  }

  pool = (uintptr_t)state->pool_ptrs[2];
  if (pool != 0u) {
    state->pickup_handles =
        dc_count_u32(pool + PROBE_DC_PICKUP_HANDLE_OFFSET,
                     PROBE_DC_PICKUP_CAPACITY, 0u, 1);
    state->pickup_server_ids =
        dc_count_u32(pool + PROBE_DC_PICKUP_SERVER_ID_OFFSET,
                     PROBE_DC_PICKUP_CAPACITY, 0xffffffffu, 1);
    state->pickup_timers =
        dc_count_u32(pool + PROBE_DC_PICKUP_TIMER_OFFSET,
                     PROBE_DC_PICKUP_CAPACITY, 0u, 1);
  }

  pool = (uintptr_t)state->pool_ptrs[3];
  if (pool != 0u) {
    state->object_listed =
        dc_count_u32(pool + PROBE_DC_OBJECT_LISTED_OFFSET,
                     PROBE_DC_OBJECT_CAPACITY, 0u, 1);
    state->object_wrappers =
        dc_count_u32(pool + PROBE_DC_OBJECT_WRAPPERS_OFFSET,
                     PROBE_DC_OBJECT_CAPACITY, 0u, 1);
    state->first_object_id =
        dc_find_first_pair(pool + PROBE_DC_OBJECT_LISTED_OFFSET,
                           pool + PROBE_DC_OBJECT_WRAPPERS_OFFSET,
                           PROBE_DC_OBJECT_CAPACITY, &pointer_value);
    state->first_object_wrapper = pointer_value;
  }

  pool = (uintptr_t)state->pool_ptrs[4];
  if (pool != 0u) {
    state->actor_listed =
        dc_count_u32(pool + PROBE_DC_ACTOR_LISTED_OFFSET,
                     PROBE_DC_ACTOR_CAPACITY, 0u, 1);
    state->actor_wrappers =
        dc_count_u32(pool + PROBE_DC_ACTOR_WRAPPERS_OFFSET,
                     PROBE_DC_ACTOR_CAPACITY, 0u, 1);
    state->first_actor_id =
        dc_find_first_pair(pool + PROBE_DC_ACTOR_LISTED_OFFSET,
                           pool + PROBE_DC_ACTOR_WRAPPERS_OFFSET,
                           PROBE_DC_ACTOR_CAPACITY, &pointer_value);
    state->first_actor_wrapper = pointer_value;
    if (state->first_actor_id != 0xffffffffu) {
      state->first_actor_gta_ped =
          dc_read_u32(pool + PROBE_DC_ACTOR_GTA_PED_OFFSET +
                          state->first_actor_id * sizeof(DWORD),
                      0u);
    }
  }

  pool = (uintptr_t)state->pool_ptrs[5];
  if (pool != 0u) {
    state->gangzone_listed =
        dc_count_u32(pool + PROBE_DC_GANGZONE_LISTED_OFFSET,
                     PROBE_DC_GANGZONE_CAPACITY, 0u, 1);
  }
  pool = (uintptr_t)state->pool_ptrs[6];
  if (pool != 0u) {
    state->textdraw_listed =
        dc_count_u32(pool + PROBE_DC_TEXTDRAW_LISTED_OFFSET,
                     PROBE_DC_TEXTDRAW_CAPACITY, 0u, 1);
  }
  pool = (uintptr_t)state->pool_ptrs[7];
  if (pool != 0u) {
    state->label_listed =
        dc_count_u32(pool + PROBE_DC_LABEL_LISTED_OFFSET,
                     PROBE_DC_LABEL_CAPACITY, 0u, 1);
  }
  pool = (uintptr_t)state->pool_ptrs[8];
  if (pool != 0u) {
    state->menu_listed =
        dc_count_u32(pool + PROBE_DC_MENU_LISTED_OFFSET,
                     PROBE_DC_MENU_CAPACITY, 0u, 1);
    state->menu_current =
        dc_read_u8(pool + PROBE_DC_MENU_CURRENT_OFFSET, 0xffu);
  }
  state->remove_building_count =
      dc_read_u32(g_dc_samp_base + PROBE_DC_REMOVE_BUILDING_COUNT_RVA,
                  0u);
}

static void dc_begin_trace(probe_dc_trace *trace, BYTE kind, DWORD hook_rva,
                           DWORD object, DWORD argument, void *caller) {
  memset(trace, 0, sizeof(*trace));
  trace->event_seq = InterlockedIncrement(&g_dc_event_seq);
  trace->tick = GetTickCount();
  trace->thread_id = GetCurrentThreadId();
  trace->gta_frame = dc_load_u32(PROBE_DC_GTA_FRAME_COUNTER_ADDR);
  trace->caller_rva = dc_caller_rva(caller);
  trace->hook_rva = hook_rva;
  trace->object = object;
  trace->argument = argument;
  trace->kind = kind;
}

static void dc_publish_trace(probe_dc_trace *trace) {
  probe_dc_trace *slot;
  LONG ring_seq;
  if (trace == NULL) {
    return;
  }
  ring_seq = InterlockedIncrement(&g_dc_trace_write_seq);
  trace->ring_seq = ring_seq;
  trace->committed_seq = 0;
  slot = &g_dc_trace_ring[
      ((DWORD)ring_seq - 1u) % PROBE_DC_TRACE_RING_SIZE];
  InterlockedExchange(&slot->committed_seq, 0);
  *slot = *trace;
  MemoryBarrier();
  InterlockedExchange(&slot->committed_seq, ring_seq);
}

static int PROBE_DC_THISCALL hook_dc_local_process(void *self) {
  probe_dc_trace trace;
  int result;
  int publish;
  dc_begin_trace(&trace, PROBE_DC_EVENT_PROCESS,
                 PROBE_DC_LOCAL_PROCESS_RVA, (DWORD)(uintptr_t)self, 0u,
                 __builtin_return_address(0));
  dc_capture_local((DWORD)(uintptr_t)self, 0u, &trace.before_local);
  result = ((probe_dc_local_int_fn)g_dc_hooks[0].trampoline)(self);
  trace.result = (DWORD)result;
  dc_capture_local((DWORD)(uintptr_t)self, 0u, &trace.after_local);
  publish =
      memcmp(&trace.before_local, &trace.after_local,
             sizeof(trace.before_local)) != 0 ||
      !g_dc_last_process_valid ||
      memcmp(&g_dc_last_process_state, &trace.after_local,
             sizeof(g_dc_last_process_state)) != 0 ||
      (DWORD)(trace.tick - g_dc_last_process_tick) >=
          PROBE_DC_PROCESS_HEARTBEAT_MS;
  if (publish) {
    g_dc_last_process_state = trace.after_local;
    g_dc_last_process_tick = trace.tick;
    g_dc_last_process_valid = 1;
    dc_publish_trace(&trace);
  }
  return result;
}

static int PROBE_DC_THISCALL hook_dc_local_spawn(void *self) {
  probe_dc_trace trace;
  int result;
  dc_begin_trace(&trace, PROBE_DC_EVENT_SPAWN,
                 PROBE_DC_LOCAL_SPAWN_RVA, (DWORD)(uintptr_t)self, 0u,
                 __builtin_return_address(0));
  dc_capture_local((DWORD)(uintptr_t)self, 0u, &trace.before_local);
  result = ((probe_dc_local_int_fn)g_dc_hooks[1].trampoline)(self);
  trace.result = (DWORD)result;
  dc_capture_local((DWORD)(uintptr_t)self, 0u, &trace.after_local);
  dc_publish_trace(&trace);
  return result;
}

static void PROBE_DC_THISCALL hook_dc_class_selection(void *self) {
  probe_dc_trace trace;
  dc_begin_trace(&trace, PROBE_DC_EVENT_CLASS_SELECTION,
                 PROBE_DC_LOCAL_CLASS_SELECTION_RVA,
                 (DWORD)(uintptr_t)self, 0u,
                 __builtin_return_address(0));
  dc_capture_local((DWORD)(uintptr_t)self, 0u, &trace.before_local);
  ((probe_dc_local_void_fn)g_dc_hooks[2].trampoline)(self);
  dc_capture_local((DWORD)(uintptr_t)self, 0u, &trace.after_local);
  dc_publish_trace(&trace);
}

static void dc_run_cleanup_hook(BYTE kind, DWORD hook_rva, size_t hook_index,
                                void *self, void *caller) {
  probe_dc_trace trace;
  dc_begin_trace(&trace, kind, hook_rva, (DWORD)(uintptr_t)self, 0u,
                 caller);
  trace.cleanup_valid = 1u;
  dc_capture_local(0u, (DWORD)(uintptr_t)self, &trace.before_local);
  dc_capture_cleanup((DWORD)(uintptr_t)self, &trace.before_cleanup);
  ((probe_dc_net_void_fn)g_dc_hooks[hook_index].trampoline)(self);
  dc_capture_local(0u, (DWORD)(uintptr_t)self, &trace.after_local);
  dc_capture_cleanup((DWORD)(uintptr_t)self, &trace.after_cleanup);
  dc_publish_trace(&trace);
  if (kind == PROBE_DC_EVENT_QUIT_DESTRUCTOR &&
      trace.caller_rva == PROBE_DC_CLEAN_QUIT_DESTRUCTOR_CALLER_RVA) {
    InterlockedExchange(&g_dc_clean_quit_destructor_seq, trace.ring_seq);
  }
}

static void PROBE_DC_THISCALL hook_dc_gmx_reset(void *self) {
  dc_run_cleanup_hook(PROBE_DC_EVENT_GMX_RESET,
                      PROBE_DC_NETGAME_GMX_RESET_RVA, 3u, self,
                      __builtin_return_address(0));
}

static void PROBE_DC_THISCALL hook_dc_connection_lost(void *self,
                                                       void *packet) {
  probe_dc_trace trace;
  dc_begin_trace(&trace, PROBE_DC_EVENT_CONNECTION_LOST,
                 PROBE_DC_NETGAME_CONNECTION_LOST_RVA,
                 (DWORD)(uintptr_t)self, (DWORD)(uintptr_t)packet,
                 __builtin_return_address(0));
  trace.cleanup_valid = 1u;
  dc_capture_local(0u, (DWORD)(uintptr_t)self, &trace.before_local);
  dc_capture_cleanup((DWORD)(uintptr_t)self, &trace.before_cleanup);
  ((probe_dc_net_packet_fn)g_dc_hooks[4].trampoline)(self, packet);
  dc_capture_local(0u, (DWORD)(uintptr_t)self, &trace.after_local);
  dc_capture_cleanup((DWORD)(uintptr_t)self, &trace.after_cleanup);
  dc_publish_trace(&trace);
}

static void PROBE_DC_THISCALL hook_dc_destructor(void *self) {
  dc_run_cleanup_hook(PROBE_DC_EVENT_QUIT_DESTRUCTOR,
                      PROBE_DC_NETGAME_DESTRUCTOR_RVA, 5u, self,
                      __builtin_return_address(0));
}

static void dc_invoke_original_exit_process(UINT exit_code) {
  probe_dc_exit_process_fn original = g_dc_original_exit_process;
  if (original != NULL) {
    original(exit_code);
  }
  ExitProcess(exit_code);
  for (;;) {
    Sleep(INFINITE);
  }
}

static VOID WINAPI hook_dc_exit_process(UINT exit_code) {
  DWORD caller_rva = dc_caller_rva(__builtin_return_address(0));
  DWORD wait_result;

  /*
   * STATIC_037:
   * The clean R5 main-loop path calls the KERNEL32 ExitProcess import at
   * samp.dll+0xC508B. Its return address is exactly +0xC5091. Other calls
   * through the shared import slot must remain transparent.
  */
  if (caller_rva != PROBE_DC_EXITPROCESS_CALLER_RVA ||
      InterlockedCompareExchange(&g_dc_install_state, 0, 0) != 1 ||
      g_dc_terminal_stop_event == NULL ||
      g_dc_terminal_done_event == NULL ||
      InterlockedCompareExchange(&g_dc_terminal_state, -1, 0) != 0) {
    dc_invoke_original_exit_process(exit_code);
  }

  if (!ResetEvent(g_dc_terminal_done_event)) {
    dc_invoke_original_exit_process(exit_code);
  }
  g_dc_terminal_exit_code = (DWORD)exit_code;
  g_dc_terminal_caller_rva = caller_rva;
  g_dc_terminal_thread_id = GetCurrentThreadId();
  g_dc_terminal_tick = GetTickCount();
  g_dc_terminal_netgame =
      dc_load_u32(g_dc_samp_base + PROBE_DC_NETGAME_PTR_RVA);
  g_dc_terminal_requested_seq =
      InterlockedCompareExchange(&g_dc_trace_write_seq, 0, 0);
  MemoryBarrier();
  InterlockedExchange(&g_dc_terminal_state, 1);

  if (!SetEvent(g_dc_terminal_stop_event)) {
    dc_invoke_original_exit_process(exit_code);
  }
  wait_result = WaitForSingleObject(g_dc_terminal_done_event,
                                    PROBE_DC_TERMINAL_DRAIN_TIMEOUT_MS);
  if (wait_result != WAIT_OBJECT_0) {
    OutputDebugStringA(
        "[samp_probe] death_cleanup_exit_r5 terminal drain timed out\n");
  }
  dc_invoke_original_exit_process(exit_code);
}

static int dc_bytes_match(DWORD rva, const BYTE *bytes, size_t size) {
  return rva <= g_dc_samp_size &&
         size <= (size_t)(g_dc_samp_size - rva) &&
         dc_memory_is_readable(g_dc_samp_base + rva, size) &&
         memcmp((const void *)(g_dc_samp_base + rva), bytes, size) == 0;
}

static int dc_relocated_dword_bytes_match(
    DWORD rva, const BYTE *preferred_bytes, size_t size,
    size_t operand_offset, DWORD *runtime_operand_out) {
  BYTE expected[64];
  DWORD preferred_operand;
  DWORD referenced_rva;
  DWORD runtime_operand;

  /*
   * STATIC_037:
   * Normalize exactly one known PE HIGHLOW operand while keeping every
   * surrounding byte exact. CLocalPlayer::Spawn's SEH registration entry
   * contains the R5 image pointer covered by relocation RVA +0x3C29.
   */
  if (preferred_bytes == NULL || size == 0u || size > sizeof(expected) ||
      operand_offset > size ||
      sizeof(preferred_operand) > size - operand_offset) {
    return 0;
  }
  memcpy(expected, preferred_bytes, size);
  memcpy(&preferred_operand, preferred_bytes + operand_offset,
         sizeof(preferred_operand));
  if (preferred_operand < PROBE_DC_R5_PREFERRED_BASE) {
    return 0;
  }
  referenced_rva = preferred_operand - PROBE_DC_R5_PREFERRED_BASE;
  if (referenced_rva >= g_dc_samp_size ||
      g_dc_samp_base > (uintptr_t)(0xffffffffu - referenced_rva)) {
    return 0;
  }
  runtime_operand = (DWORD)(g_dc_samp_base + (uintptr_t)referenced_rva);
  memcpy(expected + operand_offset, &runtime_operand,
         sizeof(runtime_operand));
  if (!dc_bytes_match(rva, expected, size)) {
    return 0;
  }
  if (runtime_operand_out != NULL) {
    *runtime_operand_out = runtime_operand;
  }
  return 1;
}

static void **dc_exit_iat_slot(void) {
  if (g_dc_samp_size < (DWORD)sizeof(void *) ||
      PROBE_DC_EXITPROCESS_IAT_RVA >
          g_dc_samp_size - (DWORD)sizeof(void *) ||
      !dc_memory_is_readable(
          g_dc_samp_base + PROBE_DC_EXITPROCESS_IAT_RVA,
          sizeof(void *))) {
    return NULL;
  }
  return (void **)(g_dc_samp_base + PROBE_DC_EXITPROCESS_IAT_RVA);
}

static int dc_exit_iat_target_matches(void) {
  HMODULE kernel32;
  FARPROC exit_process;
  void **slot = dc_exit_iat_slot();
  if (slot == NULL) {
    return 0;
  }
  kernel32 = GetModuleHandleA("KERNEL32.dll");
  if (kernel32 == NULL) {
    return 0;
  }
  exit_process = GetProcAddress(kernel32, "ExitProcess");
  return exit_process != NULL && *slot == (void *)(uintptr_t)exit_process;
}

static int dc_preflight(void) {
  static const BYTE process_tail[] = {
      0x5e, 0x5d, 0xb8, 0x01, 0x00, 0x00,
      0x00, 0x5b, 0x83, 0xc4, 0x10, 0xc3};
  static const BYTE spawn_tail[] = {
      0x8b, 0x8c, 0x24, 0x20, 0x01, 0x00, 0x00,
      0x5f, 0x5e, 0xb8, 0x01, 0x00, 0x00, 0x00,
      0x5b, 0x64, 0x89, 0x0d, 0x00, 0x00, 0x00, 0x00,
      0x81, 0xc4, 0x20, 0x01, 0x00, 0x00, 0xc3};
  static const BYTE class_tail[] = {
      0x5f, 0x89, 0x86, 0x47, 0x01, 0x00, 0x00, 0x5e, 0xc3};
  static const BYTE gmx_tail[] = {0x5f, 0x5e, 0x5d, 0x5b, 0xc3};
  static const BYTE lost_tail[] = {
      0xc7, 0x87, 0xcd, 0x03, 0x00, 0x00, 0x01, 0x00,
      0x00, 0x00, 0x5f, 0xc2, 0x04, 0x00};
  static const BYTE destructor_tail[] = {0x5f, 0x5e, 0x5b, 0xc3};
  struct dc_tail {
    DWORD rva;
    const BYTE *bytes;
    size_t size;
  };
  static const struct dc_tail tails[] = {
      {0x00007e37u, process_tail, sizeof(process_tail)},
      {0x00003ea7u, spawn_tail, sizeof(spawn_tail)},
      {0x000040cau, class_tail, sizeof(class_tail)},
      {0x0000a730u, gmx_tail, sizeof(gmx_tail)},
      {0x0000ad6eu, lost_tail, sizeof(lost_tail)},
      {0x00009a31u, destructor_tail, sizeof(destructor_tail)},
  };
  size_t i;
  if (!dc_relocated_dword_bytes_match(
          PROBE_DC_EXITPROCESS_CALLSITE_RVA, g_dc_exit_callsite,
          sizeof(g_dc_exit_callsite), 3u,
          &g_dc_exit_runtime_iat_operand) ||
      g_dc_exit_runtime_iat_operand !=
          (DWORD)(g_dc_samp_base + PROBE_DC_EXITPROCESS_IAT_RVA) ||
      !dc_exit_iat_target_matches()) {
    return 0;
  }
  for (i = 0u; i < sizeof(g_dc_hooks) / sizeof(g_dc_hooks[0]); ++i) {
    int matched;
    if (g_dc_hooks[i].rva == PROBE_DC_LOCAL_SPAWN_RVA) {
      matched = dc_relocated_dword_bytes_match(
          g_dc_hooks[i].rva, g_dc_hooks[i].expected,
          g_dc_hooks[i].length, 9u, &g_dc_spawn_runtime_operand);
    } else {
      matched = dc_bytes_match(g_dc_hooks[i].rva,
                               g_dc_hooks[i].expected,
                               g_dc_hooks[i].length);
    }
    if (!matched) {
      return 0;
    }
  }
  for (i = 0u; i < sizeof(tails) / sizeof(tails[0]); ++i) {
    if (!dc_bytes_match(tails[i].rva, tails[i].bytes, tails[i].size)) {
      return 0;
    }
  }
  return 1;
}

static int dc_rel32(void *from_after, void *to, LONG *relative) {
  intptr_t delta = (BYTE *)to - (BYTE *)from_after;
  if (delta < INT32_MIN || delta > INT32_MAX) {
    return 0;
  }
  *relative = (LONG)delta;
  return 1;
}

static int dc_prepare_trampoline(probe_dc_hook *hook) {
  BYTE *trampoline;
  LONG back_rel;
  uintptr_t target;
  if (hook == NULL || hook->length < 5u ||
      hook->length > sizeof(hook->saved)) {
    return 0;
  }
  target = g_dc_samp_base + hook->rva;
  trampoline = (BYTE *)VirtualAlloc(
      NULL, (SIZE_T)hook->length + 5u, MEM_COMMIT | MEM_RESERVE,
      PAGE_EXECUTE_READWRITE);
  if (trampoline == NULL) {
    return 0;
  }
  memcpy(hook->saved, (const void *)target, hook->length);
  memcpy(trampoline, hook->saved, hook->length);
  if (!dc_rel32(trampoline + hook->length + 5u,
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

static int dc_install_one(probe_dc_hook *hook) {
  uintptr_t target;
  BYTE patch[16];
  LONG replacement_rel;
  DWORD old_protect;
  DWORD ignored_protect;
  if (hook == NULL || hook->trampoline == NULL ||
      hook->length > sizeof(patch)) {
    return 0;
  }
  target = g_dc_samp_base + hook->rva;
  if (!dc_memory_is_readable(target, hook->length) ||
      memcmp((const void *)target, hook->saved, hook->length) != 0) {
    return 0;
  }
  if (!dc_rel32((void *)(target + 5u), hook->replacement,
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

static int dc_patch_is_owned(const probe_dc_hook *hook) {
  BYTE expected[16];
  LONG relative;
  uintptr_t target;
  if (hook == NULL || hook->length > sizeof(expected)) {
    return 0;
  }
  target = g_dc_samp_base + hook->rva;
  if (!dc_rel32((void *)(target + 5u), hook->replacement, &relative)) {
    return 0;
  }
  memset(expected, 0x90, hook->length);
  expected[0] = 0xe9u;
  memcpy(expected + 1u, &relative, sizeof(relative));
  return dc_memory_is_readable(target, hook->length) &&
         memcmp((const void *)target, expected, hook->length) == 0;
}

static int dc_restore_one(probe_dc_hook *hook) {
  uintptr_t target;
  DWORD old_protect;
  DWORD ignored_protect;
  int owned;
  if (hook == NULL ||
      InterlockedCompareExchange(&hook->installed, 0, 0) != 1) {
    return 0;
  }
  owned = dc_patch_is_owned(hook);
  if (!owned) {
    InterlockedExchange(&hook->installed, -1);
    return 0;
  }
  target = g_dc_samp_base + hook->rva;
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

static int dc_install_exit_iat(void) {
  void **slot = dc_exit_iat_slot();
  void *replacement = (void *)hook_dc_exit_process;
  void *original;
  void *previous;
  DWORD old_protect;
  DWORD ignored_protect;
  BOOL protect_restored;

  if (slot == NULL ||
      InterlockedCompareExchange(&g_dc_exit_iat_installed, 0, 0) != 0) {
    return 0;
  }
  original = *slot;
  if (original == NULL || !dc_exit_iat_target_matches()) {
    return 0;
  }
  if (!VirtualProtect(slot, sizeof(*slot), PAGE_EXECUTE_READWRITE,
                      &old_protect)) {
    return 0;
  }
  g_dc_original_exit_process = (probe_dc_exit_process_fn)original;
  previous = InterlockedCompareExchangePointer(
      (PVOID volatile *)slot, replacement, original);
  protect_restored = VirtualProtect(
      slot, sizeof(*slot), old_protect, &ignored_protect);
  if (previous != original || !protect_restored) {
    if (previous == original) {
      (void)InterlockedCompareExchangePointer(
          (PVOID volatile *)slot, original, replacement);
    }
    if (!protect_restored) {
      (void)VirtualProtect(slot, sizeof(*slot), old_protect,
                           &ignored_protect);
    }
    g_dc_original_exit_process = NULL;
    return 0;
  }
  InterlockedExchange(&g_dc_exit_iat_installed, 1);
  return 1;
}

static int dc_restore_exit_iat(void) {
  void **slot = dc_exit_iat_slot();
  void *replacement = (void *)hook_dc_exit_process;
  void *original = (void *)g_dc_original_exit_process;
  void *previous;
  DWORD old_protect;
  DWORD ignored_protect;
  BOOL protect_restored;

  if (slot == NULL || original == NULL ||
      InterlockedCompareExchange(&g_dc_exit_iat_installed, 0, 0) != 1) {
    return 0;
  }
  if (!VirtualProtect(slot, sizeof(*slot), PAGE_EXECUTE_READWRITE,
                      &old_protect)) {
    return 0;
  }
  previous = InterlockedCompareExchangePointer(
      (PVOID volatile *)slot, original, replacement);
  protect_restored = VirtualProtect(
      slot, sizeof(*slot), old_protect, &ignored_protect);
  if (previous != replacement || !protect_restored) {
    if (!protect_restored) {
      (void)VirtualProtect(slot, sizeof(*slot), old_protect,
                           &ignored_protect);
    }
    InterlockedExchange(&g_dc_exit_iat_installed, -1);
    return 0;
  }
  InterlockedExchange(&g_dc_exit_iat_installed, 0);
  return 1;
}

static void dc_close_terminal_done_event(
    probe_death_cleanup_log_fn log_fn) {
  HANDLE done_event = g_dc_terminal_done_event;
  g_dc_terminal_done_event = NULL;
  if (done_event != NULL && !CloseHandle(done_event) && log_fn != NULL) {
    log_fn("death_cleanup_hook: terminal_event_close_failed error=%lu",
           (unsigned long)GetLastError());
  }
}

int probe_death_cleanup_install(HMODULE samp_module, DWORD samp_size,
                                int enabled, int code_hooks_disabled,
                                HANDLE worker_stop_event,
                                probe_death_cleanup_log_fn log_fn,
                                int log_summary) {
  HMODULE gta_module;
  size_t hook_count = sizeof(g_dc_hooks) / sizeof(g_dc_hooks[0]);
  size_t requested_count = hook_count + 1u;
  size_t i;
  int installed = 0;

  if (!enabled) {
    if (log_summary && log_fn != NULL) {
      log_fn("death_cleanup_hook: disabled by default; enable with "
             "SAMP_PROBE_DEATH_CLEANUP_HOOKS=1 or "
             "samp_probe_death_cleanup_hooks.flag");
    }
    return 0;
  }
  if (code_hooks_disabled) {
    if (log_summary && log_fn != NULL) {
      log_fn("death_cleanup_hook: disabled by "
             "SAMP_PROBE_NO_SAMP_CODE_HOOKS");
    }
    return 0;
  }
  if (InterlockedCompareExchange(&g_dc_install_state, 0, 0) == 1) {
    return (int)requested_count;
  }
  if (InterlockedCompareExchange(&g_dc_install_state, 0, 0) < 0) {
    return 0;
  }

  if (worker_stop_event == NULL) {
    if (log_summary && log_fn != NULL) {
      log_fn("death_cleanup_hook: skip missing_worker_stop_event "
             "installed=0 requested=%u",
             (unsigned)requested_count);
    }
    InterlockedExchange(&g_dc_install_state, -1);
    return 0;
  }

  g_dc_samp_base = (uintptr_t)samp_module;
  g_dc_samp_size = samp_size;
  g_dc_terminal_stop_event = worker_stop_event;
  gta_module = GetModuleHandleA(NULL);
  if (g_dc_samp_size != PROBE_DC_R5_IMAGE_SIZE ||
      !dc_pe_identity_matches(samp_module, PROBE_DC_R5_TIMESTAMP,
                              PROBE_DC_R5_ENTRY_RVA,
                              PROBE_DC_R5_IMAGE_SIZE,
                              PROBE_DC_R5_PREFERRED_BASE, 0u, 0, 0) ||
      (uintptr_t)gta_module != PROBE_DC_GTA_PREFERRED_BASE ||
      !dc_pe_identity_matches(gta_module, PROBE_DC_GTA_TIMESTAMP,
                              PROBE_DC_GTA_ENTRY_RVA,
                              PROBE_DC_GTA_IMAGE_SIZE,
                              PROBE_DC_GTA_PREFERRED_BASE,
                              PROBE_DC_GTA_CHECKSUM, 1, 1)) {
    if (log_summary && log_fn != NULL) {
      log_fn("death_cleanup_hook: skip unsupported_identity installed=0 "
             "samp_base=0x%08lx samp_size=0x%08lx "
             "samp_delta=0x%08lx samp_sha256=%s "
             "gta_base=0x%08lx gta_sha256=%s "
             "evidence=STATIC_037",
             (unsigned long)g_dc_samp_base,
             (unsigned long)g_dc_samp_size,
             (unsigned long)(g_dc_samp_base -
                             PROBE_DC_R5_PREFERRED_BASE),
             PROBE_DC_R5_SHA256,
             (unsigned long)(uintptr_t)gta_module, PROBE_DC_GTA_SHA256);
    }
    InterlockedExchange(&g_dc_install_state, -1);
    return 0;
  }
  if (!dc_preflight()) {
    if (log_summary && log_fn != NULL) {
      log_fn("death_cleanup_hook: skip preflight_mismatch installed=0 "
             "requested=%u evidence=STATIC_037",
             (unsigned)requested_count);
    }
    InterlockedExchange(&g_dc_install_state, -1);
    return 0;
  }

  g_dc_terminal_done_event = CreateEventA(NULL, TRUE, FALSE, NULL);
  if (g_dc_terminal_done_event == NULL) {
    if (log_summary && log_fn != NULL) {
      log_fn("death_cleanup_hook: terminal_event_failed installed=0 "
             "requested=%u error=%lu",
             (unsigned)requested_count,
             (unsigned long)GetLastError());
    }
    InterlockedExchange(&g_dc_install_state, -1);
    return 0;
  }

  for (i = 0u; i < hook_count; ++i) {
    if (!dc_prepare_trampoline(&g_dc_hooks[i])) {
      break;
    }
  }
  if (i != hook_count) {
    size_t j;
    for (j = 0u; j < hook_count; ++j) {
      if (g_dc_hooks[j].trampoline != NULL) {
        VirtualFree(g_dc_hooks[j].trampoline, 0u, MEM_RELEASE);
        g_dc_hooks[j].trampoline = NULL;
      }
    }
    if (log_summary && log_fn != NULL) {
      log_fn("death_cleanup_hook: trampoline_allocation_failed "
             "prepared=%u requested=%u installed=0",
             (unsigned)i, (unsigned)requested_count);
    }
    dc_close_terminal_done_event(log_fn);
    InterlockedExchange(&g_dc_install_state, -1);
    return 0;
  }

  for (i = 0u; i < hook_count; ++i) {
    if (!dc_install_one(&g_dc_hooks[i])) {
      break;
    }
    ++installed;
  }
  if ((size_t)installed != hook_count) {
    while (installed > 0) {
      --installed;
      (void)dc_restore_one(&g_dc_hooks[installed]);
    }
    if (log_summary && log_fn != NULL) {
      log_fn("death_cleanup_hook: incomplete_install installed=0 "
             "requested=%u; run_invalid=1",
             (unsigned)requested_count);
    }
    InterlockedExchange(&g_dc_install_state, -1);
    dc_close_terminal_done_event(log_fn);
    return 0;
  }
  if (!dc_install_exit_iat()) {
    while (installed > 0) {
      --installed;
      (void)dc_restore_one(&g_dc_hooks[installed]);
    }
    if (log_summary && log_fn != NULL) {
      log_fn("death_cleanup_hook: exit_iat_install_failed installed=0 "
             "requested=%u; run_invalid=1",
             (unsigned)requested_count);
    }
    dc_close_terminal_done_event(log_fn);
    InterlockedExchange(&g_dc_install_state, -1);
    return 0;
  }
  ++installed;
  InterlockedExchange(&g_dc_install_state, 1);
  if (log_summary && log_fn != NULL) {
    log_fn("death_cleanup_hook: summary installed=%u requested=%u "
           "rvas=0x74c0,0x3c20,0x4080,0xa540,0xacf0,0x9880 "
           "exit_iat_rva=0x000e5188 exit_caller_rva=0x000c5091 "
           "samp_base=0x%08lx samp_delta=0x%08lx "
           "operand_3c29=0x%08lx operand_c508d=0x%08lx "
           "samp_sha256=%s gta_sha256=%s "
           "guard=identity,samp_relocation_normalized,gta_preferred_base,"
           "entry_bytes,tails,exit_callsite,exit_export,all_or_nothing "
           "evidence=STATIC_037,TODO_VERIFY",
           (unsigned)installed, (unsigned)requested_count,
           (unsigned long)g_dc_samp_base,
           (unsigned long)(g_dc_samp_base -
                           PROBE_DC_R5_PREFERRED_BASE),
           (unsigned long)g_dc_spawn_runtime_operand,
           (unsigned long)g_dc_exit_runtime_iat_operand,
           PROBE_DC_R5_SHA256, PROBE_DC_GTA_SHA256);
  }
  return (int)requested_count;
}

static const char *dc_event_name(BYTE kind) {
  switch (kind) {
  case PROBE_DC_EVENT_PROCESS:
    return "local_process";
  case PROBE_DC_EVENT_SPAWN:
    return "spawn";
  case PROBE_DC_EVENT_CLASS_SELECTION:
    return "class_selection";
  case PROBE_DC_EVENT_GMX_RESET:
    return "gmx_reset";
  case PROBE_DC_EVENT_CONNECTION_LOST:
    return "connection_lost";
  case PROBE_DC_EVENT_QUIT_DESTRUCTOR:
    return "quit_destructor";
  default:
    return "unknown";
  }
}

static void dc_log_local(probe_death_cleanup_log_fn log_fn,
                         const probe_dc_trace *trace, const char *phase,
                         const probe_dc_local_state *state) {
  union {
    DWORD bits;
    float value;
  } health;
  int dead_or_wasted;
  health.bits = state->ped_health_bits;
  dead_or_wasted =
      state->wasted != 0u || state->action == 54u ||
      state->action == 55u ||
      ((state->valid_mask & 0x08u) != 0u && health.value <= 0.0f);
  log_fn(
      "death_cleanup_local_r5: seq=%ld event=%ld phase=%s "
      "valid=0x%08lx netgame=0x%08lx state=%lu pools=0x%08lx "
      "player_pool=0x%08lx local=0x%08lx active=%lu wasted=%lu "
      "spectating=%lu cleared_spawn=%lu has_spawn=%lu wants_class=%lu "
      "class_selection=%lu class_input=%lu class_ticks=%lu,%lu,%lu "
      "vehicle=0x%08lx ped_wrapper=0x%08lx gta_ped=0x%08lx "
      "action=%u dead_or_wasted=%d health_bits=0x%08lx "
      "ped_state=0x%08lx entity_status=%u entity_flags=0x%08lx "
      "ped_flags=0x%08lx matrix=0x%08lx rw=0x%08lx "
      "spawn_hash=0x%08lx spawn_head=%08lx,%08lx,%08lx,%08lx",
      (long)trace->ring_seq, (long)trace->event_seq, phase,
      (unsigned long)state->valid_mask, (unsigned long)state->netgame,
      (unsigned long)state->netgame_state, (unsigned long)state->pools,
      (unsigned long)state->player_pool,
      (unsigned long)state->local_player, (unsigned long)state->active,
      (unsigned long)state->wasted, (unsigned long)state->spectating,
      (unsigned long)state->cleared_to_spawn,
      (unsigned long)state->has_spawn_info,
      (unsigned long)state->wants_another_class,
      (unsigned long)state->class_selection,
      (unsigned long)state->class_input_owned,
      (unsigned long)state->class_tick_a,
      (unsigned long)state->class_tick_b,
      (unsigned long)state->class_tick_c,
      (unsigned long)state->current_vehicle,
      (unsigned long)state->ped_wrapper,
      (unsigned long)state->gta_ped, (unsigned)state->action,
      dead_or_wasted, (unsigned long)state->ped_health_bits,
      (unsigned long)state->ped_state, (unsigned)state->entity_status,
      (unsigned long)state->ped_entity_flags,
      (unsigned long)state->ped_flags, (unsigned long)state->ped_matrix,
      (unsigned long)state->ped_rw_object,
      (unsigned long)state->spawn_info_hash,
      (unsigned long)state->spawn_info_head[0],
      (unsigned long)state->spawn_info_head[1],
      (unsigned long)state->spawn_info_head[2],
      (unsigned long)state->spawn_info_head[3]);
  log_fn(
      "death_cleanup_tasks_r5: seq=%ld event=%ld phase=%s "
      "intelligence=0x%08lx roots=%08lx,%08lx,%08lx,%08lx,%08lx,"
      "%08lx,%08lx,%08lx,%08lx,%08lx,%08lx",
      (long)trace->ring_seq, (long)trace->event_seq, phase,
      (unsigned long)state->ped_intelligence,
      (unsigned long)state->task_roots[0],
      (unsigned long)state->task_roots[1],
      (unsigned long)state->task_roots[2],
      (unsigned long)state->task_roots[3],
      (unsigned long)state->task_roots[4],
      (unsigned long)state->task_roots[5],
      (unsigned long)state->task_roots[6],
      (unsigned long)state->task_roots[7],
      (unsigned long)state->task_roots[8],
      (unsigned long)state->task_roots[9],
      (unsigned long)state->task_roots[10]);
  log_fn(
      "death_cleanup_ui_r5: seq=%ld event=%ld phase=%s "
      "scoreboard=0x%08lx visible=%lu dialog=0x%08lx active=%lu "
      "selector=0x%08lx active=%lu chat=0x%08lx active=%lu "
      "class_gui=0x%08lx visible=%lu game=0x%08lx "
      "input_depth=%lu,%lu camera=%u,%u frontend=%u,%u,%u",
      (long)trace->ring_seq, (long)trace->event_seq, phase,
      (unsigned long)state->scoreboard,
      (unsigned long)state->scoreboard_visible,
      (unsigned long)state->dialog, (unsigned long)state->dialog_active,
      (unsigned long)state->textdraw_selector,
      (unsigned long)state->textdraw_active,
      (unsigned long)state->chat, (unsigned long)state->chat_active,
      (unsigned long)state->class_gui,
      (unsigned long)state->class_gui_visible,
      (unsigned long)state->game,
      (unsigned long)state->game_input_depth_a,
      (unsigned long)state->game_input_depth_b,
      (unsigned)state->camera_mode, (unsigned)state->camera_mode2,
      (unsigned)state->frontend_a, (unsigned)state->frontend_b,
      (unsigned)state->frontend_c);
}

static void dc_log_cleanup(probe_death_cleanup_log_fn log_fn,
                           const probe_dc_trace *trace, const char *phase,
                           const probe_dc_cleanup_state *state) {
  log_fn(
      "death_cleanup_pools_r5: seq=%ld event=%ld phase=%s "
      "valid=0x%08lx netgame=0x%08lx pools=0x%08lx "
      "pool_ptrs=%08lx,%08lx,%08lx,%08lx,%08lx,%08lx,%08lx,%08lx,%08lx "
      "vehicle=%lu/%lu remote=%lu/%lu pickup_raw=%lu/%lu/%lu "
      "object=%lu/%lu actor=%lu/%lu gangzone=%lu textdraw=%lu "
      "label=%lu menu=%lu current=%lu remove_building_count=%lu",
      (long)trace->ring_seq, (long)trace->event_seq, phase,
      (unsigned long)state->valid_mask, (unsigned long)state->netgame,
      (unsigned long)state->pools,
      (unsigned long)state->pool_ptrs[0],
      (unsigned long)state->pool_ptrs[1],
      (unsigned long)state->pool_ptrs[2],
      (unsigned long)state->pool_ptrs[3],
      (unsigned long)state->pool_ptrs[4],
      (unsigned long)state->pool_ptrs[5],
      (unsigned long)state->pool_ptrs[6],
      (unsigned long)state->pool_ptrs[7],
      (unsigned long)state->pool_ptrs[8],
      (unsigned long)state->vehicle_listed,
      (unsigned long)state->vehicle_wrappers,
      (unsigned long)state->remote_aux,
      (unsigned long)state->remote_wrappers,
      (unsigned long)state->pickup_handles,
      (unsigned long)state->pickup_server_ids,
      (unsigned long)state->pickup_timers,
      (unsigned long)state->object_listed,
      (unsigned long)state->object_wrappers,
      (unsigned long)state->actor_listed,
      (unsigned long)state->actor_wrappers,
      (unsigned long)state->gangzone_listed,
      (unsigned long)state->textdraw_listed,
      (unsigned long)state->label_listed,
      (unsigned long)state->menu_listed,
      (unsigned long)state->menu_current,
      (unsigned long)state->remove_building_count);
  log_fn(
      "death_cleanup_entities_r5: seq=%ld event=%ld phase=%s "
      "vehicle=id:%lu wrapper:0x%08lx entity:0x%08lx gta:0x%08lx "
      "matrix:0x%08lx rw:0x%08lx flags:0x%08lx "
      "object=id:%lu wrapper:0x%08lx "
      "actor=id:%lu wrapper:0x%08lx gta_ped:0x%08lx",
      (long)trace->ring_seq, (long)trace->event_seq, phase,
      (unsigned long)state->first_vehicle_id,
      (unsigned long)state->first_vehicle_wrapper,
      (unsigned long)state->first_vehicle_entity,
      (unsigned long)state->first_vehicle_gta,
      (unsigned long)state->first_vehicle_matrix,
      (unsigned long)state->first_vehicle_rw_object,
      (unsigned long)state->first_vehicle_flags,
      (unsigned long)state->first_object_id,
      (unsigned long)state->first_object_wrapper,
      (unsigned long)state->first_actor_id,
      (unsigned long)state->first_actor_wrapper,
      (unsigned long)state->first_actor_gta_ped);
}

void probe_death_cleanup_flush(probe_death_cleanup_log_fn log_fn) {
  LONG write_seq;
  LONG pending;
  if (log_fn == NULL) {
    return;
  }
  write_seq = InterlockedCompareExchange(&g_dc_trace_write_seq, 0, 0);
  pending = write_seq - g_dc_trace_flushed_seq;
  if (pending > (LONG)PROBE_DC_TRACE_RING_SIZE) {
    LONG skipped = pending - (LONG)PROBE_DC_TRACE_RING_SIZE;
    g_dc_trace_flushed_seq += skipped;
    g_dc_trace_overflow_count += skipped;
    log_fn("death_cleanup_r5: overflow skipped=%ld total_skipped=%ld "
           "ring=%u",
           (long)skipped, (long)g_dc_trace_overflow_count,
           (unsigned)PROBE_DC_TRACE_RING_SIZE);
  }
  while (g_dc_trace_flushed_seq < write_seq) {
    LONG next_seq = g_dc_trace_flushed_seq + 1;
    probe_dc_trace *slot =
        &g_dc_trace_ring[
            ((DWORD)next_seq - 1u) % PROBE_DC_TRACE_RING_SIZE];
    probe_dc_trace trace;
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
        "death_cleanup_r5: seq=%ld event=%ld tick=%lu thread=%lu "
        "frame=%lu kind=%s caller_rva=0x%08lx hook_rva=0x%08lx "
        "object=0x%08lx argument=0x%08lx result=0x%08lx "
        "cleanup=%u evidence=STATIC_037,TODO_VERIFY",
        (long)trace.ring_seq, (long)trace.event_seq,
        (unsigned long)trace.tick, (unsigned long)trace.thread_id,
        (unsigned long)trace.gta_frame, dc_event_name(trace.kind),
        (unsigned long)trace.caller_rva,
        (unsigned long)trace.hook_rva, (unsigned long)trace.object,
        (unsigned long)trace.argument, (unsigned long)trace.result,
        (unsigned)trace.cleanup_valid);
    dc_log_local(log_fn, &trace, "pre", &trace.before_local);
    dc_log_local(log_fn, &trace, "post", &trace.after_local);
    if (trace.cleanup_valid) {
      dc_log_cleanup(log_fn, &trace, "pre", &trace.before_cleanup);
      dc_log_cleanup(log_fn, &trace, "post", &trace.after_cleanup);
    }
    g_dc_trace_flushed_seq = next_seq;
  }
}

void probe_death_cleanup_complete_terminal_drain(
    probe_death_cleanup_log_fn log_fn) {
  LONG requested_seq;
  LONG flushed_seq;
  LONG destructor_seq;
  int drain_complete;

  if (InterlockedCompareExchange(&g_dc_terminal_state, 0, 0) != 1) {
    return;
  }

  /*
   * The caller is the probe worker after its stop event was signaled by the
   * exact R5 ExitProcess callsite. Keep file I/O on this worker, then release
   * the game thread only after the append-and-close log path has completed.
   */
  probe_death_cleanup_flush(log_fn);
  requested_seq = g_dc_terminal_requested_seq;
  flushed_seq = g_dc_trace_flushed_seq;
  destructor_seq =
      InterlockedCompareExchange(&g_dc_clean_quit_destructor_seq, 0, 0);
  drain_complete = flushed_seq >= requested_seq;

  if (log_fn != NULL) {
    log_fn(
        "death_cleanup_exit_r5: tick=%lu thread=%lu "
        "caller_rva=0x%08lx exit_code=%lu netgame=0x%08lx "
        "destructor_seq=%ld requested_seq=%ld flushed_seq=%ld "
        "drain=%s timeout_ms=%u exit_iat_restored=%d "
        "evidence=STATIC_037,TODO_VERIFY",
        (unsigned long)g_dc_terminal_tick,
        (unsigned long)g_dc_terminal_thread_id,
        (unsigned long)g_dc_terminal_caller_rva,
        (unsigned long)g_dc_terminal_exit_code,
        (unsigned long)g_dc_terminal_netgame, (long)destructor_seq,
        (long)requested_seq, (long)flushed_seq,
        drain_complete ? "completed" : "partial",
        (unsigned)PROBE_DC_TERMINAL_DRAIN_TIMEOUT_MS,
        InterlockedCompareExchange(&g_dc_exit_iat_installed, 0, 0) == 0);
  }

  MemoryBarrier();
  InterlockedExchange(&g_dc_terminal_state, 2);
  if (g_dc_terminal_done_event != NULL) {
    if (!SetEvent(g_dc_terminal_done_event)) {
      OutputDebugStringA(
          "[samp_probe] death_cleanup_exit_r5 completion signal failed\n");
    }
  }
}

void probe_death_cleanup_uninstall(probe_death_cleanup_log_fn log_fn) {
  size_t hook_count = sizeof(g_dc_hooks) / sizeof(g_dc_hooks[0]);
  size_t requested_count = hook_count + 1u;
  size_t i;
  int restored = 0;
  if (InterlockedCompareExchange(&g_dc_install_state, 0, 0) != 1) {
    return;
  }
  restored += dc_restore_exit_iat();
  for (i = hook_count; i > 0u; --i) {
    restored += dc_restore_one(&g_dc_hooks[i - 1u]);
  }
  if (log_fn != NULL) {
    log_fn("death_cleanup_hook: restore restored=%d requested=%u "
           "gateway_lifetime=process",
           restored, (unsigned)requested_count);
  }
  InterlockedExchange(&g_dc_install_state,
                      restored == (int)requested_count ? 0 : -1);
}
