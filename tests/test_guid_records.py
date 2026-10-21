"""Construct a tiny synthetic .rodata to verify GUID pointer-table parsing."""
import unittest
from struct import pack_into

from inspect_guid_records import records


class GuidRecordTests(unittest.TestCase):
    def test_valid_record_and_bad_marker(self):
        base = 0x2131000
        data = bytearray(200)
        guid = b"c928398a5e4b4debb4099f62383eb196\x00"
        data[96:96 + len(guid)] = guid
        pack_into("<QQQ", data, 0, base + 96, 0x2e521f0, 0x403)
        pack_into("<QQQ", data, 24, base + 96, 0x2e52200, 0x402)
        found = list(records(data, base))
        self.assertEqual(1, len(found))
        self.assertEqual("c928398a5e4b4debb4099f62383eb196", found[0]["guid"])
        self.assertEqual("0x2131000", found[0]["record_va"])


if __name__ == "__main__":
    unittest.main()
