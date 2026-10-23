# ADF index hypothesis — falsified, followed by actual NSO disassembly

Research and static analysis: **OpenAI ChatGPT (GPT-6)**. Original WWZ Switch game binary is NOT committed.

## Empirical index results (31 private test captures)

- Every decompressed `entries` byte length is divisible by 12.
- 31 captures contain 28 distinct payloads, and three exact pairs are duplicates.
- The stricter sequential offset/length test found **zero** strong matches for any of the six pairs of columns in three little-endian 32-bit words.
- Best median adjacency: **0%** for all candidate field pairs. Even in-bounds pairs are not proof of an index. Treat offset/length interpretation as unconfirmed, and discontinue speculative decoders based only on 12-byte arithmetic.

## Stronger static evidence from original Switch NSO

The user previously provided `wwz exefx.zip` containing Nintendo Switch NSO `main`. Its text and rodata sections were decompressed using the sizes and LZ4-compressed offsets in the NSO header. The NSO `MOD0` pointer provided the address of the dynamic table; DT_HASH/DT_SYMTAB/DT_STRTAB resolve ordinary C++ symbol names with actual code addresses. Static ARM64 inspection establishes:

| Mangled C++ name (demangled) | Text virtual address | Notes |
| --- | --- | --- |
| `ADF_STREAM::FlushChunks()` | `0x94C150` | Function dispatches to work at `0x94C260` |
| `ADF_STREAM::CopyThreadChunkData(FLUSHING_INFO&)` | `0x94D6A0` | Copies buffers and metadata |
| `ADF_STREAM::PACK::CheckEntries()` | `0x94D900` | Contains just an ARM64 `ret`, no validation |
| `ADF_STREAM::UPLOADER::Update()` | `0x94E7A0` | Begins upload-related processing |

In `FlushChunks` worker code, a 12-byte indexing stride is used multiple times (e.g. ARM64 `orr w25, wzr, #0xc` at `0x94C598`; `madd` using that stride at `0x94C5E8`, `0x94C664`, `0x94C674`, and `0x94C868`). The code also accesses nested thread-chunk records and uses a 16-byte stride for an intermediate structure. These facts support complex chunk metadata and reject the simplifying assumption that three words must be an offset, length and flag.

**Scope/limits:** Mapping the on-wire `WriteADFPack.entries` records back to these in-memory structures still requires tracing serialization paths and memory layout. A 12-byte stride in producer code is suggestive, not a proof of a specific field interpretation. The repeated literal strings `error`, `disconnect`, and `timeout` in ADF content might be included diagnostic definitions and do not demonstrate that many actual failures occurred.

## Priority change

The actionable WWZ blocker remains a mock-client response semantic mismatch: the Switch issues a valid SignInResult/Heartbeat/Presence sequence, then sends heartbeat unregister and likely session teardown calls. Returning HTTP 200 with protobuf-parseable fields does not confirm accepted semantic values.

Use controlled, one-field-at-a-time experiments with the real protobuf descriptors and **the same Git checkout**. In particular, `SignInResult.ProviderInfo` is an optional message (field 10) that the current mock omits; `ProviderOptionalInfo.Environment=2` has enum `ServerEnvironment_Retail=2`. The subscription field should be left unchanged during this first environment test. The mock's `UserVersions.Versions` is a repeated int64 and is presently sent empty; its meaning is unknown.
