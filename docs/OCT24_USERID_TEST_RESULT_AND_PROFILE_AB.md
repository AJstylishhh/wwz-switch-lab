# Oct 24: two physical Switches — confirmed cross-player public UserId lookup

Authored by OpenAI ChatGPT (GPT-6). Research branch only. Source:
user-uploaded `userid-test-20261024-192301.log` (3784 lines);
raw log is not committed.

## Observed behavior (reported by tester)

Both physical Switches intermittently showed "connection lost", throwing them
back to the menu when creating/joining a lobby. On each console, restarting
the game permitted lobby entry. Even after both could search, neither saw
the other player.

## High confidence log findings

- Lab server started 19:23:01, while a console was apparently still running
  with credentials from a previous session. At **19:27:29–19:27:33**,
  one network source (`4aae96d55cbd`, ephemeral label) tried refreshing
  **old unrecognized credentials** three times. 9 lobby requests were
  denied with `Cannot assign lobby RPC to a signed-in user: unrecognized or
  ambiguous issued credential` (HTTP 409). It also attempted two
  unknown 22-byte user lookups, reporting `issued_user_matches=0`.
  A Heartbeat.UnRegister followed. This correlates plausibly with the
  "connection lost" UI. It is not evidence of corrupt player data or a
  failed new sign-in.
- The same source performed new Enqueue/Dequeue at **19:29:01–19:29:02**.
  Its issued `acl-token` then consistently resolved with
  `identity_resolution=issued_token`, created a squad at 19:29:06
  and queued playlist `384cb92196d4` at 19:29:22.
- A different source (`0ac4d00c1d4f`) completed fresh Dequeue at
  **19:37:20**, initially tried playlist `ba80609b8acc` then
  `384cb92196d4`. These HMAC tags are process-local and must not
  be compared with tags in prior logs.
- At **19:40:17**, the first source logged in **again**, creating a
  second active session from the same public IP and a third lobby.
  This is expected with isolated session keys but leaves a stale
  one-person lobby until TTL; do not discard existing NAT sessions
  automatically. The authenticated `acl-token` still identifies the
  active session correctly.
- At **19:41:52.421** the new session of source A started playlist
  `384cb92196d4` and joined the queued lobby of source B.
  `decision=joined_existing_queue, members=2, group_count=2`.
  At 19:42:28, status returned `members=2, queued=True`.
  `group_count=2` counts the additional stale one-person lobby;
  it is **not** two players in different matchmaking groups.
- **BREAKTHROUGH:** at 19:42:29.823 the other Switch called the previously
  unmapped 22-byte RPC with **one verified other player's locally
  issued UserId**, confirmed by
  `issued_user_matches=1, requester_verified=True,
  includes_requester=False, other_issued_users_requested=1`.
  This repeated at 19:42:32, 19:42:35, 19:43:00, :02, :05, :32,
  :34, :37 — **nine** post-match lookups, all returned HTTP 404.
  These requests are strong evidence that the mapped candidate is
  `IUserService_GetUsersPublicData`, but the native GUID-to-method
  binding remains inferred.
- At 19:42:06 and 19:42:35, one client called `MatchmakeStop` and
  the current lab implementation cleared the queued flag for the
  two-member group. This group-global queue model is still only an
  approximation and might later need separate client states.
- The first failure at 19:27 and failure of the authenticated,
  two-player matchmaking at 19:42 are **distinct stages**. Restarting
  is a plausible fix for stale client login after server restart; it
  cannot make a 404 post-match profile response succeed.

## Why the next experiment is appropriate

We have the actual extracted protobuf schemas:

```proto
message IUserService_GetUsersPublicData {
  repeated backendPb.UserId users = 1;
}
message UserBaseData {
  optional backendPb.UserId User = 1;
  optional string Nickname = 2;
  repeated backendPb.UserState UserStateData = 3;
  optional backendPb.ClanPublicInfo ActiveClan = 4;
  optional string ProviderId = 5;
  optional string ProviderUserId = 6;
}
message ServiceResult_List_UserBaseData {
  repeated backendPb.UserBaseData data = 1;
}
// In ServiceResult:
optional backendPb.ServiceResult_List_UserBaseData ServiceResult_List_UserBaseData = 194158588;
```

The exact RPC shape and native grouped GUID table remain evidence for,
not definitive proof of, the method mapping. We **do not** have a real
official-server plaintext response or a known accepted username format.

## New candidate response (opt-in only)

`--experimental-public-user-data` enables a typed
`ServiceResult(retCode=0, ServiceResult_List_UserBaseData(...))` reply
on *only* the exact observed post-match RPC.

It requires `--lobby-mvp --lobby-session-ids`; validates the
**locally issued ACL token**; checks that all requested user IDs belong
to the caller's **same existing lab lobby**; and returns
`UserBaseData.User` and a marked synthetic `UserBaseData.Nickname`.
Any missing token, malformed packet, unknown user or different lobby
continues to get HTTP 404. No stable Nintendo identity, real user profile,
friends list, game endpoint, UDP routing or authoritative simulation is
faked. With flag omitted, all behavior is unchanged. Run the new tests
first, then perform a controlled A/B test to see if the Switch leaves
the repeated lookup stage.

Stop the old server. On the VPS:

```bash
cd /opt/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p test_public_user_data.py -v
python3 -m unittest discover -s tests -p test_post_match_user_probe.py -v

umask 077
mkdir -p logs
PYTHONUNBUFFERED=1 python3 mvp_server.py \
  --host 0.0.0.0 --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt --key certs/server.key \
  --trace-clients --lobby-mvp --lobby-session-ids \
  --trace-post-match-users --experimental-public-user-data \
  2>&1 | tee "logs/profile-test-$(date +%Y%m%d-%H%M%S).log"
```

**Force-close/restart WWZ on both physical Switches after restarting
the VPS server** so clients do not replay old in-memory synthetic credentials.
Both clients must choose exactly the same playlist. Note whether either
screen now shows a second player, displays a loading state or emits new
RPCs (especially after `Experimental public user-data reply`).
Send the complete log, not just filtered lines.

Rollback: restart same server command WITHOUT
`--experimental-public-user-data`. Nothing is persisted or changed in
local routes; the flag does not implement playable online sessions.
