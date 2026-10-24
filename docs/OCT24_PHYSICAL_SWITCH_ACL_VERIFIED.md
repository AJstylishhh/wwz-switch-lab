# Oct 24 physical Switch-only `acl-token` capture and confirmed internal pairing

Authored by OpenAI ChatGPT (GPT-6), research branch only.

## Hardware clarification

The user explicitly confirms **no Citron emulator was used** for the file `acl-test-20261024-151418.log`. The log contains two IP-source HMACs, `5ec5e446977c` and `84b7577d0d37`; both correspond to physical Switch-originated traffic for this test. Do **not** attribute login resets or TLS differences to an emulator in this capture.

## Credential result: the missing identity mechanism is now established

With `--trace-acl-match`, source A signed in at 15:15:49 and its post-login Presence + candidate MatchmakeStart calls include `acl-token` that the backend **confirmed matches its own issued AccessRoleToken** (logged `issued_token_type: access_role`, `acl_tag: 7e393f36febf`). Source B signed in at 15:17:43; its Presence and MatchmakeStart calls include a **different issued AccessRoleToken** (`acl_tag: 4536ec3c24bb`). Both sent 2-byte/4-byte status queries with their own issued tokens.

A's Dequeue carried a previous `acl-token` that logged `unrecognized` *before the new SignInResult was issued*; B's Dequeue lacked the header. This is expected: the safe identity scheme must validate the **post-login** ACL token, not assume every pre-login client-asserted credential is valid. The old `--trace-clients` log has a different `credential_tag` because it uses a different keyed HMAC domain. Both compare only within the same server process.

**Result:** `--lobby-session-ids` already has sufficient real-client evidence for the known Presence methods. It validates the `Acl-Token` header against locally issued access/authorization tokens and indexes separate issued UserIds. A separate HTTP integration regression now verifies two same-IP sessions using distinct `acl-token` AccessRoleTokens join the same queue instead of overwriting one another. **Real same-NAT hardware use is not yet tested**; the two sources in this capture were already distinct.

## Other log facts

- First A queue started at 15:16:58; after a client stop at 15:17:00 it started again at 15:17:02.
- B began searching a **different** playlist (`c76c34937493`) at 15:18:24, so the registry correctly logged `playlist_differs` against A's `8effec0cf8e4`.
- B switched to the same playlist and at **15:18:33.485** server logged **`joined_existing_queue`, `members=2`, `group_count=1`, `max_count=4`**. Neither token nor player UID is printed.
- At 15:19:09 A called `MatchmakeStop`, and the current experimental *group-global queued flag* turned False for **both** members. Subsequent Starts retained the same two-person group but group-wide semantics are still a protocol approximation; this may be an issue to investigate separately.
- At 15:20:52 and 15:20:53 A's GetStatusSquad/Matchmake candidates both reported **members=2, queued=True**.
- At **15:20:54, 15:20:56 and 15:20:58** A sent previously unmapped RPC `/8aa8a8fb77a6450cb44b11e823a7c959.svc/4be808a1e9a842e581ee6eb47e8cd5eb`, **22 bytes each**, with an explicitly decoded nested shape: `field1 length20 => field1 length18 => fixed64 fields1+2`. This is **exactly one** `backendPb.UserId` wrapped in repeated field1 as defined by `IUserService_GetUsersPublicData` in the extracted `proto.proto`. Earlier 44-byte requests for this method could encode two such users. This is strong evidence for **a user-public-data lookup**, though the GUID-to-method mapping and response semantics are not yet dynamically confirmed. Server currently replies HTTP 404; don't invent a profile response without its correct structure. If mapping is validated, the likely typed reply is `ServiceResult.ServiceResult_List_UserBaseData` (field 194158588) containing repeated `UserBaseData { User, Nickname, ... }`.
- No claim of player-visible discovery, actual game session launch or P2P connectivity: the log establishes only server internal pairing and an unanswered post-match lookup.

## Next clean device test

Stop the current Python server and on VPS:

```bash
cd /opt/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p test_lobby_identity.py -v
umask 077
mkdir -p logs
PYTHONUNBUFFERED=1 python3 mvp_server.py \
  --host 0.0.0.0 --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt --key certs/server.key \
  --trace-clients --lobby-mvp --lobby-session-ids \
  2>&1 | tee "logs/physical-switch-sessions-$(date +%Y%m%d-%H%M%S).log" \
  | grep --line-buffered -E 'Listening|Experimental lobby identity:|lobby_mvp_start|lobby_mvp_match_status|Cannot assign lobby RPC|Unmapped RPC: /8aa8|ERROR'
```

Test both real Switches on same public quick-play playlist, initially with their usual distinct external IPs. If working, optionally test two on same NAT to confirm issued ACL tokens select the right session. If the server emits `Cannot assign lobby RPC` / 409, stop the experiment and fall back to `--lobby-mvp` **without** `--lobby-session-ids` until the offending request is understood. The default behavior, hosted routes, user-facing devices and firmware do not otherwise need changes.

The next protocol milestone is correctly responding to the **one-UserId profile RPC**, not more arbitrary changes to matching; the client has already made a two-player in-memory group.
