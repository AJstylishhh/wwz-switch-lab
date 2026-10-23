# Switch Multiplayer button -> Nintendo eShop / system update (Oct 24, 2026)

Authored by OpenAI ChatGPT (GPT-6); research branch only.

## Hardware report

- Console A: Switch OLED, official system firmware 22.5.0, Atmosphère 1.11.2. World War Z connects to experimental Hydra and online UI/lobby functions. Selecting Multiplayer briefly says connection lost, displays the Nintendo eShop logo, then 'A system update is required before you can proceed.'
- Console B: older Switch, official system firmware 22.5.0, Atmosphère 1.12.1; had run firmware 23.0.1 before downgrading. Multiplayer displays 'Find Match' / 'Classes' but both clients still cannot find each other's lobbies.
- A/B with experimental synthetic Hydra SignInResult ProviderInfo.HasSubscription=true had no observed effect on the affected console. Undo that experiment with enable_multiplayer_subscription_probe.py routes.remote.local.json --undo. Leave previously successful online/lobby responses unchanged.

## New static executable evidence

The user's supplied Nintendo Switch executable extracted from wwz exefx.zip (main) contains the Itanium C++ mangled name:

```
_ZN2nn7account40ShowLicenseRequirementsForNetworkServiceERKNS0_10UserHandleE
```

This demangles to:

```cpp
nn::account::ShowLicenseRequirementsForNetworkService(nn::account::UserHandle const&)
```

The binary also includes nn::ec::ShowShopProductDetails and nn::ec::ShowShopAddOnContentList SDK symbols, plus generic marketplace entitlement strings. This is consistent with a game-side/native-system online-license or eShop interface rather than an HTTP call to the custom Hydra backend. Import presence DOES NOT establish that the Multiplayer button invokes the SDK function; call-site identification requires separate static disassembly or live instrumentation.

## Firmware / CFW distinction

Nintendo's current firmware as of Oct 24, 2026 is 23.0.1. The eShop can require updating system firmware. Updating only Atmosphère does NOT change the installed Nintendo system firmware or grant a Nintendo Switch Online membership.
Official Atmosphère release notes: 1.11.2 explicitly supports system FW 22.5.0; 1.12.1 supports FW 23.0.x DNS resolver changes and browser applet fixes. No release note proves an WWZ Multiplayer menu fix. It is possible to test a newer Atmosphère version while keeping HOS 22.5.0, with correct matching boot payload and a complete SD/emuMMC backup; do NOT update the underlying Nintendo firmware without independent reason and an appropriate rollback plan.

## Device-only controlled test (no forced system FW update)

1. Both Switch testers note System Settings -> System version including the (E) vs (S) suffix (emuMMC/sysMMC), Atmosphère version, game version through + Options, game update and installed DLC. Compare the selected local Nintendo user profile and any legitimate Nintendo Switch Online entitlement (use Nintendo Account web portal rather than the eShop on a modified console).
2. If CFW changes are acceptable, backup the affected console's microSD, boot files, Atmosphère hosts redirects, and the emuMMC if used. Try official Atmosphère 1.12.1 PLUS the matching fusee.bin (or updated Hekate launch setup) while **leaving system FW at 22.5.0**. This isolates whether the CFW version explains the behavioral difference. Do not overwrite or discard the custom wwz.wwzapi.com host redirect.
3. When modifying CFW for a test, temporarily disable optional third-party menu replacements/overlays/sysmodules (e.g. custom qlaunch/eshop replacement, themes) only after backing them up; do not delete core Atmosphère services. Re-test WWZ from a complete power-off, not only sleep mode.
4. If it still invokes the eShop, treat the firmware prompt as Nintendo's system behavior, not evidence our Hydra TLS server is misconfigured. Follow the game-specific code path to its account/license UI before attempting an ExeFS patch; no safe or working patch has been established.
5. Do not connect a modified emuMMC to Nintendo services merely to check this hypothesis; Nintendo Account membership can be checked through the ordinary web portal on a PC. Network/ban risk depends on configuration.

## Project's game-backend scope

These native Nintendo license checks are distinct from the current absent lobby registry/membership replication in mvp_server.py. Resolving the menu does not make peer-to-peer join or gameplay work until shared server-side state and transport signaling are implemented.

Sources:
- https://github.com/Atmosphere-NX/Atmosphere/releases/tag/1.11.2
- https://github.com/Atmosphere-NX/Atmosphere/releases/tag/1.12.1
- https://en-americas-support.nintendo.com/app/answers/detail/a_id/22525/
- https://en-americas-support.nintendo.com/app/answers/detail/a_id/41199/
