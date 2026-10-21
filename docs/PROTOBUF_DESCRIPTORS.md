# Extracted protobuf descriptors

The source binary embeds two byte-exact \`FileDescriptorProto\` messages.
The utility \`extract_descriptors.py\` recovers them from **locally
decompressed main.rodata**, writes their original serialized descriptors
and reconstructs text \`.proto\` schemas. The game executable, original
assets, certificates and raw network captures are **not** stored here.

Requirements: Python 3.10+ and \`protobuf\` (\`pip install protobuf\`).

Usage:

\`\`\`bash
python extract_descriptors.py main.rodata.bin --output generated-descriptors
\`\`\`

On the analyzed Nintendo Switch build, output is:

| Descriptor | Bytes | Messages | Enums | SHA256 |
| --- | ---: | ---: | ---: | --- |
| bcl.proto | 762 | 7 | 0 | 3fbe19ca969a8c0fcb91f822066865feef848c2c288bbb22a3acc3d5e6b82e6f |
| proto.proto | 59012 | 317 | 36 | a5def4a263d211158fc652642693867fbbebc1639994b107e5dcced7b7e28534 |

Results checked by regenerating from local main.rodata and comparing
SHA256 against independently extracted binary descriptors. The generated
text was compared against the earlier standalone research-kit schemas;
it differs only in introductory comments. The script is tailored to the
observed descriptor layout and is not a general NSO extractor.

These descriptors give client-readable **wire structure**, not known
backend policy, security keys, or server-approved values. Recovering
**client response handling** now requires ARM64 code tracing in addition
to decoding schemas. The local candidate EnvironmentList in
\`mvp_server.py\` has not been tested on a physical Switch.

Files under generated-descriptors/ are ignored to prevent accidentally
committing reconstructed game metadata without review.
