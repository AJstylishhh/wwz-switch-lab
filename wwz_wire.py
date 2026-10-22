"""Minimal WWZ Hydra wire encoding. Reconstructed from Switch protobuf descriptors.

The response is a syntactically valid candidate, NOT Switch-validated.
"""
ENVIRONMENT_ROUTE = "/c928398a5e4b4debb4099f62383eb196.svc/44829c126af14aeb9f535e504fa413ee"
ENVIRONMENT_RESULT_FIELD = 86868329


def varint(value):
    if not 0 <= value < 2**64:
        raise ValueError("uint64 out of range")
    output = bytearray()
    while value >= 128:
        output.append((value & 127) | 128)
        value >>= 7
    output.append(value)
    return bytes(output)


def scalar(field, value):
    return varint(field << 3) + varint(value)


def blob(field, value):
    return varint((field << 3) | 2) + varint(len(value)) + value


def string(field, value):
    return blob(field, value.encode("utf-8"))


def environment_result(address, port, name, environment_id, region, datacenter_id=None):
    """ServiceResult<ServiceResult_EnvironmentList<EnvironmentList>>.

    Only shape and field numbers are confirmed; endpoint values are hypotheses.
    """
    port = int(port)
    if not 1 <= port <= 65535:
        raise ValueError("invalid TCP port")
    if not all(isinstance(v, str) and v for v in (address, name, environment_id, region)):
        raise ValueError("environment values must be nonempty strings")
    # CompactEndpointInfo: Name, IP, Port, Protocols_HTTPS=1, IsDefault.
    endpoint = string(1, name) + string(2, address) + scalar(3, port) + scalar(4, 1) + scalar(5, 1)
    # EnvironmentInfo: Endpoint=1, EnvironmentId=2, Region=3,
    # DataCenters=5 (repeated), IsUnderMaintenance=6.
    env = blob(1, endpoint) + string(2, environment_id) + string(3, region)
    if datacenter_id is not None:
        if not isinstance(datacenter_id, str) or not datacenter_id:
            raise ValueError("datacenter_id must be a nonempty string")
        # DataCenterInfo: DataCenterId=1, Occupation=2 (0),
        # HideWhenNotAvailable=3 (false), Endpoints=4.
        # This is a *mock* datacenter, not an actual WWZ matchmaking server.
        dc = (string(1, datacenter_id) + scalar(2, 0) + scalar(3, 0) +
              blob(4, endpoint))
        env += blob(5, dc)
    env += scalar(6, 0)
    # EnvironmentList.Environments=1; ServiceResult_EnvironmentList.data=1
    wrapped = blob(1, blob(1, env))
    return scalar(1, 0) + blob(ENVIRONMENT_RESULT_FIELD, wrapped)


def read_varint(data, offset):
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError("truncated protobuf varint")
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
    raise ValueError("oversized protobuf varint")


def fields(data):
    i = 0
    while i < len(data):
        tag, i = read_varint(data, i)
        field, wire = tag >> 3, tag & 7
        if not field:
            raise ValueError("protobuf field zero")
        if wire == 0:
            value, i = read_varint(data, i)
        elif wire == 2:
            n, i = read_varint(data, i)
            if n > len(data) - i:
                raise ValueError("truncated length-delimited field")
            value = data[i:i+n]
            i += n
        elif wire in (1, 5):
            n = 8 if wire == 1 else 4
            value = data[i:i+n]
            if len(value) != n:
                raise ValueError("truncated fixed-width field")
            i += n
        else:
            raise ValueError(f"unsupported wire type {wire}")
        yield field, wire, value


def describe_environment_request(raw):
    """Log public build metadata, never fingerprints or authentication tokens."""
    build = {}
    versions = 0
    for field, wire, value in fields(raw):
        if field == 1 and wire == 2:
            for child, kind, part in fields(value):
                if child == 1 and kind == 2:
                    build["configuration"] = part.decode("utf-8", "replace")
                elif child == 2 and kind == 2:
                    build["version"] = part.decode("utf-8", "replace")
        elif field == 2 and wire == 2:
            versions += 1
    return {"build": build, "service_versions": versions, "bytes": len(raw)}
