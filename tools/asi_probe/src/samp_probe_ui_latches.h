#ifndef SAMP_PROBE_UI_LATCHES_H
#define SAMP_PROBE_UI_LATCHES_H

#include <windows.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*probe_ui_latches_log_fn)(const char *format, ...);

int probe_ui_latches_install(HMODULE samp_module, DWORD samp_size,
                             int enabled, int code_hooks_disabled,
                             probe_ui_latches_log_fn log_fn,
                             int log_summary);
void probe_ui_latches_flush(probe_ui_latches_log_fn log_fn);
void probe_ui_latches_uninstall(probe_ui_latches_log_fn log_fn);

#ifdef __cplusplus
}
#endif

#endif
