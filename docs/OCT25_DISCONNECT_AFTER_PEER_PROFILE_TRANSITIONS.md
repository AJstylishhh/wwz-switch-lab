# Oct 24 22:43–22:51 — two-client disconnects after real profile delivery

Authored by OpenAI ChatGPT (GPT-6). Only the research branch is modified.
The user-supplied `public-discovery-20261024-224332.log` was analyzed
locally and is NOT committed (raw logs may contain private identifiers).

## What is confirmed

The user reports creating a lobby twice, and that the second player
received "connection lost" while attempting Find Match.

The two authenticated client source tags were:
- `d9a844a5efff` (TLS 1.2; physical Switch probable, based on
  earlier source traffic) and session `ed97970d7a84`.
- `6346077eeebd` (TLS 1.3; Citron probable) and session
  `581bcf668a94`.

A third login from the first source occurred at 22:47:41, obtaining
session `2587f2a6aa62`; the old session was still indexed. This is a
**fresh sign-in**, not evidence that the server explicitly rejected
the client's old credentials. This trace contains no
`Cannot assign lobby RPC` or refresh-token rejection.

**First pairing**
- 22:45:11: `playlist0` enters queue alone.
- **22:45:21.360**: `playlist1` is forcibly paired under experimental
  cross-playlist flag. `members=2, group_count=1`.
- **22:45:21.938**: one client issues unknown Presence RPC
  `a5849554ff43457e88339d6a58fd6116`, with zero-byte body.
  The server returns HTTP 404.
- 22:45:22.051 and .215: both clients issue dynamic
  `GetStatusSquad` with two members and `GetStatusMatchmake` in queue.
- **22:45:22.420**: the first client sends `MatchmakeStop`, our
  registry detaches it and immediately removes the paired membership.
- 22:45:22.487 onward: **nine** candidate public-user lookups
  (22 bytes) on both clients now get **404**, because the two
  users have already been separated by the Stop.
- 22:45:24.310: the remaining member does report the pulsed version
  after the roster changes again. The pulse mechanism is operational.

**Second pairing**
- 22:47:41: new sign-in from original network source.
- 22:47:57: `playlist1` is queued alone.
- **22:48:36.058**: `playlist0` forcibly joins the other queue,
  `members=2`.
- **22:48:37.415 and .995**: **both** authenticated game clients
  report the exact *pulsed* nine-value vector. This is a confirmed
  client acknowledgment, not just a server-side queue merge.
- **22:48:38.240**: one client successfully requests a previously
  issued peer UserId; server returns a typed
  `ServiceResult_List_UserBaseData` with one synthetic record, HTTP 200.
- **22:48:49.064**: another zero-byte unknown Presence RPC
  `f05e89628988405c89a51dc520957cae` receives HTTP 404.
- **22:48:49.586**: `MatchmakeStop` follows, again removing the
  peer from the current shared lobby.
- 22:48:50.890 and 22:48:57.805: more unknown zero-byte
  `a5849554ff43457e88339d6a58fd6116` calls receive HTTP 404.

The logs prove **internal pairing, accepted heartbeat updates and at
least one successful typed peer-profile response**. They do **not**
prove that official public lobby discovery or gameplay-session
allocation are implemented, nor that any particular HTTP 404 causes
the exact on-screen disconnect.

## Newly implemented optional experiments

### 1. `--profile-grace-seconds 12`

Requires `--experimental-public-user-data --lobby-mvp --lobby-session-ids`.
When a paired client calls MatchmakeStop, an in-memory lease preserves
only that pair's **server-issued synthetic player IDs** for at most
12 seconds (configurable 1–30). In-flight public profile RPCs can
complete even after the registry splits the pair. The lease:
- Is not renewed by profile reads.
- Expires monotonically.
- Cannot be used for unrelated synthetic users.
- Is cleared on identity replacement.
- Requires a valid locally issued ACL token per lookup.
- Is OFF by default (0 seconds), preserving earlier behavior.

This addresses the nine post-Stop 404s without falsely keeping users
in the same active matchmaking lobby.

### 2. `--experimental-presence-empty-acks`

Requires `--lobby-mvp --lobby-session-ids`. For the **two exact**
unimplemented Presence RPCs above, if and only if their bodies are
empty and the request bears a valid **locally issued** ACL token,
reply with `ServiceResult.Success` (protobuf 08 00; HTTP 200).
Malformed bodies and unverified sessions are still rejected.
**The methods' meanings have not been confirmed.** This is only
an A/B test of whether HTTP 404 blocks a later protocol step; it
does NOT enact squad-leave, session teardown, a match-ready action,
or anything else that the real methods might require. Do not
interpret a disappearance of 404 as proof of correct semantics.
Flag OFF restores the old 404.

## Independent evidence and limitations

The native Switch `main` NSO contains the ASCII RPC string
`a5849554ff43457e88339d6a58fd6116` next to
`b2ba5509c32e43f09b39cb0a828059df` (an observed repeating
two-byte scalar request) and adjacent `IsOwner` string.
That proximity **does not definitively identify the method**.
The `f05e8962...` string was not found as an ASCII GUID in the
provided NSO zip; it might be registered dynamically or in another
binary. Both have empty request bodies, making several protobuf
Presence methods plausible. A future mapped implementation
requires stronger native cross-reference or official plaintext
evidence.

Both real clients selected different `playlist0` and
`playlist1` categories. The forced cross-playlist feature remains
an artificial **debug-only** grouping; it is not proof that these
game modes are compatible in WWZ. This is still not a joinable
gameplay server, and users should not be asked to coordinate
repeated testing without a meaningful server-side change.

## One next lab run (only when collaborators are available)

Stop the existing VPS process; checkout/pull the same research branch.
Restart both games after the new VPS process has started, to avoid
stale in-memory credentials. Reuse the previously configured private
route/cert files and append exactly these two flags:

```
--profile-grace-seconds 12 --experimental-presence-empty-acks
```

Current base flags:
```bash
cd /opt/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p 'test_post_match_transition.py' -v
umask 077; mkdir -p logs
PYTHONUNBUFFERED=1 python3 mvp_server.py \
  --host 0.0.0.0 --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt --key certs/server.key \
  --trace-clients --lobby-mvp --lobby-session-ids \
  --public-lobby-discovery --lab-cross-playlist-probe \
  --trace-playlist-labels --lobby-version-pulse \
  --trace-post-match-users --experimental-public-user-data \
  --profile-grace-seconds 12 --experimental-presence-empty-acks \
  2>&1 | tee "logs/transition-test-$(date +%Y%m%d-%H%M%S).log"
```

Check: first/second pair; pulsed version ack; typed peer profile
with `membership_scope: current_pair` or `recent_pair`;
`Experimental unknown Presence empty ACK` for either method; new
RPC calls after each; how/when the client decides to Stop; and
actual user-visible error. A server restart without these two
flags restores old behavior without changing route JSON or
persisted state.

Regression tests in `tests/test_post_match_transition.py`
cover user identity separation, ACL isolation, 12-second lease
expiry without renewal, profile lookup HTTP behavior, the two
unknown method ACKs, malformed request rejection, and rollback.
