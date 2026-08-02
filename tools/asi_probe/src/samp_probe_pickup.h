#ifndef SAMP_PROBE_PICKUP_H
#define SAMP_PROBE_PICKUP_H

#include <windows.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*probe_pickup_log_fn)(const char *format, ...);

int probe_pickup_install(HMODULE samp_module, DWORD samp_size, int enabled,
                         int code_hooks_disabled,
                         probe_pickup_log_fn log_fn, int log_summary);
int probe_pickup_is_active(void);
void probe_pickup_observe_rpc(BYTE rpc_id, const BYTE *payload, int bits,
                              int priority, int reliability,
                              char ordering_channel, DWORD caller_rva,
                              BYTE result);
void probe_pickup_flush(probe_pickup_log_fn log_fn);
void probe_pickup_uninstall(probe_pickup_log_fn log_fn);

#ifdef __cplusplus
}
#endif

#endif
