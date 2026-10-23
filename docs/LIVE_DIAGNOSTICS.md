# Live WWZ diagnostic uploads (October 2026)

Authored by **OpenAI ChatGPT (GPT-6)**. Changes only on `research/chatgpt-hydra-server-mvp`.

The experimental server now processes `WriteADFPack` live in `post_login.py` using `diagnostic_live.py` and the existing bounded inspector in `diagnostic_deep_probe.py`. It prints only recognized marker strings, format types and verified gzip/zlib/ZIP extraction. This means `--capture-dir` is **not required** for basic diagnostics.

When reviewing the console, find:

```text
INFO Client diagnostic pack (strings NOT confirmed as errors): {'packed_fields': ..., 'verified_decompression': ..., 'known_marker_strings': [...]}
```

The collaborator ZIP demonstrated that some packs contain the exact string:

```text
autogen VersionDataType_Last does not corresponds with backend values
```

**Interpretation limit:** Presence of this string in a diagnostic pack does not prove the Switch raised that error in the current run. ADF data may include a string table containing known messages. Absence of any recognized marker does not exclude an unrecognized error.

Parsing is bounded and failures still return the exact same diagnostic success ACK. Never log raw account credentials, arbitrary ADF string values or real access tokens on an internet-exposed host.

## Your Linux lab

```bash
cd /data/repos/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p test_diagnostic_live.py -v

# Stop previous server (Ctrl+C) before re-running:
python3 mvp_server.py --host 0.0.0.0 \
  --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt \
  --key certs/server.key
```

`routes.remote.local.json` is a local untracked configuration advertising the user's own public IPv4; do not replace it with example JSON or publish it as a sample with private IP data.

## Original Windows test checkout

```powershell
cd "$HOME\OneDrive\Desktop\wwz-switch-lab-research"
git pull --ff-only
py -m unittest discover -s tests -p test_diagnostic_live.py -v
py mvp_server.py --host 0.0.0.0 --ports 11701,11702,11704 --routes routes.heartbeat-versions4.example.json --cert ..\wwz-switch-lab\certs\server.crt --key ..\wwz-switch-lab\certs\server.key
```

## ZIP checkout

Download the latest branch ZIP at
`https://github.com/AJstylishhh/wwz-switch-lab/archive/refs/heads/research/chatgpt-hydra-server-mvp.zip`.
Extract alongside existing `certs`; no setup script is needed.

```powershell
cd "$HOME\OneDrive\Desktop\wwz-switch-lab"
py -m unittest discover -s tests -p test_diagnostic_live.py -v
py mvp_server.py --host 0.0.0.0 --ports 11701,11702,11704 --routes routes.heartbeat-versions4.example.json --cert .\certs\server.crt --key .\certs\server.key
```

If the diagnostic report is empty but heartbeat unregister persists, the next step is decoding the actual ADF *entry* and identifying runtime events, not assuming missing text means no client error.
