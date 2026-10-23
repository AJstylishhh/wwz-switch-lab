# Next controlled WWZ connection experiment: provider environment

Research by OpenAI ChatGPT (GPT-6), not repository owner. Main branch unchanged by this experiment.

## Why

The earlier data-center test did not clear the main-menu error. The
diagnostic ADF upload is binary, and its 12-byte `entries` records are
NOT a simple sequential offset/length index (zero strong matches across
31 uploads). Static ARM64 inspection located real `ADF_STREAM` methods,
but does not yet provide a decoded root-cause record.

The recovered protobuf descriptor defines:

```
SignInResult.ProviderInfo = 10
ProviderOptionalInfo.Environment = 2
ServerEnvironment_Retail = 2
```

Our previous `SignInResult` omitted `ProviderInfo` entirely; this
means the client's environment lookup may default to Unknown. An
optional variant now includes **only** `ProviderInfo.Environment=Retail`
and leaves `HasSubscription` absent/false. This is not a substitute
for any legitimate Nintendo subscription, nor a demonstrated fix.

## A/B isolation

`routes.mvp.example.json` is the old baseline (no provider info).
`routes.provider-retail.example.json` changes exactly one config value
for the Dequeue method. The latter adds just one optional nested
protobuf field in SignInResult. The existing data-center experiment
`routes.datacenter.example.json` is NOT combined.

Start the baseline or alternate server on the SAME Git revision,
with the same certificates, Switch and network; stop the other process
first, since TCP 11702 and 11704 must be free.

Baseline: `py mvp_server.py --host 0.0.0.0 --routes routes.mvp.example.json`

Variant: `py mvp_server.py --host 0.0.0.0 --routes routes.provider-retail.example.json`

When using a separate repository checkout, add:
`--cert ..\wwz-switch-lab\certs\server.crt --key ..\wwz-switch-lab\certs\server.key`

Collect: the exact WWZ menu result, whether `Heartbeat.UnRegister`
still appears shortly after `PresenceConnect`, and whether other RPC
GUIDs are called. **A 200 response alone does not prove acceptance.**

Do not run multiple server variants simultaneously, and do not commit
captured credentials or TLS private keys. Default configuration and
mimicked entitlement state remain unchanged.

Regression: `py -m unittest discover -s tests -p test_provider_environment.py -v`.
