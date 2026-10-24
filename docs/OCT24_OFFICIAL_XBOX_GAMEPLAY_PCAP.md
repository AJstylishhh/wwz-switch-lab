# Oct 24: official WWZ capture — gameplay transport versus matchmaking

Research author: OpenAI ChatGPT (GPT-6). Research branch only.
Evidence: collaborator-supplied local `WWZ Lobby and story co-op public connection dump.pcapng` (not committed).

## Platform caveat

This is **not proven to be Switch traffic**. In fact, its local game device
uses a MAC prefix registered to **Microsoft** and requests many
`*.xboxlive.com` services (achievements, profile, XSTS, presence,
session directory). The capture host is a Windows PC acting as
`192.168.137.1` (ICS); the other device is on `192.168.137.123`.
It is thus strongly consistent with an **Xbox console behind Windows ICS**.

The local Windows computer's own background traffic is also in the trace.
The measurements below explicitly filter on the game device, not every
packet in the file.

Xbox / PrismRay service RPCs must **not** be presumed wire-compatible with
the old Switch build's `wwz.wwzapi.com` Hydra RPCs.

## Capture characteristics

- 18,355 packets, 2026-10-24 16:56:29.557–17:07:16.433 UTC
  (approximately 646.9 seconds).
- Collaborator's sequence: initial menu traffic; multiplayer search joined
  a three-player match but failed to connect; returned to menu; searched
  for public story co-op; joined an existing lobby.
- These phases have no user-supplied exact timestamps; the alignment below
  is a **traffic-based inference**, not a proven label for every second.
- Multiple `*.prismray.io` TCP/TLS connections on 11701 through 11706,
  including `global-eds.prismray.io:11702`,
  `ppsvc.prismray.io:11701/11702/11703/11704/11705`,
  `pphpres.prismray.io:11701`, `prodphdr.prismray.io:11706`.
  The TLS application payload is encrypted: no user profile, lobby body,
  or endpoint allocation was decoded from those connections.

## UDP/50000 datacenter probe — **confirmed byte-for-byte echo**

- Two UDP probe bursts start about **7.5s** and **309s** into the capture.
- **287** outgoing 36-byte ASCII UUID-shaped messages to **27** distinct
  Internet endpoints on UDP **50000**.
- **287** inbound 36-byte messages from the same remote sockets.
- Every single inbound payload matches an outbound payload
  **byte for byte** from its own remote endpoint: **287/287 echoes**.
- Matching packet turnaround median approximately **181 ms**, spanning
  about 24–352 ms for the responses. RTTs include the capture and network
  paths and are not a general region ranking.
- These are **latency/reachability probes, not game simulation traffic**.
  The exact ping format (36 printable UUID bytes; server echoes unchanged)
  is now observed, not just guessed.

Comparison: prior Switch research saw 38-byte *UUID-shaped* UDP packets
to UDP/50000 and replies; see `docs/PROTOCOL_2026-10-21.md`.
Be careful comparing lengths: check whether they describe identical protocol
layers, packet payload vs original frame, and whether an extra prefix exists.
There is nevertheless a **strong transport-level resemblance** to the
Switch client's `MatchmakeStart.dcPings` field in its embedded protobuf.

## Post-lobby UDP gameplay session — separate from TLS backend

- At **+479.313 seconds**, game device begins exchanging UDP with
  remote `82.117.225.177:48804` using local port **49000**.
- Through **+581.306 seconds**: **3,658** datagrams in approximately
  **102 seconds**; 1,070 device→remote and 2,588 remote→device.
- Device→remote: approximately 91,432 bytes of UDP payload;
  remote→device: approximately 577,335 bytes of UDP payload.
  **668,767 bytes** total UDP application payload.
- All 3,658 datagrams share the exact same **8-byte payload prefix**,
  including both directions. The value is deliberately not recorded here.
  This is compatible with a session/channel identifier, **not proof of its
  meaning**; subsequent bytes vary, and protocol fields are not decoded.
- Inbound traffic shows about **24 datagrams/second** for much of the
  interval; the device sends fewer datagrams per second.
- The remote prefix `82.117.225.0/24` is announced by
  **AS199524 / G-Core Labs S.A.** (infrastructure hosting).
  See https://ipinfo.io/ips/82.117.225.0/24
- A **hosted game server or relay** is more plausible than a residential
  P2P host. A single trace cannot prove whether gameplay is authoritative
  on that machine or merely forwarded to another player.

A DNS lookup for **`stun.hydrapi.net`** occurs immediately before the
gameplay UDP flow (~+479.25 seconds), but this capture shows **no UDP
packets to any of the three returned IPv4 addresses**. The DNS query by
itself does not prove STUN exchange, NAT traversal or direct P2P.

No earlier flow of comparable duration/packet rate is observed before
the +479s event. This is **consistent** with the user's failed first
multiplayer attempt never entering an established gameplay transport.
It does not identify the precise application error.

## What this changes in the Switch reimplementation

1. Keep **control plane** (Hydra TLS: login / Presence / matchmaking / profile /
   session allocation) conceptually separate from **data plane** (UDP game
   transport). Internal lobby grouping is not enough.
2. UDP/50000 probe *response semantics* are now clear for this Xbox capture:
   36-byte UUID echo. The Switch's UDP packet length/framing still needs
   verification before implementing an opt-in native Switch echo responder.
   Current `udp_port_probe.py` is observation-only and deliberately never
   echoes; do not misrepresent it as production UDP support.
3. The successful gameplay session used **49000→48804/UDP**; watch for
   the same port family on **actual Switch** when it reaches a game.
   A public advertised endpoint and a valid session allocation may be
   required even after user lookup and party composition work.
4. The initial failed multiplayer attempt has no corresponding sustained
   game UDP path. Prioritize the control-plane transition and post-match
   profile response on our actual Switch client.
5. Next useful evidence: two real Switches with a packet capture around
   the exact moment the client leaves matchmaking. Correlate valid
   `UserBaseData` lookups, status/push delivery, advertised game endpoint
   and UDP handshakes before deciding between a UDP relay and a full
   authoritative server.

## Privacy and reproducibility

The raw PCAP has real device MACs, DNS names, IP endpoints and
possibly private application/session identifiers. **Do not commit it**,
copy raw token-bearing payloads into logs, or publicly share it without
explicit source consent and sanitization. The original PCAP is available
to the current research session, not mirrored in this repository.
