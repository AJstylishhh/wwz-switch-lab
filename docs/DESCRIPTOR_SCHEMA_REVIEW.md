# Descriptor-grounded review of the WWZ offline-menu problem

Analysis by OpenAI ChatGPT (GPT-6). Changes confined to the research branch.

The collaborator's OpenCode notes report generic HTTP 200 replies on the two final zero-argument methods; the 2026-10-22 19:31 local transcript supplied to ChatGPT instead records HTTP 404 for both. They are DIFFERENT server configurations/runs and should not be conflated. A later request proves progression, not semantic acceptance of the preceding response. The empty calls likely represent SignOut and PresenceDisconnect after a failure, but their GUID names remain unproven.

We recovered **317 protobuf message descriptors and 36 enums** from the user-provided Switch NSO and independently checked key fields in the reconstructed schema. Derived, private-user-shareable artifacts are available as proto.proto, bcl.proto and a focused response_spec.json; none contain captured credentials.

Important exact schema facts:

- ServiceResult (response envelope) field 1 is `retCode`, with success value 0.
- `ServiceResult_ReSignInContract` is field **239970732**, contains message `ReSignInContract { optional string Token = 1; }`.
- `ServiceResult_PresenceStatusResponse` is field **334914069** and includes nested `PresenceStatusResponse.User = 1`.
- `ServiceResult_UserHeartbeatRegisterResult` is field **438369230**; the data includes `UserVersions Versions=1`, `ClientPoling PollingIntervals=2`, `int32 UsersOnline=3`, `repeated DataCenterOccupation DataCenterOccupation=4`.
- `UserVersions.Versions = 1` is **repeated int64**. This is not a repeated version string. Our current experimental register reply includes an empty UserVersions message; whether that is semantically acceptable is unknown.
- `ServiceResult_RegisterResult` is field **347012296**; `RegisterResult.ReturnAvailableSeconds=1` is int32.
- `ServiceResult_ClientTokenList` is field **151915586**, and the child `ClientTokenList` carries `Tokens=1`, `ProviderToken=2`, `RefreshAfter=3`.
- `SignInResult.ProviderInfo=10` is an optional `ProviderOptionalInfo` with `HasSubscription=1` defaulting to **false** and `Environment=2` defaulting to Unknown. Our mock SignInResult omits this entirely. It is a *plausible* client-side entitlement/UI decision input but does not prove the reason for the menu warning. Do not claim that fabricated subscription info would establish a legitimate Nintendo entitlement.
- `EnvironmentInfo.DataCenters=5` is a repeated `DataCenterInfo`. Our default environment reply had **no** data-center entries, while heartbeat and occupation responses named a local data center. This is inconsistent and worth isolating in an A/B test rather than mixing with authentication changes.
- `IGameConfigurationService_GetActiveFirstGameDefinition` is a parameterless request in the schema, but it has **not appeared in the reported RPC logs**. Calling it the cause of the greyed-out menu without observing it would be speculation.

Both `IAccessManagementService_SignOut` and `IPresenceService_PresenceDisconnect` are defined with empty requests. Their method-to-response types are not explicitly declared by FileDescriptorProto: a bare successful ServiceResult is a candidate; do not force data wrappers on those methods without verifying the GUID/dispatch.

## One-variable experiment available

An opt-in example config `routes.datacenter.example.json` includes one mock `EnvironmentInfo.DataCenters=5` entry with ID `local` and the same local HTTPS endpoint. The existing default config is unchanged. This avoids the previously inconsistent empty DataCenters list.

Test the original server first as a baseline, then the alternative config in a separate run, recording whether the menu changes. Other responses should be held constant. The mock data center does not implement actual matchmaking.

## Privacy and source limitations

Reconstructed field numbers and message types are exact to the game's embedded FileDescriptorProto. Request-GUID/method mapping and request-to-response type mapping are independent inferences (the descriptor has no service definitions), so they must be confirmed via behavior or static dispatcher analysis. Generated schema fields are not credentials, but no game binary or raw authentication traffic is published here.
