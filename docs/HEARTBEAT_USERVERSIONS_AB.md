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
