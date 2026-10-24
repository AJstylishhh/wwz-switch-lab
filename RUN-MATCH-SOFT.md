# Soft matchmaking fix (Grok 2026-10-24)

Main briefly had a bad lobby_registry placeholder. Fix locally:

```powershell
cd "$HOME\OneDrive\Desktop\wwz2-switch-lab-2"
git fetch origin
# restore full file from research tip
git show origin/research/chatgpt-hydra-server-mvp:lobby_registry.py | Set-Content -Encoding utf8 lobby_registry.py
```

Then either pull this commit's `lobby_registry.py` when published, or ask Grok for the patched file.

## What the fix does
1. Strip playlist strings before compare
2. If exact playlist match fails but **exactly one** other open queued lobby exists, **join it** (`joined_soft_playlist_mismatch`) — covers 167 vs 144 byte public queues
3. Status polls without Dequeue correlation return empty success instead of HTTP 400

## Run
```powershell
py mvp_server.py --host 0.0.0.0 --ports 11702,11704 --routes routes.session-test.local.json --lobby-mvp
```
Both clients must **fully re-login** after server start. Watch for `Experimental lobby registry: ... decision`.
