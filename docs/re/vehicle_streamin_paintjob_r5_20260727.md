# R5 vehicle stream-in paintjob semantics

Date: 2026-07-27

Original binary:

- `samp.dll` R5
- SHA256:
  `b72b5dbe725f81864ca3f78bc7063bda56cc05fc7188af822fa7a754432553a2`

## Static R5 result

`STATIC_037`: the RPC 164 stream-in path does not pass the received paintjob
byte straight to GTA:

- `samp.dll+0xE820`: clear the temporary integer.
- `samp.dll+0xE822`: load the RPC paintjob byte.
- `samp.dll+0xE826`: test the byte.
- `samp.dll+0xE828`: skip paintjob application when it is zero.
- `samp.dll+0xE82A`: decrement a non-zero byte.
- `samp.dll+0xE82F`: call the vehicle paintjob wrapper at
  `samp.dll+0xB80F0`.

The wrapper at `samp.dll+0xB80F0`:

- classifies the live GTA vehicle through `samp.dll+0xB61E0`;
- only continues for the automobile subtype;
- accepts logical paintjob IDs `0..3`;
- invokes GTA opcode `0x06ED` through the command descriptor at
  `samp.dll+0xED628`.

Therefore the RPC 164 wire encoding is:

| Wire byte | R5 behavior |
| --- | --- |
| `0` | no paintjob request; do nothing |
| `1..4` | apply GTA logical paintjob `0..3` to automobiles |
| `>4` | rejected by the wrapper's logical range check |

This is corroborated by `OPENMP_REF`: open.mp stores vehicle paintjobs as
logical IDs and adds one when constructing the stream-in RPC because zero means
"no paintjob" on that wire path.

## Legacy distinction

The 0.2x legacy source also guards its stream-in paintjob call with a non-zero
test. Its older code passes the remaining byte directly to opcode `0x06ED`,
however, so it is not evidence for the R5 byte-to-logical mapping. The R5
instructions above decide replacement behavior.

## Current trailer A/B interpretation

The compared model 435 (`artict1`) stream-in event contains `paintjob=0`.
`STATIC_037` proves that original R5 does not apply opcode `0x06ED` for that
event. The original screenshot's Cok-O-Pops appearance and the replacement's
dark/plain appearance therefore cannot be fixed compatibly by forcing logical
paintjob 0.

`TODO_VERIFY`: isolate the remaining model-435 visual difference as GTA default
remap/material state. Repeat comparable original/replacement starts while
recording the trailer's live remap texture/material state and creation order.
Lighting and camera angle should be held constant. Do not add a model-specific
paintjob override without such evidence.
