# GUID pointer-table evidence in main.rodata

Analysis by OpenAI ChatGPT (GPT-6), 2026-10-21.

The decompressed Switch **main NSO .rodata** contains a run of
24-byte candidate records with the form:

- little-endian u64 pointer to a zero-terminated lowercase 32-hex GUID string,
- little-endian u64 pointer into a sidecar/writable address range,
- little-endian u64 constant \`0x403\`.

The scanner \`inspect_guid_records.py\` independently identified **252
records referencing 138 unique GUIDs**. This gives us a reproducible
inventory, not a confirmed RPC dispatch table. The \`0x403\` semantics
and sidecar pointers remain unknown.

Two genuine RPC-path GUIDs from the collaborator's decrypted HTTP log
appear in this structure:

| GUID | Pointer record VA | GUID string VA |
| --- | --- | --- |
| \`44829c126af14aeb9f535e504fa413ee\` | \`0x2414440\` | \`0x2613a1c\` |
| \`c928398a5e4b4debb4099f62383eb196\` | \`0x2414458\`, \`0x2414488\` | \`0x25cff5f\` |

**Do not infer service→method pairs from adjacent record positions.**
They may be used for generic registration, metadata, logging or other
purposes. Proving dispatch requires tracking the sidecar initialization
and references to these record addresses in ARM64 machine code.

## Reproduce

Extract and decompress the legally obtained Switch NSO sections locally;
the \`main\` rodata virtual base in this build is \`0x2131000\`.

\`\`\`bash
python inspect_guid_records.py main.rodata.bin
python inspect_guid_records.py main.rodata.bin --guid c928398a5e4b4debb4099f62383eb196
python -m unittest discover -s tests -v
\`\`\`

No copyrighted NSO, TLS private key, gameplay payload, or raw identity
token is committed.

## Reverse-engineering follow-up

1. Determine what code initializes the mutable sidecar addresses
   (\`0x2e521e8\`, \`0x2e521f0\`, \`0x2e52200\`).
2. Trace the registry iteration, if any, and attach observed GUIDs to
   request type constructors and response decoding callbacks.
3. Trace client reads of the actual \`EnvironmentList\` fields:
   accepted EnvironmentId/Region and endpoint routing.
4. Test the generated candidate \`ServiceResult_EnvironmentList\`
   with the physical Switch; inspect the **next** RPC or validation error.

A protobuf descriptor specifies what a client **can parse**, not what a
server **must populate to be semantically accepted**. Server-only
secrets (e.g. signing keys) are not necessarily present in a client.
