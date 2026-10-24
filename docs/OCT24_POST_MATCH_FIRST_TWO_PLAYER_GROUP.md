# Oct 24 14:20: successful in-memory two-source pairing, new post-match RPC

Authored by OpenAI ChatGPT (GPT-6), not repository owner; research branch only.

## Evidence from user log

Input: `next-test-20261024-142001.log`, 1521 lines, 14:20:02–14:26:56 server time on Oct 24, 2026.

- Source `7c7b48c99cb3` logs in at 14:20:47, creates a four-seat squad, and starts playlist HMAC `22abe3124c92` at 14:20:57.
- A second network source `20a5eeb166d5` logs in at 14:22:37. It searches different playlist HMAC `551fb403d76d` at 14:23:04. These source tags represent **IP addresses**, not proven hardware, emulator or per-session identities.
- At 14:24:09, `7c7b48c99cb3` logs in again with a new identity, and `source_replaced=True, had_previous_lobby=True, previous_queue_active=True`. The prior squad is removed because identity is currently keyed by public IP. This could result from a physical Switch and Citron emulator sharing a NAT; the log does not prove which client restarted.
- At **14:24:47.579**, `7c7b48c99cb3` starts `551fb403d76d` and the backend reports **`decision=joined_existing_queue`, `members=2`, `group_count=1`, `max_count=4`**. This is the first hardware-driven confirmation that the registry can assign two *network sources* into one in-memory lobby. It is NOT proof of a cross-device game lobby or transport.
- The source immediately starts polling an unverified 2-byte scalar Presence RPC `b2ba5509...` at ~0.43s cadence; currently it is acknowledged with bare 0800. This may be an in-game waiting/client-state check but method mapping remains unverified.
- Later source `7c7b48c99cb3` calls `MatchmakeStart` four more times between 14:25:16–14:25:47; the registry still reports `members=2` and `group_count=1`. Previous `no_other_queue` logs were misleading for an already matched client because other queues exclude the client's own. New version reports `already_in_shared_queue` (same bytes, no state/behavior change).
- At **14:25:50.307** it fetches the typed `GetStatusSquad` candidate and at **14:25:50.804** `GetStatusMatchmake`, each with `members=2`. The *other* source never requests these status endpoints after the join in the observed window. This leaves propagation/callback/push as an open question.
- At **14:25:51.409** it begins repeated **44-byte** POSTs to **unknown service** `8aa8a8fb77a6450cb44b11e823a7c959`, method `4be808a1e9a842e581ee6eb47e8cd5eb`, then retries ~2.4s later. Nine requests through 14:26:56; server returns 404. This is a new post-match protocol lead.
- No crash/traceback or failed auth is visible in the log; clients continue Heartbeat.Update with nine versions.

## New exact-size method hypothesis: GetUsersPublicData

The analyzed Switch executable's native hashed GUID record table groups `4be808a1e9a842e581ee6eb47e8cd5eb` directly before repeated service GUID `8aa8a8fb77a6450cb44b11e823a7c959`, consistent with the observed RPC path. The table contains **four method candidates** for this service. The embedded `proto.proto` contains **four IUserService methods**, including `IUserService_GetUsersPublicData { repeated backendPb.UserId users = 1; }`. This is an intriguing correlation, **not a validated service-name mapping**.

From the actual descriptor: `backendPb.UserId { optional bcl.Guid Uid = 1; }` and `bcl.Guid` contains two fixed64 fields. A serialized UserId takes **20 bytes**; repeated field1 wrapper takes **22 bytes per user**; two requests would be **exactly 44 bytes**. Thus the unknown packet's 44-byte length is consistent with looking up two players' public profiles immediately after a match. It might instead be another method or shape until actual field layout is observed. Do NOT fabricate a response from length alone.

## New opt-in-safe instrumentation

`request_shape.py` now recognizes only the exact unknown post-match path and emits a bounded, nested protobuf **field-number / wire-type / byte-length** shape; no string text, scalar values, account UUIDs, tokens, hashes of user IDs or packet bytes are printed. The endpoint still returns HTTP 404. `tests/test_post_match_shape.py` verifies two synthetic user IDs produce a 44-byte request and that the log reveals only the nested schema.

`lobby_registry.py` now reports `already_in_shared_queue` rather than `no_other_queue` for repeated `MatchmakeStart` by a member of a two-source group; this alters logging only, not response bytes or matching. Tests cover group preservation and response stability.

## Next hardware test

Use the existing VPS working `--lobby-mvp --trace-clients` invocation, after `git pull --ff-only`. Citron and physical Switch on the same IP still share a single source key; for clean inference use only one at a time or separate real external IPs. For internal pairing, both source tags must match playlist, and the next log should again show `joined_existing_queue` or `already_in_shared_queue` with two members. Then watch the `Unimplemented RPC request shape: /8aa8...` line; if it shows repeated field1 / nested GUID fields and sizes fitting two UserIds, we can implement a candidate typed profile lookup response in a separately opt-in test. Until that evidence, do not change that 404.

Shell:

```bash
cd /opt/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p 'test_post_match_shape.py' -v
python3 -m unittest discover -s tests -p 'test_lobby_matching_diagnostics.py' -v
umask 077
mkdir -p logs
PYTHONUNBUFFERED=1 python3 mvp_server.py \
  --host 0.0.0.0 --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt --key certs/server.key \
  --trace-clients --lobby-mvp \
  2>&1 | tee "logs/post-match-$(date +%Y%m%d-%H%M%S).log" \
  | grep --line-buffered -E 'Experimental lobby registry:|Unimplemented RPC request shape: /8aa8|Unmapped RPC: /8aa8|rejected|ERROR'
```

This filters heartbeat spam on screen without losing the full file. The next goal is verified profile/public lobby discovery semantics, not simply two members counted in Python. Rollback: omit `--lobby-mvp`, no JSON changes needed.
