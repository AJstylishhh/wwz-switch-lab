#!/usr/bin/env python3
"""Recover two embedded WWZ protobuf descriptors from a locally extracted NSO rodata.

Usage: pip install protobuf
       python extract_descriptors.py main.rodata.bin --output generated-descriptors
No Nintendo game binary or captured credentials should be committed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from google.protobuf import descriptor_pb2


def varint(data, index):
    value = 0
    for shift in range(0, 70, 7):
        if index >= len(data):
            raise ValueError("truncated protobuf")
        byte = data[index]
        index += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, index
    raise ValueError("oversized protobuf varint")


def recover(data, filename):
    needle = bytes((10, len(filename))) + filename.encode("ascii")
    start = data.find(needle)
    if start < 0:
        raise ValueError(f"descriptor {filename} not found")
    cursor = start
    while cursor < len(data):
        try:
            tag, pos = varint(data, cursor)
            field, wire = tag >> 3, tag & 7
            if field not in {1,2,3,4,5,6,7,8,9,10,11,12,14,15} or wire != 2:
                break
            size, pos = varint(data, pos)
            if size > 2_000_000 or size > len(data)-pos:
                break
            cursor = pos+size
        except ValueError:
            break
    descriptor = descriptor_pb2.FileDescriptorProto()
    descriptor.ParseFromString(data[start:cursor])
    if descriptor.name != filename or not descriptor.message_type:
        raise ValueError(f"invalid descriptor {filename}")
    return data[start:cursor], descriptor


def field_text(field, types, labels, indent="  "):
    label = labels.Name(field.label).removeprefix("LABEL_").lower()
    type_name = (field.type_name.lstrip(".") if field.type in (10,11,14) else
                 types.Name(field.type).removeprefix("TYPE_").lower())
    declaration = f"{indent}{label} {type_name} {field.name} = {field.number}"
    options = []
    if field.HasField("default_value"):
        default = field.default_value
        if field.type in (9,12):
            default = json.dumps(default)
        options.append("default = " + str(default))
    if field.options.HasField("packed"):
        options.append("packed = " + str(field.options.packed).lower())
    if options:
        declaration += " [" + ", ".join(options) + "]"
    return declaration + ";"


def emit_enum(enum, depth=0):
    indent = "  " * depth
    lines = [f"{indent}enum {enum.name} "+"{"]
    lines.extend(f"{indent}  {v.name} = {v.number};" for v in enum.value)
    return lines + [indent + "}"]


def emit_message(message, field_descriptor, depth=0):
    indent = "  " * depth
    lines = [f"{indent}message {message.name} "+"{"]
    lines.extend(field_text(f, field_descriptor.Type, field_descriptor.Label, indent+"  ")
                 for f in message.field)
    for enum in message.enum_type:
        lines.extend(emit_enum(enum, depth+1))
    for nested in message.nested_type:
        lines.extend(emit_message(nested, field_descriptor, depth+1))
    for ext in message.extension_range:
        lines.append(f"{indent}  extensions {ext.start} to {ext.end-1};")
    return lines + [indent+"}"]


def to_proto(descriptor):
    field_descriptor = descriptor_pb2.FieldDescriptorProto
    lines = ["// Reconstructed from a WWZ Switch NSO embedded descriptor.",
             'syntax = "proto2";', f"package {descriptor.package};", ""]
    lines.extend(f'import "{dep}";' for dep in descriptor.dependency)
    lines.append("")
    for enum in descriptor.enum_type:
        lines.extend(emit_enum(enum)); lines.append("")
    for message in descriptor.message_type:
        lines.extend(emit_message(message, field_descriptor)); lines.append("")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rodata", type=Path)
    parser.add_argument("--output", type=Path, default=Path("generated-descriptors"))
    args = parser.parse_args()
    data = args.rodata.read_bytes()
    args.output.mkdir(parents=True, exist_ok=True)
    for name in ("bcl.proto", "proto.proto"):
        raw, desc = recover(data, name)
        (args.output / (name + ".descriptor.bin")).write_bytes(raw)
        (args.output / name).write_text(to_proto(desc), encoding="utf-8")
        print(name, len(raw), len(desc.message_type), len(desc.enum_type))


if __name__ == "__main__":
    main()
