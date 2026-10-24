# Oct 24: WWZ `acl-token` header and same-IP session collision

Author: OpenAI ChatGPT (GPT-6). Research branch only.

## Full trace reviewed

Source: uploaded `identity-test-20261024-145627.log`, 1261 lines (14:56:28–15:02:41, Oct 24, 2026). User enabled `--trace-clients --lobby-mvp --trace-header-names`; did **not** enable `--lobby-session-ids`.

There are two process-specific **public-IP source** HMAC labels: `8360bedd2f8c` and `754cef197f4e`. These are network-source labels, not reliable machine or authenticated-player IDs.

**Confirmed new finding:** HTTP header **`acl-token`** is present on both clients' Presence status and MatchmakeStart calls, and on one earlier Dequeue call. First source: Dequeue at 14:58:35 includes `acl-token`; Presence status at 14:58:37 and MatchmakeStart at 14:59:18 include it too. Second source: Dequeue at 14:59:44 does **not** include it, but Presence status at 14:59:48 and MatchmakeStart at 15:00:32 do.

This means the prior header allowlist (`Authorization`, `AuthorizationToken`, etc.) was incomplete. Crucially, the **first client's Dequeue `acl-token` arrives before our experimental SignInResult**, so it cannot be presumed to be a token freshly issued by this server. It might be a previously cached ACL credential, a third-party token, or another protocol mechanism. Header **presence** and a keyed **fingerprint** establish correlation only; matching against an *issued and active* token establishes our lab's session authentication.

Other facts:
- First network source attempts to refresh tokens twice at 14:58:53 / 14:58:55; both were rejected as `Unrecognized refresh tokens`. The same source performs a **fresh Dequeue at 14:59:01**, and the IP-keyed registry logs `source_replaced=True`, clearing its earlier one-member lobby. This is compatible with emulator and physical console behind the same NAT, but the log cannot by itself identify which device sent which request.
- At 15:00:32 the second network source starts a different nine-byte playlist, so the registry reports `playlist_differs`. At **15:01:39.811**, matchmaking returns `joined_existing_queue`, **`members=2`, `group_count=1`**, playlist tag `559082970739`. This is an in-memory pairing, not proof of in-game lobby discovery or gameplay.
- No `8aa8a8fb…/4be808a1…` post-match public-data candidate appeared in this capture. The earlier 44-byte RPC remains an unverified lead.
- No server crash shown. RedLynx `getenvironmentinfo` remains unimplemented.

## Code changes

- `lobby_identity.CREDENTIAL_HEADERS` now includes `Acl-Token`; **`--lobby-session-ids` still authorizes it only if it exactly matches our own active synthetic SignInResult authorization or access-role token**, checked in constant time. Arbitrary client-provided ACL values cannot claim another user's identity.
- Header retrieval is explicitly case-insensitive, including synthetic test dicts.
- `--trace-clients` now includes a **process-keyed ephemeral credential fingerprint** for the `acl-token` header when present. It is safe to compare within one run but changes on restart. No raw value or IP is printed.
- New **`--trace-acl-match`** option checks the actual `acl-token` in memory against synthetic active issued AuthorizationToken, AccessRoleToken, DiagnosticToken, or ProviderToken, and reports only `issued_token_type` classification and process-scoped `acl_tag` for each distinct (source, method, token fingerprint). It does not alter request responses or lobby identity behavior. An unrecognized token is explicitly logged as `unrecognized`; no body, header value, UUID or credential text is printed.
- All changes are opt-in diagnostic except recognizing the new header in the already separate `--lobby-session-ids` mode. Existing `--lobby-mvp` without `--lobby-session-ids` still keys by network source; this *has not solved* same-NAT collisions in live tests.

## Recommended next controlled experiment

Stop the running server and run:

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
  --trace-clients --lobby-mvp --trace-header-names --trace-acl-match \
  2>&1 | tee "logs/acl-correlation-$(date +%Y%m%d-%H%M%S).log" \
  | grep --line-buffered -E 'Listening|ACL token correlation:|Potential auth header names:|lobby_mvp_identity_attach|lobby_mvp_start|Unrecognized refresh|ERROR'
```

For the next run, try the sequence Citron sign-in, then hardware Switch behind the same router signing in, while still recording one external friend independently. Compare **`acl_tag`** and **`credential_tag`** for requests from the same source and the classified `issued_token_type` after login.

- If MatchmakeStart carries `issued_token_type: authorization` or `access_role`, verified login-specific routing using `--lobby-session-ids` has a credible basis for that client.
- If MatchmakeStart carries only `unrecognized`, this alone is **not** authenticated session identity. We must determine ACL token issuance and validity or find a different verified identifier before safely routing same-IP traffic.
- If one of the clients sends no ACL at all, our current source-fallback cannot distinguish multiple live sessions behind that address. Do not blindly use TCP source ports (HTTP/1.1 reuses/multiplies connections), TLS version, IP or arbitrary UUID as player identity.
- If both client identities are correctly distinguished, player-visible lobby discovery still requires valid typed post-match/profile/status notifications; `members=2` in Python alone is insufficient.

Never enable raw `--capture-dir` on a public server unless you explicitly accept storing private game tokens and can secure/redact those files. Never push local routes, logs or certs into the public repository.
