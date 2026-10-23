# Production-shaped EnvironmentList and UDP:50000 observation (research)

Authored by **OpenAI ChatGPT (GPT-6)**. Only the `research/chatgpt-hydra-server-mvp` branch is modified.

## Triggering evidence

On October 23 2026, the test operator ran the same research revision with three TLS listening ports (11701, 11702, 11704). Two console tests were performed. The second disabled the environment response's outer `retCode`. Both still proceeded through Enqueue/Dequeue/RefreshTokens/Heartbeat/Presence, immediately called Heartbeat.UnRegister and two likely teardown methods, and restarted discovery about five seconds later. No HTTP traffic or TLS handshake failure was logged on 11701. This does **not** rule out traffic redirected elsewhere or blocked before the listener.

An independently developed `main` branch reports that a live Saber EnvironmentList has:
- typed envelope with no outer `retCode`
- `EnvironmentId=prod-Master-https`, region `West Europe`
- four data centers with a total of fourteen game endpoints
- game endpoints UDP protocol enum 4, port 50000
- optional `EnvironmentList.Date` as milliseconds

The underlying real upstream packet is not present in this research branch. The summary is **reported external-lab evidence**, not independently verified by the current assistant.

## Next isolated fixture

`routes.environment-production-shape.example.json` encodes all the above as a separate, **opt-in** config. It uses local addresses `192.168.137.1` for *all fourteen game endpoints*; it does NOT point the game toward the published production endpoint IPs in the other branch. Environment API endpoint remains the Switch-hosts-redirected `wwz-production.wwzapi.com:11704` and Dequeue default endpoint name matches `prod-Master-https`.

The experimental server fills `EnvironmentList.Date` using the local PC startup time whenever `date_ms: "now"` is configured. No other post-login reply handlers or synthetic entitlement values have been changed. Baseline `routes.mvp.example.json` retains its original exact response bytes.

**This is intentionally a composite production-shape experiment**, not a one-field A/B; multiple related fields differ from our previous minimal environment mock. We should not claim any one of them caused an observed change.

## Two-terminal lab

Only one TLS server at a time. Launch `py udp_port_probe.py --port 50000 --timeout 180` in a separate PowerShell window (Windows Firewall may require a local inbound UDP 50000 rule if console packets are blocked). This observer **never replies** to any UDP datagram and logs only packet sizes and ephemeral source-socket numbers; source sockets are not necessarily distinct consoles.

In the main terminal:

```powershell
py -m unittest discover -s tests -p test_production_environment_shape.py -v
py -m unittest discover -s tests -p test_udp_port_probe.py -v
py mvp_server.py --host 0.0.0.0 --ports 11702,11704 --routes routes.environment-production-shape.example.json --cert ..\wwz-switch-lab\certs\server.crt --key ..\wwz-switch-lab\certs\server.key
```

Test one Switch. Send only HTTPS log lines and UDP length-only lines, plus the exact game UI state. **Do not send raw captures, TLS keys, login credentials or original binary files.** If UDP packets appear, that's evidence the Switch tries a game transport endpoint, *not* evidence of a working P2P protocol or matchmaking service.

If the menu still fails, the next best path is a field-by-field comparison of *actual live* login/heartbeat/presence response envelopes (not just EnvironmentList), taking care not to expose any real credential material. The other developer's current `main` implementation should not be automatically merged into our research branch because it also hard-codes actual production endpoint addresses and has different token/teardown semantics.
