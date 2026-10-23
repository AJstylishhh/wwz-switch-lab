# Lobby UI success vs. actual discovery (2026-10-23)

Authored by OpenAI ChatGPT (GPT-6), not repository owner. Research branch only.

## Source

User-supplied lobby-20261023-215308.log, 1063 lines, 22:04:54–22:13:03 on October 23, 2026.
The users confirm they can enter/create lobbies on screen, but cannot discover each other's lobbies.

## Confirmed log facts

- 526 POST requests on 24 unique paths; 409 Heartbeat.Update requests.
- Three successful Enqueue / Dequeue sign-ins and three Heartbeat.Register requests. Three login attempts do not necessarily mean three different physical clients.
- Nine requests to Presence method 67cdaf75ca604bd993ad9f1db0c3f812 (seven 167-byte, two 144-byte). Its field-number/type/repetition pattern closely matches IPresenceService_MatchmakeStart in the extracted protobuf descriptor.
- Sixteen property-like b2a1ab68eb464d7796c4e9f49247d3c8 calls and eleven game-data-like 44a718e4c7514684b5259e0879e98c63 calls, but native hashed-GUID method mappings remain unproven.
- Seven RedLynx GetEnvironmentInfo calls on TCP 11701 are still unimplemented.
- RefreshTokens failed three times at 22:10:00.238, 22:10:01.743 and 22:10:03.890. Heartbeat.Unregister followed at 22:10:04.442.

## Root cause of refresh failure and fix

QueueState issued a five-minute ticket (ttl=300). Previously the post-login refresh path called queue.recognizes(ticket), erroneously invalidating an already authenticated client after five minutes.
AuthSessions now separates queue-ticket validity at initial Dequeue from bounded authenticated sessions (3600-second sliding idle expiry, max 256 by default). Refresh succeeds only for tokens all belonging to the same still-active local session. Unknown and expired credentials are rejected. This is still an experimental backend without real Nintendo authorization.
Regression tests: tests/test_session_lifetime.py and tests/test_post_login.py.

## Why the second Switch cannot find the lobby

The prior enable_lobby_rpc_probe.py only returns bare ServiceResult.Success (hex 0800) to seven hashed RPC paths. No lobby registry, shared player roster, join code, owner/participant membership, matchmaking queue or session identifier is actually stored.
The current typed PresenceStatusResponse probe also returns MatchmakeStatus.State=msMenu with no active squad or matchmaking membership. Thus the UI accepting a lobby creation is not proof that a discoverable lobby exists.
Protobuf contains IPresenceService_MatchmakeStart, SquadJoin, MatchmakeJoinCode, GetStatusSquad, GetStatusMatchmake; mapping all of their GUIDs and validating the request/response contracts are still necessary before implementing matching.

## Next two-console experiment: safe correlation, same routes

Opt-in --trace-clients adds process-keyed HMAC source_tag labels to individual POST log lines. If a known authentication header is present, a credential_tag is also logged. Raw IP and credential contents are never printed; values cannot be linked across Python restarts. Behind the same NAT source_tag may represent two users. A credential_tag is a trace label, not proof of a verified game account.

VPS instructions (stop server before restarting):

```bash
cd /opt/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p test_session_lifetime.py -v
python3 -m unittest discover -s tests -p test_client_trace.py -v
umask 077
mkdir -p logs
PYTHONUNBUFFERED=1 python3 mvp_server.py \
  --host 0.0.0.0 --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt --key certs/server.key \
  --trace-clients 2>&1 | tee "logs/client-pairs-$(date +%Y%m%d-%H%M%S).log"
```

First client logs in, creates and keeps a private lobby. Second client logs in and attempts the actual in-game discover/join action. Record which UI option they use and their result. Upload the full log. Do not use --capture-dir for this ordinary test because it stores raw, potentially credential-bearing request bodies.

Even with trace labels, the test will not suddenly enable lobby discovery; it determines which operations the two devices actually invoke and whether their identities can be associated safely. Stateful squad and matchmaking behavior must be implemented before a real cross-client lobby can work.
