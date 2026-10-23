# October 23: Heartbeat UserVersions 4-element isolated test

Authored by **OpenAI ChatGPT (GPT-6)** on the research branch only.

## Outcome of preceding test

The collaborator's test on October 23 at 20:46 local ran `routes.presence-300.example.json`. It reached `PresenceConnect` and logged `available_seconds=300`, but `Heartbeat.UnRegister` followed **61 ms later**. The game restarted discovery around five seconds later. Therefore a 300-second presence duration alone is insufficient.

The corresponding unit-test failure was **not a product failure**. Comparing the two independently rendered `date_ms="now"` environment responses yielded distinct milliseconds. `test_presence_duration.py` now freezes the date in both renders before comparison.

## Captured diagnostic lead

The user-supplied collaborator ZIP contains the client diagnostic string:
`autogen VersionDataType_Last does not corresponds with backend values`.

The descriptor-derived UserVersions submessage is:
`UserVersions { repeated int64 Versions = 1; }`

Our research server had sent that field as a present but **empty** submessage in both heartbeat Register and Update replies. The collaborator's later local code explicitly varied the list length and repeated the Switch build number `8802288`.

The mismatch evidence suggests the list *length* matters; it does **not establish** that the correct length is four or any other count. The five-minute run's settings at capture time cannot be uniquely recovered from the ZIP.

## Controlled test

`routes.heartbeat-versions4.example.json` differs from
`routes.environment-production-shape.example.json` **only** by setting
`heartbeat_version_values: [8802288,8802288,8802288,8802288]` on
`heartbeat_register` and `heartbeat_update`.

No entitlement, token rotation, presence duration, environment, data center,
UDP behavior or unknown RPC handling is changed.

Both heartbeat replies emit the same four int64 values under
`UserVersions.Versions`. The default server behavior remains an empty list.
The route reader rejects different version lists between Register and Update.

### Windows Git checkout

```powershell
cd "$HOME\OneDrive\Desktop\wwz-switch-lab-research"
git pull --ff-only
py -m unittest discover -s tests -p test_presence_duration.py -v
py -m unittest discover -s tests -p test_heartbeat_versions.py -v
py mvp_server.py --host 0.0.0.0 --ports 11701,11702,11704 --routes routes.heartbeat-versions4.example.json --cert ..\wwz-switch-lab\certs\server.crt --key ..\wwz-switch-lab\certs\server.key
```

### ZIP extraction of latest research branch

```powershell
cd "$HOME\OneDrive\Desktop\wwz-switch-lab"
py -m unittest discover -s tests -p test_presence_duration.py -v
py -m unittest discover -s tests -p test_heartbeat_versions.py -v
py mvp_server.py --host 0.0.0.0 --ports 11701,11702,11704 --routes routes.heartbeat-versions4.example.json --cert .\certs\server.crt --key .\certs\server.key
```

Stop any other HTTPS/UDP listeners on the selected ports first. No separate UDP process is needed for this heartbeat-specific test. Observe how soon `Heartbeat.UnRegister` occurs, whether repeated Update RPCs continue, any new paths, and the game's actual menu result. Never commit the collaborator's original captures or tokens.

Passing synthetic unit tests verifies *encoding*, not that four is the correct client enum count. If four fails, analyze actual client enum count rather than blindly sweeping all guesses.


## October 23 remote Linux test result — count four still fails

The current remote test on the user's Linux host used
`routes.remote.local.json` derived from the four-version fixture.
After verified TLS, Enqueue and Dequeue:

- 20:25:40.599 — Heartbeat.Register: `version_count=4`.
- 20:25:41.211 — Heartbeat.Update: `version_count=4`.
- 20:25:41.463 — initial ADF WriteADFPack: both compressed parts successfully decoded, no recognized marker.
- 20:25:41.974 — empty-body Access service method, likely sign-out.
- 20:25:42.059 — second decoded ADF WriteADFPack includes the literal
  `autogen VersionDataType_Last does not corresponds with backend values`.
- 20:25:42.177 — Heartbeat.UnRegister.
- 20:25:49.036 — repeated EnvironmentDiscovery.

This is evidence that **four copies of build `8802288` in both heartbeat responses do not fix the disconnect**. The client diagnostic marker remains present in the second upload; the decoder matches *strings* rather than decoded ADF event types, so it does not prove which client check fired.

Independent offline review of the already-provided collaborator ZIP: the literal string appeared in **25 of 62** older diagnostic packs, concentrated in second/terminal packs of short sessions, while the approximately five-minute sequence had no such match in its accompanying packs. That pattern favors a runtime failure signal rather than an immutable upload dictionary, but is not formal event-level decoding.

The local ZIP has a persisted `state/version_sweep.json` with `step=11` and a later-modified source version that iterates counts `[4,5,3,6,2,7,8,9,10,11,12,13,14,15,16,17,18,19,20,1]`. **This snapshot cannot prove the count used during the five-minute capture**; do not label a count as correct based on that file. The Switch executable includes the diagnostic literal, but its `VersionDataType_Last` constant has not yet been recovered.

Next: determine enum cardinality from the game binary or capture actual ADF event records, rather than performing blind version-count sweeps. Keep the controlled four-entry fixture as a documented failed baseline. No raw captured credentials are committed.
