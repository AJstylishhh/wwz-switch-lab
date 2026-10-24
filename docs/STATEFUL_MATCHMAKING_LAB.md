# Two-player matchmaking registry experiment (opt-in)

Authored by OpenAI ChatGPT (GPT-6). Research branch only. Do not merge this into main or advertise the server as playable.

## What we now know

Two Switch consoles, seen in the October 23 VPS trace as different ephemeral source tags, successfully authenticate and separately send the same candidate `IPresenceService_MatchmakeStart` RPC (method GUID `67cdaf75ca604bd993ad9f1db0c3f812`). However, the previous `enable_lobby_rpc_probe.py` returns only bare ServiceResult Success for these paths and the default typed GetStatusMatchmake reply always reports msMenu (0). That cannot create shared server-visible matchmaking.

The Switch binary's extracted proto2 descriptor includes `IPresenceService_MatchmakeStart.dcPings/mmOptions/playlist/variants`, `SquadStatusResponse`, `SquadStatus.SquadMembers`, `MatchmakeStatusResponse`, `MatchmakeStatus.StatusQueue.PartyMembers`, and state `MatchmakeSessionState_msQueue=1`. The GUIDs are inferred from request layout rather than independently confirmed native method references. No listener for gameplay transport has been implemented.

## Implementation

`lobby_registry.py` now provides an in-memory lab registry:

- `SquadSetSettings`, `SquadSetGameData`, and `SquadSetInvitesState` candidate methods populate one squad per previously authenticated source.
- `MatchmakeStart` places that source in the matching queue, pairing two separately authenticated sources with the **exact same playlist string**. Only already-queued groups are eligible; merely creating a local squad does not advertise a match.
- It emits descriptor-grounded `PresenceStatusResponse.Squad` and `.Matchmake` status with stable synthetic member UserIds, squad ID, owner, count, and msQueue state when the respective candidate GetStatus methods are called.
- `MatchmakeStop` clears the queued flag. Idle squads are pruned after 30 minutes. Registry limits are 128 groups and 256 client sources.
- It associates a completed Dequeue identity with a temporary keyed digest of the network source IP. This is a lab-only approximation; **two Switches behind the same public NAT address are not distinguishable** without decoding/validating request authorization headers or session tokens. The previous trace had distinct tags and should permit two-source testing.
- No raw IPs, raw packets or token strings are logged or written to disk. The running process still holds temporary GameData and playlists in RAM.

`mvp_server.py --lobby-mvp` enables this behavior only for the seven exact observed paths. Without the flag, the old route table/working menu/lobby UI continues byte-for-byte unchanged. Do **not** change the JSON success probes; the opt-in server intercepts those routes in memory.

## What this does NOT do

- Does not implement actual game session allocation, multiplayer packet forwarding/UDP, join codes, invitations, public lobby *list* response, peer handoff or a verified connection to the client-side session lobby view.
- Does not send unsolicited notifications to Switches. The observed log has the two candidate GetStatus calls near login, **not after the attempted MatchmakeStart**. If the game expects server push or another status refresh trigger, the registry may show `members=2` internally but the Switches may not show each other yet.
- Does not have a verified mapping between all hashed presence GUIDs and method names. The status mappings are request-schema hypotheses.
- Does not replace Nintendo's Network Service / eShop licensing applet on the device.

## Recommended next VPS A/B test

Stop the Python process. Preserve the working local config, certs and host redirect.

```bash
cd /opt/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p 'test_lobby_registry.py' -v

umask 077
mkdir -p logs
PYTHONUNBUFFERED=1 python3 mvp_server.py \
  --host 0.0.0.0 --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt --key certs/server.key \
  --trace-clients --lobby-mvp \
  2>&1 | tee "logs/lobby-state-$(date +%Y%m%d-%H%M%S).log"
```

1. Switch A: fully restart WWZ, enter Online, create a **public** lobby and leave it open.
2. Switch B: fully restart WWZ, enter the same **public** mode / quick-play playlist (not Private), try to search/join. The separate console's `Multiplayer` eShop redirect remains unaddressed; use the working Online mode.
3. Note what *each* screen displays and any changes, especially whether either one shows the other's username, player count, queue or lobby. Upload the complete log.
4. Look for `Experimental lobby registry: {'stage': 'lobby_mvp_start', 'lobby_present': True, 'members': 2, 'queued': True, 'group_count': 1}`. This shows **internal matching only**, not proven network gameplay or UI discovery.
5. With one client, compare candidate `squad_status` and `match_status` log lines before/after matching. If there are **no status reads after Start**, our next reverse-engineering task is the delivery/notification mechanism, not another 0800 reply.

Rollback: stop Python and restart the same command **without** `--lobby-mvp`. No JSON edit, database migration or device firmware change is necessary.

All tests use synthetic protobuf, synthetic UUIDs, and localhost HTTP. GitHub Actions runs the full regression suite. The environment and token logic are unchanged when the opt-in flag is not used.
