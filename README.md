# wwz-switch-lab (main)

**Full Matty research tree** + **Grok soft-session layer** on `mvp_server.py`.

Research branch `research/chatgpt-hydra-server-mvp` is unchanged.

## Folder

```powershell
cd "$HOME\OneDrive\Desktop\wwz2-switch-lab-2"
git fetch origin
git checkout main
git reset --hard origin/main-with-research-soft
.\gen_certs.ps1
.\run-mvp.ps1
```

Or after main is updated to this tip: `git pull` then `.un-mvp.ps1`.

## Soft-session (default on)

- `datacenter_id=local` on environment discovery
- Teardown SignOut/PresenceDisconnect GUIDs -> Success
- Soft post-login (shape errors -> Success not 400)
- Unmapped GUIDs -> Success + log
- Queue TTL 15 min
- `--no-soft` restores strict research behavior

Still not finished matchmaking. Watch for session hold + new GUID paths.
