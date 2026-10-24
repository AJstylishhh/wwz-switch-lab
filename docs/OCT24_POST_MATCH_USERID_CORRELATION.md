# Oct 24: opt-in correlation for the 22-byte post-match UserId RPC

Authored by OpenAI ChatGPT (GPT-6). Research branch only.

## Motivation and evidence

The physical Switch-only `acl-test-20261024-151418.log` reports two
different issued `access_role` ACL credentials and an experimental
`joined_existing_queue` with `members=2` at **15:18:33.485**.
Later, one client repeatedly POSTs **22 bytes** to the still-unmapped
`/8aa8a8fb77a6450cb44b11e823a7c959.svc/4be808a1e9a842e581ee6eb47e8cd5eb`
at 15:20:54, 15:20:56 and 15:20:58.

The nested request shape is consistent with one
`backendPb.UserId { bcl.Guid Uid = 1 }`, wrapped in repeated field 1.
It is not yet dynamically proven that the hashed GUID identifies
`IUserService_GetUsersPublicData`. Do not return fabricated profile data.

## New read-only probe

Use `--trace-post-match-users` when starting `mvp_server.py`. This
parses *only* the exact observed method and *only* a strictly validated
1..16-record repeated UserId/bcl.Guid structure. It compares decoded IDs
in memory to **active locally issued SignInResult user IDs**, interpreting
fixed64 halves in their original .NET little-endian GUID layout.

To identify the **requester**, the probe uses the game's observed HTTP
`acl-token` only if it exactly matches a locally issued AuthorizationToken
or AccessRoleToken. A missing, stale or unrecognized ACL token does not
get source-IP-based authority.

Output is counts and booleans only, e.g. (illustrative, NOT live results):

```text
Post-match user lookup correlation: {'format': 'user_ids', 'requested_records': 1, 'distinct_requested_users': 1, 'issued_user_matches': 1, 'unknown_user_ids': 0, 'requester_verified': True, 'includes_requester': False, 'other_issued_users_requested': 1}
```

No raw protobuf, user UUIDs, auth tokens, token fingerprints or network
addresses are logged by this probe. The existing optional
`--trace-clients` has its own separate source labels. Malformed or
unexpected requests are reported only as `format='unrecognized'`.

**Response behavior is unchanged.** The RPC still returns HTTP 404.
This probe is not an implementation of `GetUsersPublicData`.

## Recommended controlled test

Stop the previous server. Pull the research branch, run tests, then:

```bash
cd /opt/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p test_post_match_user_probe.py -v
python3 -m unittest discover -s tests -p test_lobby_identity.py -v
umask 077
mkdir -p logs
PYTHONUNBUFFERED=1 python3 mvp_server.py \
  --host 0.0.0.0 --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt --key certs/server.key \
  --trace-clients --lobby-mvp --lobby-session-ids \
  --trace-post-match-users \
  2>&1 | tee "logs/post-match-userid-$(date +%Y%m%d-%H%M%S).log" \
    | grep --line-buffered -E 'Listening|Experimental lobby identity:|joined_existing_queue|Post-match user lookup correlation:|Unmapped RPC: /8aa8|Cannot assign lobby RPC|ERROR'
```

Use **two physical Switches**, with both matchmaking on exactly the same
playlist. Capture the full log and note what each console actually shows.

### Interpretation

- `requester_verified=True`, `includes_requester=False`,
  `other_issued_users_requested=1`: the client is requesting the other
  locally issued player's user ID (strong evidence for profile resolution
  immediately after grouping).
- `includes_requester=True`: this request contains the sender's own ID.
- `issued_user_matches=0`: the ID is not among active, locally
  issued IDs; investigate whether it is persistent/cached/third-party.
- `requester_verified=False`: no verified issued ACL token was present,
  so own-versus-peer classification is deliberately not possible.
- `format=unrecognized`: our strict `UserId` shape hypothesis
  did not hold for this request.

Next, depending on those observations, verify the method mapping against
the extracted native GUID table and protobuf descriptors, and only then
experiment with a separate opt-in typed `UserBaseData` response.
Avoid guessing profile fields, making every RPC succeed, or changing
the successful pairing logic without evidence.

All observations are for synthetic/local identities only. Internal grouping
does not establish a player-visible lobby or P2P connectivity.
