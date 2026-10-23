#!/usr/bin/env python3
"""Opt-in diagnostic toggle for the synthetic WWZ SignInResult subscription bit.

This changes ONLY the Dequeue handler's provider_has_subscription field, not
Nintendo system entitlements, credentials, game files, Atmosphere or DNS.
Server restart is required for the changed route JSON to take effect.
"""
import argparse
import json
import os
from pathlib import Path
import tempfile

DEQUEUE = "0ae806e0260340fe86eb38ff8708252f.svc/c4504538d0ca4b2fb2a9e87f0091f97e"


def update(config, undo=False):
    if not isinstance(config, dict):
        raise ValueError("route configuration must be JSON object")
    if DEQUEUE not in config or config[DEQUEUE].get("handler") != "dequeue":
        raise ValueError("expected auth Dequeue handler not found")
    current = config[DEQUEUE]
    before = current.get("provider_has_subscription")
    if undo:
        if before is None:
            return config
        if before is not True:
            raise ValueError("cannot undo customized subscription setting")
    else:
        if before is not None and before is not True:
            raise ValueError("refusing to overwrite customized subscription setting")
    output = {key: dict(value) for key, value in config.items()}
    if undo:
        output[DEQUEUE].pop("provider_has_subscription", None)
    else:
        output[DEQUEUE]["provider_has_subscription"] = True
    return output


def modify_file(path, undo=False):
    original = json.loads(path.read_text(encoding="utf-8"))
    result = update(original, undo)
    fd, temp = tempfile.mkstemp(prefix=".wwz-multiplayer-", dir=path.parent)
    try:
        os.fchmod(fd, path.stat().st_mode & 0o777)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(result, file, indent=2)
            file.write("\n")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("routes", type=Path)
    ap.add_argument("--undo", action="store_true",
                    help="remove only this diagnostic subscription override")
    args = ap.parse_args()
    modify_file(args.routes, args.undo)
    print("Synthetic SignIn ProviderInfo.HasSubscription probe:",
          "disabled" if args.undo else "enabled")
    print("No Nintendo account entitlement or Atmosphere change is made.")


if __name__ == "__main__":
    main()
