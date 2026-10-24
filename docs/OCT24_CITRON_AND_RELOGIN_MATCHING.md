# 2026-10-24 13:52–14:08: Citron, console re-login and unmatched lobby attempts

Authored by OpenAI ChatGPT (GPT-6), not repository owner. Research branch only.

## Source / important qualifications

User-uploaded match-decisions-20261024-135227.log, 2241 lines. User reports first two environment-discovery requests were likely the Citron emulator; later a physical Switch and another player attempted to join but didn't find each other. Ephemeral source tags identify a network source and may aggregate emulator and hardware behind a NAT. Do not infer hardware identity from tags or IPs alone.

## Discrete protocol sequence (server clock)

- 13:57:31 and 13:57:43: only environment discovery, both from `77422f04648d` over TLSv1.3 for first connection; no complete login. Consistent with the reported Citron tests.
- 13:58:46 and 13:58:50: same source tag now uses TLSv1.2, discovers and signs in; sets a four-player squad at 13:58:52.
- 14:02:41: source `77422f04648d` starts matchmaking (`c84ef4e06741`, 9-byte playlist). A brief stop occurs at 14:02:42, then same source starts again at 14:02:44.
- 14:04:16–14:04:22: new source `dedabcca2939` starts sign-in, **while source `77422f04648d` performs another fresh Dequeue** and receives a new synthetic identity. The registry currently keys by HMAC of the public IP, and its `attach` logic calls `_leave` for a different UserId on the same source key. This silently removes the original queued lobby. Subsequent `group_count=1` reflects this reset, not that two sources cannot coexist.
- 14:05:11: source `dedabcca2939` starts matchmaking with different 9-byte playlist HMAC `2d1d52a2066c`; registry reports `no_other_queue` because the other source's queued group was already cleared.
- 14:05:17–14:06:31: repeated Start with the same playlist, still no other queued group.
- 14:06:57: source `77422f04648d` invokes zero-byte unimplemented `f05e89628988405c89a51dc520957cae`; it calls `MatchmakeStop` at 14:06:58 and remains unqueued.
- 14:07:07–14:08:30: source `77422f04648d` repeatedly invokes another unimplemented **zero-byte** GUID `a5849554ff43457e88339d6a58fd6116`, about five times with initial ~5–7 second spacing. This could indicate missing menu/discovery functionality but exact method mapping has NOT been proven.
- 14:07:10: source `dedabcca2939` starts with playlist tag `c84ef4e06741`, which **matches the earlier tag from `77422f04648d`**, but that original queue had disappeared and is not active now. Therefore `no_other_queue` is correct.
- No successful `joined_existing_queue` or two-member group in this trace.

## What the HMAC labels prove

- `c84ef4e06741` and `2d1d52a2066c` are genuinely different exact nine-byte playlist strings within this one Python process. They may represent different modes, public/private or other matchmaking selections; log does not reveal their text.
- Later reuse of `c84ef4e06741` by the other source proves the two consoles sometimes request the same playlist. **Their queue activity just didn't overlap while that playlist was active.**
- Repeated `b2ba5509c32e43f09b39cb0a828059df` single scalar requests predominantly report 0 while unqueued and 1 while queued on one source. Consistent with, but not proof of, `IPresenceService_SetGameClientState`.
- All squad settings in observed sessions report `max_count=4`, so capacity was NOT a blocker in this test.
- The logged raw HTTP requests did not contain known auth headers (there are source tags but no credential tags). This does not rule out custom headers or identity inside protobuf, but implies using only the public IP for unique player sessions is a known limitation.

## Changes after reviewing this log

`lobby_registry.py` now returns privacy-limited metadata for each completed Dequeue attachment: whether a different synthetic identity replaced another for the same source key, whether the previous source had a lobby, whether it was queued, previous member count, and remaining group count. Explicit `MatchmakeStop` now reports `decision=client_called_stop` and `previously_queued`, without changing the reply payload. `mvp_server.py` prints this attachment metadata only in opt-in `--lobby-mvp` mode. Regression tests cover duplicate-user replacement, queue loss and stop, with full GitHub CI.

## Reproduction: focus on two physical Switches and avoid test interference

1. Fully exit Citron and all other WWZ instances using the same public IP before launching the test. Restart the VPS Python process to clear stale synthetic identities and lobbies.
2. Run the exact same working `--trace-clients --lobby-mvp` command. On Switch A: complete fresh sign-in, choose **public Quick Play** for a specified map/playlist, start the queue and stay queued.
3. On Switch B on a *different external network*: fully restart WWZ, choose the identical public Quick Play selection and keep matchmaking active. Distinguish *public matchmaking* from *private lobby browsing*; this backend has **no browse/list endpoint** yet.
4. Check for `source_replaced: true` on the A login; if it appears, A's queue may have been invalidated by another same-IP process. Compare `playlist_tag` and `decision` at both clients' Start calls and verify `joined_existing_queue` / members=2.
5. If server achieves two members but neither console sees the other, stop repeating pairing tests and investigate status/event-delivery RPCs, including GUIDs `a584...` and `f05e...`; the existing game requests only status at login and may need notification/poll responses. **Don't assign GUID mappings or return blanket 0800 without evidence.**

Rollback is to omit `--lobby-mvp`; no need to revert Git or the JSON routes.

Concise output without discarding logs:

```bash
cd /opt/wwz-switch-lab
git pull --ff-only
umask 077
mkdir -p logs
set -o pipefail
PYTHONUNBUFFERED=1 python3 mvp_server.py \
  --host 0.0.0.0 --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt --key certs/server.key \
  --trace-clients --lobby-mvp \
  2>&1 | tee "logs/concise-lobby-$(date +%Y%m%d-%H%M%S).log" \
  | grep --line-buffered -E 'Listening|Experimental lobby registry:|Unmapped RPC:|rejected|ERROR'
```

The full log still goes to the private file; heartbeat spam is filtered from the terminal only.
