# Oct 24 two-Switch lobby-state trace: two queues, no joined session

Authored by OpenAI ChatGPT (GPT-6), not repository owner. Research branch only.

## Source and environment

Source: user-supplied lobby-state-20261024-004244.log, 911 lines, 00:42:45–00:50:43 Europe/Berlin (server clock). Running experimental --trace-clients --lobby-mvp.

Both consoles were pointed at the correct VPS IP, fixing the unrelated previous wrong-IP error. Log includes 457 POST calls across two stable per-process source tags and contains no WARN, ERROR or traceback lines.

## Two network sources, not joined

| Observation | Source 5ed76dd54bb8 | Source a59454d6b56f |
| --- | --- | --- |
| Dequeue SignIn | 00:44:42 | 00:46:15 |
| Lobby settings and game data recorded | 00:44:45 | 00:46:20 |
| First matchmaking candidate Start | 00:44:57 (167 B) | 00:47:17 (144 B) |
| Second matchmaking candidate Start | 00:49:46 (167 B) | 00:47:23 (144 B) |
| Heartbeat updates | 205 | 150 |
| Rapidly repeated scalar GUID b2ba5509... | 47 | 1 |

The first matchmaking call created group_count=1, members=1. When B prepared a squad, group_count=2, members=1. At B's two Start calls, group_count stayed 2 and members=1. When A re-sent Start at 00:49:46, group_count was still 2 and members=1. No line shows members=2 or one common group. Both connections remained healthy.

The two MatchmakeStart payload lengths differ (167 B vs 144 B), but the HTTP log does not contain the actual playlist field. A payload size difference alone DOES NOT prove a different playlist. The registry joins only if:

1. the other group is already queued;
2. the playlist string exactly matches; and
3. the other group has free seats, based on SquadSettings.MaxCount from the validated protobuf definition.

At B's start all parties had already met condition (1), so the next likely explanations are playlist mismatch or MaxCount/capacity. The existing logging did not identify which; do not arbitrarily merge queues or override private lobbies.

## Unmapped repeated two-byte method

Source A emitted **47** POSTs on Presence GUID `b2ba5509c32e43f09b39cb0a828059df` beginning at 00:49:47, about every 0.6 seconds; source B emitted one at 00:47:17. Requests are only 2 bytes. Previously this returned static `0800` and was called a possible game-client state transition, but exact GUID-to-method mapping remains UNKNOWN. The frequency could indicate a status loop or repeated reporting; neither is established. Do not assume this is a get-status query, nor send an invented typed response.

## New diagnostic code

`lobby_registry.py` now logs only a keyed, ephemeral `playlist_tag` (process-random HMAC, no raw playlist), `playlist_bytes`, number of other queued groups, number with identical playlists, open seat count, and explicit decision:

- `no_other_queue`: no other source currently queued.
- `playlist_differs`: one or more other queues exist but no exact playlist match.
- `matching_queue_full`: a playlist matches, but configured SquadSettings.MaxCount leaves no room.
- `joined_existing_queue`: same playlist and capacity, member added to the shared registry.

The actual configured `max_count` is also logged when SquadSetSettings is called. The repeated two-byte GUID now gets passive field-1 scalar observation, with only the first value, changes and each 20th repeat logged; the HTTP reply remains bare protobuf Success. This reduces repeated diagnostic noise. No raw IPs, account tokens, strings or packets are stored.

All new instrumentation is within existing opt-in `--lobby-mvp`. Existing no-flag behavior remains byte-for-byte the same. Tests: `tests/test_lobby_matching_diagnostics.py` and the earlier full suite.

## Next hardware test

Stop server with Ctrl+C and on VPS:

```bash
cd /opt/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p test_lobby_matching_diagnostics.py -v
umask 077
mkdir -p logs
PYTHONUNBUFFERED=1 python3 mvp_server.py \
  --host 0.0.0.0 --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt --key certs/server.key \
  --trace-clients --lobby-mvp \
  2>&1 | tee "logs/match-decisions-$(date +%Y%m%d-%H%M%S).log"
```

Switch A: choose a **public** lobby/Quick Play mode and stay queued. Switch B: choose **the exact same playlist/mode** and try joining/Quick Play. Compare what each console UI shows. This experiment does not implement browse-list UI, invitation, join-code or UDP gameplay transport.

To inspect bounded diagnostics without sharing tokens:

```bash
grep -E 'Experimental lobby registry:|Unmapped RPC|request rejected' logs/match-decisions-*.log
```

If `playlist_differs`, compare precise game mode/map/playlist selections. If `matching_queue_full`, confirm client-descriptor MaxCount and game-specific mode settings before any changes. If `joined_existing_queue` / members=2 but client still sees nothing, identify the SDK request or pushed event by which it learns matchmaking state; this remains unsolved. The repeated b2ba... scalar might become a lead only after the safe value is observed.

Rollback: stop server and restart without `--lobby-mvp`. No JSON or firmware changes required.
