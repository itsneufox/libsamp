# F8 black-screenshot fallback (R5, 2026-07-27)

## Scope

This note covers the screenshot path only. It does not change scene,
streaming, presentation, or device-reset behavior.

## Original R5 evidence

Reference binary:

```text
SHA256=b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2
```

`STATIC_037`: the screenshot routine starts at `samp.dll+0x755C0`. It:

1. creates a desktop-sized `D3DFMT_A8R8G8B8` scratch-pool surface;
2. calls `IDirect3DDevice9::GetFrontBufferData`;
3. converts the GTA client origin to screen coordinates and crops to the
   client rectangle; and
4. calls `D3DXSaveSurfaceToFileA` with PNG output.

The request flag is stored at `samp.dll+0x12DE64`. The render callback at
`samp.dll+0x75730` calls the screenshot routine at `samp.dll+0x7575D`.

The replacement retains that sequence as its unconditional first capture
attempt.

## Runtime observation

`PROBE_TRACE`: under GE-Proton10-34 with its DXVK D3D9 implementation,
replacement screenshots `sa-mp-000.png` through `sa-mp-004.png` were:

- valid 640x448 PNG files;
- byte-identical, 914 bytes each;
- completely black (`#000000`, including every sampled/counted pixel); and
- reported as successfully saved in `samp_runtime.log`.

For example, `sa-mp-002.png` and `sa-mp-004.png` both had:

```text
SHA256=f457319c60552399ed67162df57fbc13b7383880c12195938fe0f449671b0c8f
```

Thus the failure is not a filename or PNG-encoding failure:
`GetFrontBufferData` and the encoder both returned success while the captured
crop contained no visible RGB data.

`INFERRED`: this is the known class of one-buffer/last-present front-buffer
behavior for which DXVK exposes `d3d9.extraFrontbuffer`. The DXVK reference
configuration describes that option as adding a framebuffer whose contents
are preserved for `GetFrontBufferData`:

<https://github.com/doitsujin/dxvk/blob/master/dxvk.conf>

This inference does not replace the observed pixel/result evidence and does
not alter the original-first policy.

## Compatibility fallback

`PROBE_TRACE + INFERRED`: after a successful original-style front-buffer
capture, the replacement defensively locks and inspects only the validated
client crop. It falls back to the current render target only when every RGB
byte in that crop is zero.

The fallback:

1. obtains render target 0;
2. validates its descriptor, dimensions, format, pool, render-target usage,
   and lack of multisampling;
3. creates a matching system-memory surface;
4. copies with `GetRenderTargetData`; and
5. saves that surface through the existing D3DX PNG writer.

An unsupported format, invalid rectangle, bad pitch/bounds, unreadable
memory, failed lock/unlock, missing COM method, multisampled target, or failed
HRESULT leaves the original behavior in place or reports the screenshot as
failed. All acquired COM surfaces are released on every return path. Runtime
logs identify `backend=frontbuffer` or
`backend=render_target_fallback`.

## Verification plan

1. Build and install the replacement DLL without enabling
   `d3d9.extraFrontbuffer`.
2. Enter a visibly non-black game scene and press F8.
3. Confirm the log reports the fully black front-buffer crop, a successful
   render-target copy, and `backend=render_target_fallback`.
4. Confirm the PNG has the expected client dimensions and nonzero RGB
   content (more than one color).
5. On a native/known-good front-buffer implementation, confirm a normal
   screenshot still reports `backend=frontbuffer`.
6. As an optional causality check, repeat with
   `DXVK_CONFIG="d3d9.extraFrontbuffer = True"` and confirm the original
   front-buffer backend remains usable.
7. Repeat after a device reset and verify retries neither crash nor leak COM
   references.

Runtime verification of the new fallback is still `TODO_VERIFY`.
