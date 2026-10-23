# Switch ARM64: nine VersionDataType entries required

**Author: OpenAI ChatGPT (GPT-6).** October 23, 2026.
Research is limited to user-provided WWZ Switch NSO `main` in `wwz exefx.zip`.
Never add the game binary, decrypted captures, private keys, or other copyright-protected binaries to this repo.

## Binary provenance and static evidence

- Original NSO `main` SHA-256: `0e93e33bf2026f031dfcbc0bf51eba85cd6ee1e7e2305f11abecfaddded6560c`.
- NSO segments are LZ4 block compressed. Text decompressed RVA begins at 0, RODATA decompressed RVA begins at `0x2131000`.
- The client diagnostic literal `autogen VersionDataType_Last does not corresponds with backend values` resides at RODATA offset `0x571847`, RVA `0x26A2847`.
- Its **ADRP+ADD** text reference occurs at `0xC063D4/0xC063D8` and is used in the mismatch branch. This demonstrates the literal is used by this count check, not just nearby unrelated text.

The relevant AArch64 instructions disassemble to:

```asm
0xC06314  ldr   w1, [x0, #0x10]       ; read count
0xC06318  cmp   w1, #9
0xC0631C  b.ne  0xC063C4              ; mismatch
...
0xC063C4  adrp  x0, 0x2632000
0xC063C8  add   x0, x0, #0x266
0xC063CC  mov   w2, #9
0xC063D0  bl    0x94C1C0
0xC063D4  adrp  x8, 0x26A2000
0xC063D8  add   x8, x8, #0x847        ; literal RVA 0x26A2847
0xC063DC  str   x8, [sp]
...
0xC063F0  bl    0x952670              ; diagnostic output
```

Two direct caller sites of the count-validation function at `0xC062F0` are `0xC05E1C` and `0xC065E8`. The check reads the count at offset `+0x10` from the passed object. This is consistent with the client's version collection mapping.

**High confidence:** this binary's `VersionDataType_Last` check expects a count of **nine**, not four.
**Unverified:** whether all nine values are the same `8802288`, whether the game also validates per-version semantics, and whether this check alone causes the online-menu failure.

## Isolated remote test

Prior 4-entry heartbeat test failed with the marker still present in the second diagnostic pack. New `routes.heartbeat-versions9.example.json` changes **only** `UserVersions.Versions` in Heartbeat.Register and Heartbeat.Update from empty to nine repeated int64 values of `8802288`; presence remains 0, all other route settings unchanged.

For the Linux host, retain the public-IP-configured `routes.remote.local.json` and update ONLY its two heartbeat lists:

```bash
cd /data/repos/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p test_heartbeat_versions9.py -v
python3 set_heartbeat_versions.py routes.remote.local.json 9
python3 mvp_server.py --host 0.0.0.0 --ports 11701,11702,11704 \
  --routes routes.remote.local.json --cert certs/server.crt --key certs/server.key
```

Terminate the previous server before restarting. Test once from the Switch. Relevant output lines:

- `heartbeat_register` and `heartbeat_update`: `version_count: 9`;
- `Client diagnostic pack`: whether marker `VersionDataType_Last` still appears in the **second** compressed pack;
- `heartbeat_unregister`: whether it remains immediate;
- new RPC paths or repeated heartbeat updates and in-game result.

Do not treat the absence of the marker as proof that connection succeeded: the decoder matches known strings but does not decode event-level context. Likewise, a marker might appear as a string constant. Record game outcome separately.

### Local Windows Git test (if needed)

```powershell
cd "$HOME\OneDrive\Desktop\wwz-switch-lab-research"
git pull --ff-only
py -m unittest discover -s tests -p test_heartbeat_versions9.py -v
py mvp_server.py --host 0.0.0.0 --ports 11701,11702,11704 --routes routes.heartbeat-versions9.example.json --cert ..\wwz-switch-lab\certs\server.crt --key ..\wwz-switch-lab\certs\server.key
```

### Windows ZIP download

Latest [research branch ZIP](https://github.com/AJstylishhh/wwz-switch-lab/archive/refs/heads/research/chatgpt-hydra-server-mvp.zip); extract next to existing certs and then run:

```powershell
cd "$HOME\OneDrive\Desktop\wwz-switch-lab"
py -m unittest discover -s tests -p test_heartbeat_versions9.py -v
py mvp_server.py --host 0.0.0.0 --ports 11701,11702,11704 --routes routes.heartbeat-versions9.example.json --cert .\certs\server.crt --key .\certs\server.key
```

## Next hypothesis if count nine still fails

Find whether the game validates individual values (e.g., which version types are assigned to each index). Do not randomly change the expected cardinality, and do not assume an extended session proves that online matchmaking works.
