# WWZ Switch: two-source trace and experimental Multiplayer menu entitlement hypothesis

Authored by OpenAI ChatGPT (GPT-6), not repository owner. Research branch only.

## User's current test

File: client-pairs-20261023-222632.log (623 lines, 22:26:32–22:31:37). User reports no obvious behavioral improvement; both consoles can create local lobby UI but cannot find each other's lobby. One Switch OLED with Atmosphere 1.11.2 on system FW 22.5.0 opens eShop/system-update prompt when selecting Multiplayer, whereas the other Switch with Atmosphere 1.12.1 on FW 22.5.0 (previously 23.0.1) reaches Find Match and Classes.

## Evidence from the new server log

- 321 POST requests: 215 from source_tag f473cc24fd31 and 106 from source_tag 5a1200965d00. These process-keyed tags indicate two distinct network sources, not verified identity/player accounts.
- Both signed in successfully: source A started at 22:27:41, source B at 22:29:09. Both continue heartbeat updates until the capture ends. Counts: 136 (A) and 70 (B).
- Presence method 67cdaf75ca604bd993ad9f1db0c3f812 (high-confidence MatchmakeStart based on field schema) called 9 times from A and 3 times from B. These are attempts, not a functioning queue.
- Source A called the likely game-data RPC 44a718e4c7514684b5259e0879e98c63 18 times and source B called it 3 times. Both independently exchange lab RPCs but no shared lobby or membership is returned.
- No new unmapped RPC warnings, no rejected token refresh, no evidence of a successful cross-device join. No HTTP request in this log proves why the Nintendo eShop UI opened; OS applet transactions may bypass this experimental WWZ server entirely.

## ProviderInfo.HasSubscription hypothesis

Extracted Switch NSO protobuf descriptor defines SignInResult.ProviderInfo (field 10) as ProviderOptionalInfo with HasSubscription (field 1, optional bool default false), Environment (field 2). Previous synthetic SignInResult omitted HasSubscription entirely. It is plausible, but NOT established, that this influences the Multiplayer menu's online membership path. Nintendo lists some World War Z online modes as requiring Nintendo Switch Online membership; server-side value is NOT evidence or a replacement for a valid Nintendo entitlement.

Repository now supports opt-in bool provider_has_subscription on ONLY the experimental auth Dequeue route. Setting true adds typed protobuf ProviderInfo.HasSubscription=1 to the lab's SignInResult. By default it is absent and behavior unchanged; the helper is reversible and rejects conflicting user settings.

Atmosphere 1.11.2 officially supports FW 22.5.0. Release notes for 1.12.1 describe support for new firmware-23 DNS resolver, filesystem API and browser applet fixes. Neither is evidence that the WWZ Multiplayer button is directly fixed by moving 1.11.2 to 1.12.1 on FW 22.5.0. The two consoles may also differ in Nintendo Account, Switch Online subscription, game/DLC/update version, eShop applet, installed sysmodules, or remnants of a system downgrade. Avoid irreversible firmware modifications based on this observation.

### VPS test (A/B, one affected Switch first)

1. Stop Python with Ctrl+C. Preserve existing working nine-version, presence, and seven-lobby success routes.
2. Enable synthetic subscription probe:

```bash
cd /opt/wwz-switch-lab
git pull --ff-only
python3 -m unittest discover -s tests -p test_multiplayer_subscription_probe.py -v
cp -p routes.remote.local.json routes.remote.presubscription.local.json
printf '%s\n' '/routes.remote.presubscription.local.json' >> .git/info/exclude
python3 enable_multiplayer_subscription_probe.py routes.remote.local.json
umask 077
mkdir -p logs
PYTHONUNBUFFERED=1 python3 mvp_server.py \
  --host 0.0.0.0 --ports 11701,11702,11704 \
  --routes routes.remote.local.json \
  --cert certs/server.crt --key certs/server.key \
  --trace-clients 2>&1 | tee "logs/subscription-$(date +%Y%m%d-%H%M%S).log"
```

3. On affected Switch, fully exit/relaunch World War Z so SignInResult is reissued; select the Multiplayer button. Record whether it still opens eShop/system-update or reaches Find Match and Classes. Record whether normal Online and lobby UI still work.
4. A/B rollback (stop Python first) and restart original command:

```bash
python3 enable_multiplayer_subscription_probe.py routes.remote.local.json --undo
```

Alternatively restore the complete pretest file using cp -p. The flag is NOT a bypass of Nintendo's system-side network checks; if eShop behavior persists, focus on console account/entitlement/app-side check and exact UI message, not the Hydra backend.

## Real matchmaking still requires implementing shared state

The lobby RPC probe still sends bare Success (08 00). It does not allocate lobby ID, owner, members, join-code, session transport, list result or cross-client data. Neither a second successful sign-in nor MatchmakeStart creates a findable lobby with current code. Next: identify exact methods and response extension types for Invite/Join/GetStatusSquad/Matchmake and implement per-identity lobby registry. Do not claim joining enabled by HasSubscription toggle.
