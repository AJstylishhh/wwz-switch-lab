# October 23: WWZ UDP:50000 endpoint probes before Enqueue

Authored by OpenAI ChatGPT (GPT-6). Changes to research branch only.

## Observed in production-shape fixture

With `routes.environment-production-shape.example.json`:

- 4 advertised data centers / 14 total local UDP port 50000 endpoints
- First observed UDP datagram at **16:56:02.129**, while the Enqueue HTTP request reached the server at **16:56:02.241** (112 milliseconds later).
- The supplied excerpt shows at least **70 datagrams**, all **38 bytes**, from one source socket, between **16:56:02.129 and 16:56:02.329** (~200 ms).
- 70 = 14 × 5, but all advertised game endpoints shared one IP/port, and the listener did not record payload identity. **Do not assert that five probes were sent per endpoint** from this count alone.
- Dequeue, refresh, heartbeat, presence and diagnostics still proceeded. At **16:56:02.957**, an empty possible PresenceDisconnect request was observed, followed by Heartbeat.UnRegister at 16:56:02.958 and a possible SignOut at 16:56:02.972; the order differs slightly between runs because requests are concurrent.
- Environment discovery started again at **16:56:08.210**.
- The observer **never responded** to these datagrams. HTTP status 200 and UDP reception alone do not prove the client accepted an online session.
- All 3 production-shape fixture tests and both passive UDP observer tests passed on the collaborator's Windows machine.

## Context from other developer's main branch

The `main` branch contains `lab_udp_echo.py`, which reflects any received packet. The repository does not document a confirmed successful WWZ menu session or actual protocol recognition from using it. Do not infer a fixed WWZ echo handshake or a working matchmaking protocol.

## Next controlled test

`udp_probe_compare.py` provides two locally contained modes:

- **Passive (default)**: print aggregate unique payload count, duplicate groups, lengths and source-socket count.
- **Echo (opt-in)**: the same statistics, plus reflect only exactly 38-byte UDP datagrams to a client address in `192.168.137.0/24` or `127.0.0.0/8`. This is an artificial response, not a protocol-correct packet.

No source addresses, ports, hashes or raw payload bytes are emitted or written. The script has no packet-capture output. Use the same TLS server configuration across runs, and ensure the previous UDP observer is stopped before starting either probe. Only one process may bind UDP 50000.

Commands from the research Git checkout (another console window, while WWZ TLS server is active):

```powershell
py -m unittest discover -s tests -p test_udp_probe_compare.py -v
py udp_probe_compare.py --timeout 90
# Do one Switch session, compare result with echo mode; stop first listener.
py udp_probe_compare.py --echo-38 --timeout 90
# Do one more Switch session with same TLS configuration.
```

In a second terminal, use:

```powershell
py mvp_server.py --host 0.0.0.0 --ports 11702,11704 --routes routes.environment-production-shape.example.json --cert ..\wwz-switch-lab\certs\server.crt --key ..\wwz-switch-lab\certs\server.key
```

Compare whether `Heartbeat.UnRegister` still occurs, whether the menu state changes, and whether new GUID RPCs or repeated UDP traffic appear. An echo might be ignored by the Switch and cannot be assumed to simulate the real UDP service. Continue to avoid publishing raw authentication captures or TLS private keys.
