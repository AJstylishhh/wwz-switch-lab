# October 25 — Public lobby discovery: first descriptor-typed server path

**Research branch only. Authored by OpenAI ChatGPT.**

## Why the previous Citron/Switch test did not reach the heartbeat or profile stage

The `pulse-test-20261024-222018.log` trace shows a distinct Citron source
(`e0c92108ba95`) and second Switch source (`e9a42f000f96`).
Both completed Enqueue/Dequeue and authentication. Citron had a lobby
group after 22:22:39, and began MatchmakeStart at 22:23:56.
The second client began matchmaking at 22:24:03.

However, the request field-3 playlist labels were **two different
nine-byte strings**. The two labels hashed to `6e7277b7bfcc` and
`e7a70328a905` respectively. These are **process-local HMAC tags,
not real playlist text**. Both clients repeated their own Start requests,
the normal registry correctly returned `playlist_differs`, and no
`joined_existing_queue`, shared-roster pulse, or post-match profile
request followed. We cannot assert that these playlists are semantically
compatible without seeing their plaintext labels or real game-mode data.

## Switch descriptor findings

The provided `proto.proto` schema exposes
`IPresenceService_MatchmakeStart`,
`IPresenceService_GetStatusMatchmake`,
`IPresenceService_GetStatusSquad`, `IPresenceService_SquadJoin`,
`IPresenceService_MatchmakeJoinCode`, and
`IPresenceService_GetPlaylistStat`. It **does not contain an obvious
standalone `ListPublicLobbies` RPC**. This does not establish that
actual public discovery does not exist; it may be represented through
matchmaking or another subsystem.

The schema's response analysis associates `MatchmakeStart` with
`ServiceResult_PresenceStatusResponse` (field **334914069**),
containing `PresenceStatusResponse.Squad=2` and
`PresenceStatusResponse.Matchmake=3`. Our prior lab simply returned
`ServiceResult.Success` (protobuf bytes `08 00`) for Start and
setters, so it never delivered an immediate structured status. The
GUID-to-method inference and client acceptance remain **unverified**.

## What the code now implements

### `--public-lobby-discovery` (OFF by default)

Requires `--lobby-mvp --lobby-session-ids`. Uses only **server-issued
ACL credentials** (not IP-only session affinity) to process lobby
requests. Changes descriptor-shaped outputs:

- `MatchmakeStart` returns a typed `PresenceStatusResponse` with
  **both** current squad and matchmaking data, including user IDs,
  party information and matching playlist.
- `MatchmakeStop` returns a typed status showing the caller's
  now nonqueued squad.
- `SquadSetSettings`, `SquadSetGameData` and
  `SquadSetInvitesState` return typed squad data.
- `GetStatusSquad` and `GetStatusMatchmake` retain their
  existing typed responses.
- Queued lobbies are discoverable only by **matching playlist**;
  private/nonqueued squads are not silently published as public lobbies.
  No fake `msGame` state, external user identity, or gameplay
  transport is created.

Without the flag, all new response-path changes are disabled.

### `--lab-cross-playlist-probe` (OFF by default)

**Experimental diagnostic, NOT normal matchmaking or a claim that
different modes are compatible.** Requires public-lobby-discovery mode
above. In a dedicated **two-client lab** where exactly one other queued
solo group exists and no exact playlist match is available, forcibly
associate the two sessions even when their playlist labels differ.
This tests whether the client progresses through a shared-roster
notification and typed status/profile delivery **despite** the
different queue labels.

- Never silently enables in production/default mode.
- Never forces a pair with multiple competing queued groups or if a
  same-playlist candidate exists.
- Preserves both clients' requested playlist names; repeating the
  same Start on either side does **not** immediately unmatch them.
- A client **changing** playlist deliberately detaches it, and cannot
  immediately rejoin the prior party within that same request.
- Each participant still requires a locally issued ACL credential.
- Does not create a game session or guarantee that mixed playlists
  will be accepted by WWZ.

**Interpretation:** Successful user-visible lobby discovery after
this probe would mean our wire/status notification was blocking
the next stage; it would **not** validate matching arbitrary playlists.
No discovery despite forced pairing would instead direct attention to
client-side status delivery, the response schema, or the actual
session allocation mechanism.

### `--trace-playlist-labels` (OFF by default)

Outputs only short, safe printable alphanumeric/underscore/dot/hyphen
playlist names extracted from Start field 3, capped at 32 bytes.
Unexpected identifiers are replaced by `<noncanonical>` and are
**never** printed in full. This helps identify whether Citron and
Switch selected genuinely different game modes. Playlist names are
not used as credentials.

## Tests

- `tests/test_public_lobby_discovery.py`: descriptor nested fields,
  typed squad and matchmaking on Start, cross-client join, HTTP bearer
  validation, and no-flag rollback.
- `tests/test_cross_playlist_probe.py`: strict default, forced
  two-client pairing, same-playlist precedence, third-party rejection,
  repetitive starts without group flapping, and explicit playlist
  switch detachment.
- Existing heartbeat, ACL, matchmaking registry, profile lookup
  and nonflag tests still run in GitHub Actions.

## One meaningful coordinated test

On VPS: stop old process, pull this research branch, then start:

```bash
cd /opt/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p 'test_public_lobby_discovery.py' -v
python3 -m unittest discover -s tests -p 'test_cross_playlist_probe.py' -v
umask 077
mkdir -p logs
PYTHONUNBUFFERED=1 python3 mvp_server.py \
  --host 0.0.0.0 --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt --key certs/server.key \
  --trace-clients --lobby-mvp --lobby-session-ids \
  --public-lobby-discovery --lab-cross-playlist-probe \
  --trace-playlist-labels \
  --lobby-version-pulse --trace-post-match-users \
  --experimental-public-user-data \
  2>&1 | tee "logs/public-discovery-$(date +%Y%m%d-%H%M%S).log"
```

Restart **both** game clients after the VPS process starts, to avoid
stale authentication. First client creates lobby; second browses/searches
again. Note the screen time/message; send full log.

Evidence wanted from one run:
1. `playlist_label` on both Start requests (same or different?).
2. `decision=joined_existing_queue` or
   `decision=experimental_cross_playlist_pair`.
3. `typed_status_response=squad_and_matchmake`.
4. `Experimental heartbeat roster-version pulse` for the host and
   `client_reports_pulsed` change if present.
5. Any subsequent `GetStatus*` or public-user RPC, as well as the
   **actual** user-visible result.

**Rollback:** remove `--lab-cross-playlist-probe` for strict matching;
remove `--public-lobby-discovery` for old two-byte Start acknowledgments;
remove `--lobby-version-pulse` for fixed heartbeat versions. Everything
is in-memory, so stop/restart resets the test state.

This is protocol research with synthetic identity/session state; a
genuine WWZ game session is **not** yet implemented.
