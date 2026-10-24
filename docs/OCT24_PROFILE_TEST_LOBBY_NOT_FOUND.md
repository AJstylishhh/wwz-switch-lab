# Oct 24: "Lobby not found" with profile-reply flag — no post-match RPC reached

Authored by OpenAI ChatGPT (GPT-6). Research branch only.
Evidence: user's `profile-test-20261024-200145.log`, 735 lines
(20:01:45–20:07:56, Oct 24, 2026). Do not commit the raw log,
credentials or addresses.

## User-visible result

Tester reports **"lobby not found"**. This run enabled the new
`--experimental-public-user-data` switch.

## Actual two-device timeline

Two distinct source tags (private process-scoped network-source hashes)
and two locally issued authenticated session tags appear:

| Local time | Event |
| --- | --- |
| 20:03:32 | Source A `d37df438b253` signs in; session `4806bdaa5058`. |
| 20:03:36 | A creates its one-person squad. |
| 20:03:49.540 | A queues playlist tag `6733e4f66d9f`: `no_other_queue`. |
| 20:04:45 | Source B `625aea0e9c3c` signs in; session `01c7bb6d18ce`. |
| 20:04:50 | B creates its own one-person squad. |
| **20:05:22.500** | B starts the same playlist: `decision=joined_existing_queue`, **`members=2`, `group_count=1`**. |
| 20:06:40 | B updates GameData within two-member group. |
| 20:06:41 | B sends `MatchmakeStop`; group-global `queued` becomes false. |
| 20:06:44 | B sends `MatchmakeStart` again, with same playlist; log labels `already_in_shared_queue` and group queued true. |
| 20:07:00 | A updates GameData and calls `MatchmakeStop`, clearing the shared queue. |
| 20:07:06 | A starts a **different** playlist `bcbbb2683fd6`, but the group *still has two members* and reports `already_in_shared_queue`. |
| 20:07:13 | A again starts different playlist with same two-person group. |

The second playlist does **not** describe the same search as the earlier
20:05:22 successfully paired queue.

## Critical negative observations

- **0** calls to the post-match `/8aa8...svc/4be8...` candidate RPC.
- **0** `Post-match user lookup correlation` lines.
- **0** `Experimental public user-data reply` lines.
- **0** warnings, unrecognized refresh tokens, ambiguous session/ACL
  resolutions or other server-side authentication failures.
- All observed lobby RPCs use `identity_resolution=issued_token`.
- No client `GetStatusSquad` or `GetStatusMatchmake` requests **after**
  20:05:22. The only such status calls happen before both clients have
  joined the same group.
- Approximately 266 Heartbeat.Update calls are received and answered
  with the same configured nine UserVersions values as before; their
  version list is currently a fixture, not tied to lobby changes.
- RedLynx `getenvironmentinfo` remains unimplemented on port 11701,
  observed three times here. Its response semantics are unknown.

**Conclusion:** the new profile handler was never exercised, so this
result neither verifies nor invalidates the candidate UserBaseData response.
The lab's in-memory `joined_existing_queue` is not evidence of
application-visible player discovery, session allocation or game transport.
The first console is not observed refreshing its status after B joins.

## Separate, confirmed registry modeling issues (no fix yet)

1. `MatchmakeStop` from either member clears the **whole group's**
   `queued` flag. The real backend may track per-player state, distinct
   squad/party membership, and search membership separately.
2. A fresh `MatchmakeStart` on a new playlist while a member is
   already in a two-player group changes the **shared group's playlist**,
   preserving both members and reporting `already_in_shared_queue`.
   This is incorrect for independent matchmaking attempts. Do **not**
   misinterpret it as confirmation that two people chose the new playlist.
3. `PostLogin` returns fixture `UserVersions` lists on heartbeat
   Register/Update, with no per-player delivery tracking or version change
   linked to a lobby update. Whether the Switch relies on changed version
   values to issue `GetStatus*` calls is a **hypothesis**, not established.
   The extracted descriptor defines `UserVersions { repeated int64
   Versions=1; }`, but the enum index semantics still need investigation.

## Next meaningful implementation / controlled A/B

Focus on **delivery of a match to the client**, not on sending more
profile responses. Before changing network behavior, map the user's
heartbeat `VersionDataType` enum / status-notification mechanism in the
NSO binary or observe actual backend behavior. A carefully gated
notification/version-change experiment may cause the console to request
`GetStatusSquad/Matchmake` and transition to the post-match
`GetUsersPublicData` stage. Avoid randomly changing all nine
heartbeat version slots; prior version mismatch caused client disconnects.

Separately fix or model stop/start per-client queue state in a targeted
regression test, particularly when a member changes playlist, before
concluding group_count/member_count means an active match.

For a future test, note the local timestamp when `lobby not found`
appears on each console, and whether it appears immediately on lobby
creation or only after searching. The current server log has no direct
error marker to associate with the exact on-screen text.

No code behavior or flags were changed for this report.
