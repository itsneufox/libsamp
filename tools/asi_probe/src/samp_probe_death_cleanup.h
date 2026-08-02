#ifndef SAMP_PROBE_DEATH_CLEANUP_H
#define SAMP_PROBE_DEATH_CLEANUP_H

#include <windows.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*probe_death_cleanup_log_fn)(const char *format, ...);

int probe_death_cleanup_install(HMODULE samp_module, DWORD samp_size,
                                int enabled, int code_hooks_disabled,
                                HANDLE worker_stop_event,
                                probe_death_cleanup_log_fn log_fn,
                                int log_summary);
void probe_death_cleanup_flush(probe_death_cleanup_log_fn log_fn);
void probe_death_cleanup_uninstall(probe_death_cleanup_log_fn log_fn);
void probe_death_cleanup_complete_terminal_drain(
    probe_death_cleanup_log_fn log_fn);

#ifdef __cplusplus
}
#endif

#endif
