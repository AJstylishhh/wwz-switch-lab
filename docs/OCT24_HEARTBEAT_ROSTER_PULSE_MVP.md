# 2026-10-24 — Nine-entry heartbeat roster experiment

Authored by OpenAI ChatGPT (GPT-6). Research branch only.

## Evidence

The user-provided Switch NSO (SHA256 `0e93e33bf2026f031dfcbc0bf51eba85cd6ee1e7e2305f11abecfaddded6560c`) was decompressed locally. At text offset `0xc06318`, the ARM64 instruction is `cmp w1, #9`; the following instruction branches if the version count differs. The error branch references the exact string `autogen VersionDataType_Last does not corresponds with backend values`. This establishes the required version count for this specific build: **nine**.

The nearby application code consumes indices 0, 1, 2, 4 and 6 through dedicated processing paths. Their meanings (including which one signals a new lobby) are not established.

## Changes

The opt-in registry no longer lets one participant's Stop cancel another participant's existing search. A participant choosing another playlist is detached from the former shared queue. Changes to membership increment `Lobby.roster_revision`; routine GameData updates do not.

The new flag `--lobby-version-pulse` requires `--lobby-mvp --lobby-session-ids`. On a verified user's Heartbeat.Update, it increments just the five observed candidate version slots by the bounded roster revision. It retains exactly nine entries and leaves other users' replies unchanged. This is an **experimental notification hypothesis**, not a verified method mapping. The behavior is OFF by default and rollback is removing the flag.

Unit tests cover authenticated same-network-session isolation, typed HTTP encoding, cancellation, playlist changes, and unchanged behavior when the flag is disabled.

## One coordinated hardware test

Stop the old server and pull the updated research branch. Force-close both games after the server has restarted. Use the same public playlist on both physical Switches.

```bash
cd /opt/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p 'test_queue_member_isolation.py' -v
python3 -m unittest discover -s tests -p 'test_lobby_version_pulse.py' -v

umask 077
mkdir -p logs
PYTHONUNBUFFERED=1 python3 mvp_server.py \
  --host 0.0.0.0 --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt --key certs/server.key \
  --trace-clients --lobby-mvp --lobby-session-ids \
  --trace-post-match-users \
  --lobby-version-pulse --experimental-public-user-data \
  2>&1 | tee "logs/pulse-test-$(date +%Y%m%d-%H%M%S).log"
```

Expected server events: both clients sign in, one `joined_existing_queue` with `members=2`, then a unique `Experimental heartbeat roster-version pulse` for each participant. Look for *new* GetStatusSquad, GetStatusMatchmake or post-match UserId lookups **after** the pulse. The user-visible result is the decisive outcome; internal `members=2` alone does not prove a working lobby.

If anything breaks, remove `--lobby-version-pulse`. Remove `--experimental-public-user-data` too to restore the original profile-RPC 404 behavior. No settings or saved player data are changed.

**Limitations:** The version slot-to-lobby mapping, server push semantics, real game session allocation and gameplay transport are still unverified. Keep raw logs and user credentials out of the public repository.
