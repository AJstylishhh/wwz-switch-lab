#!/usr/bin/env python3
"""Offline, opt-in experimental authorization queue response fixture.

This is valid protobuf according to extracted descriptors, not game-verified.
Only use IF second GUID route is confirmed as IAuthorizationService_Enqueue.
Does NOT create a real authenticated player session.
"""
import argparse
from pathlib import Path
import secrets
from wwz_wire import scalar, blob, string

AUTH_ROUTE = "/0ae806e0260340fe86eb38ff8708252f.svc/3ad39ec0971940b98e522d40229704b9"
RESULT_FIELD = 262225376


def candidate(token: str) -> bytes:
    # AuthorizationQueueToken: Token=1, State=2 (ReadyToDequeue).
    queue_token = string(1, token) + scalar(2, 2)
    # AuthorizationQueueTokenPosition: Token=1, Position=2 (zero).
    position = blob(1, queue_token) + scalar(2, 0)
    # ServiceResult: retCode=1 (Success=0);
    # ServiceResult_AuthorizationQueueTokenPosition=262225376; data=1.
    return scalar(1, 0) + blob(RESULT_FIELD, blob(1, position))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True,
                        help="local .bin fixture; do not commit")
    args = parser.parse_args()
    token = "wwz-lab-" + secrets.token_urlsafe(32)
    encoded = candidate(token)
    args.out.write_bytes(encoded)
    print(f"Wrote {len(encoded)} bytes to {args.out}; keep privately.")
    print("Only test after auth_probe.py supports identifying the method.")
    print("Queueing, issuing an identity, and dequeueing are NOT implemented.")


if __name__ == "__main__":
    main()
