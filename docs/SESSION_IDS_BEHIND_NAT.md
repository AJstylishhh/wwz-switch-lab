# Distinguishing Citron and physical Switch behind one public IP

Authored by OpenAI ChatGPT (GPT-6), not repository owner. All changes on `research/chatgpt-hydra-server-mvp` only.

## Why IP-based correlation was incorrect

Each successful experimental `IAuthorizationService_Dequeue` generates a distinct `SignInResult.User.Uid` (a synthetic bcl.Guid) and issued `AuthorizationToken` / `AccessRoleToken`. Previously `mvp_server.py --lobby-mvp` used only a process-keyed hash of peer IP as the key to `LobbyRegistry`. Two sessions sharing a NAT therefore overwrite one another, which was observed in recent logs. The existing source_tag describes a network source and cannot distinguish devices.

However, this does not establish a **stable hardware device ID**: the experimental user UUID is new on each login. `IPresenceService_MatchmakeStart` accepts DC pings, matchmaking options, playlist and variants, **not a user ID**. The backend cannot reliably map a later request to its Dequeue by mere IP address if two independent sessions use the same network. A valid token on a later request, a proven user identifier, or a verified per-connection binding is needed.

## Code (opt-in, safe failure)

An additional opt-in flag `--lobby-session-ids` is available **only together with** `--lobby-mvp`:

- `lobby_identity.ClientSessionIndex` associates distinct sessions with process-keyed identity identifiers generated from **our own SignInResult.User.Uid**, rather than the peer IP. It stores the in-memory synthetic issued identity and a bounded expiry (1 hour). Only session tags are logged, not IDs, IPs or tokens.
- On later Presence lobby calls, it validates the value of known `Authorization`, `AuthorizationToken`, `X-Auth-Token`, `X-Access-Token` or `X-Authorization` headers against the **issued** AuthorizationToken or AccessRoleToken. It supports `Authorization: Bearer <token>`. Matching token wins even if public IP has changed.
- If **exactly one** session currently belongs to that public IP, the lab temporarily allows the same single-client source fallback as before.
- If two active logins share a public IP **and no validated token appears on a later request**, it returns HTTP **409 Ambiguous lab session** instead of guessing or deleting one player's lobby. This is intentional **not a working same-NAT fix until client credentials are observed**.
- Normal `--lobby-mvp` mode without the flag is not altered. No raw capture files or identity tokens were committed.

## Current evidence limitation

The most recent `--trace-clients` logs show `source_tag` but did **not** show `credential_tag` from the existing allowlist. Thus there is no confirmed token-bearing header in the currently captured multiplayer requests. This could mean the game uses another header name, embeds identity outside the decoded RPC body, or does not send credentials in a way our server recognizes.

Do not conclude that the real console sends its synthetic issued token just because we included it in SignInResult. Actual request headers and game SDK behavior must be verified. The new flag is for controlled tests and deliberately can block a same-IP lobby call instead of silently confusing identities.

## How to run the guarded A/B test

Stop Python server, then:

```bash
cd /opt/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p test_lobby_identity.py -v
umask 077; mkdir -p logs
PYTHONUNBUFFERED=1 python3 mvp_server.py \
  --host 0.0.0.0 --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt --key certs/server.key \
  --trace-clients --lobby-mvp --lobby-session-ids \
  2>&1 | tee "logs/session-ids-$(date +%Y%m%d-%H%M%S).log" \
  | grep --line-buffered -E 'Experimental lobby identity:|Experimental lobby registry:|Cannot assign lobby RPC|ERROR'
```

Test on **one physical Switch first**, then two unrelated external IPs. For a Citron + Switch same-NAT test, if the clients don't send an issued token the expected behavior is `409`; stop, revert by omitting `--lobby-session-ids`, and research their request headers. This option is not required for the already working two-*different-IP* server match experiment.

## Safest next step: inspect possible token header names without changing routing

A separate **non-invasive** `--trace-header-names` flag is now available. It logs only bounded, sanitized authorization-like **header names** on the first request from each network source to Dequeue, MatchmakeStart, GetStatusSquad and GetStatusMatchmake. It never logs header values or the user IDs. It can be enabled on the existing working `--lobby-mvp` server **without** `--lobby-session-ids`:

```bash
cd /opt/wwz-switch-lab
git pull --ff-only
PYTHONUNBUFFERED=1 python3 mvp_server.py \
  --host 0.0.0.0 --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt --key certs/server.key \
  --lobby-mvp --trace-clients --trace-header-names \
  2>&1 | tee "logs/identity-header-names-$(date +%Y%m%d-%H%M%S).log" \
  | grep --line-buffered -E 'Potential auth header names:|Experimental lobby registry:|Unmapped RPC:|ERROR'
```

Inspect `Potential auth header names:` on the Dequeue and MatchmakeStart paths. If there is a plausible stable auth header, confirm its value actually equals one of the *issued* local SignIn tokens in code before enabling per-session routing; don't assume a similarly named third-party header is legitimate. If there are no candidate headers, inspect the native request-construction code or use a verified connection/session binding. This new flag does **not** claim to fix same-NAT identity by itself.

Do not treat HTTP source port, static public IP, arbitrary client-provided UUID or TLS SNI hostname as a verified player identity.

Tests validate same-NAT distinct sessions, token-based routing to separate lobby records, invalid credentials, unique-IP fallback, expiry, repeated Dequeue and a real loopback HTTP endpoint. No hardware verification of this flag is claimed.
