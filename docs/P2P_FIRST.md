# P2P-first plan and laboratory transport

**Author: OpenAI ChatGPT (GPT-6).**
The request on 2026-10-22 explicitly prioritizes P2P hosting with server-backed
player/session discovery, not a dedicated game-simulation server.

## Actual Switch progress

The collaborator launched \`mvp_server.py\` at 11:19 local on 2026-10-22.
After the synthetic environment response:

- 11:22:22 port 11702: known **environment discovery** RPC (806 bytes).
- 11:22:24 port 11704: **new, unmapped** RPC (1448 bytes), HTTP 404.
- The same second RPC reappeared after environment discovery at 11:23:18
  and 11:24:00. The previous server never observed this second stage.

The new service GUID \`0ae806e0260340fe86eb38ff8708252f\`
appears in **eight entries** in the static GUID record structure;
\`IAuthorizationService\` has **eight named operations** in the NSO's
embedded protobuf schemas. This supports an **authorization-service
hypothesis**, not a proven method mapping.

New method GUID: \`3ad39ec0971940b98e522d40229704b9\`.
The 1448-byte body is saved privately by \`--capture-dir captures\`;
use \`auth_probe.py\` to classify it without printing credentials.

## Standalone P2P directory and UDP forwarding

\`p2p_lab.py\` is **a tested generic transport prototype, not WWZ integration**.
It deliberately uses a distinct UDP port 50001 (the observed remote 50000
port was consistent with UUID reachability/latency probes, not gameplay).

- A host creates a room, receiving a private host token.
- A guest joins by room code and receives a different private token.
- Both sample clients send \`WWZ-LAB-REGISTER <token>\` over UDP 50001.
- The relay registers their observed IP:port endpoints and forwards **opaque
  datagrams unmodified** in both directions.
- UDP packets from unregistered endpoints are ignored.
- HTTP control API remains localhost-only by default and is **cleartext**.
  Do not expose it directly on a public VPS; add authentication/TLS,
  session expiry, rate limits and logging controls before considering that.

Run the lab independently of the Hydra backend:

\`\`\`powershell
py p2p_lab.py
\`\`\`

Create a room (PowerShell):

\`\`\`powershell
$hostRoom = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:11705/lab/create -ContentType application/json -Body '{}'
$guest = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:11705/lab/join -ContentType application/json -Body (@{room=$hostRoom.room} | ConvertTo-Json)
\`\`\`

The resulting tokens are intentionally secret and must not be posted publicly.
Use a cooperating Python UDP client or the included unit tests to register
those tokens and prove forwarding. Running the lab does NOT make a Nintendo
Switch contact this relay; WWZ itself does not know the invented registration
format.

Run local integration tests:

\`\`\`bash
python -m unittest discover -s tests -v
\`\`\`

## What needs to happen for actual P2P co-op

1. Identify the 1448-byte authorization RPC and implement its real response.
2. Establish player identity, presence and session discovery with two consoles.
3. Recover the **actual** WWZ lobby creation/join operations and their
   required protobuf response values from client code and test traffic.
4. Identify the negotiated gameplay host endpoint, handshake and NAT behavior.
5. Determine whether the game can send UDP directly to the peer, or whether
   the relay IP:port can be substituted in returned session data.
6. Only then connect the experimental relay/directory to the Hydra endpoint.

A Switch may already host P2P game simulation; we do not need to reimplement
enemies or missions if that hosting path is used. This is a hypothesis until
a two-console join and gameplay packet capture confirms it.
