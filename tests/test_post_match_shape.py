"""New post-match endpoint: privacy-limited nested field inspection only."""
import unittest

from request_shape import (
    POST_MATCH_USER_LOOKUP_CANDIDATE, nested_shape, unknown_request_summary,
    eligible,
)
from wwz_wire import blob, scalar


def fake_user_id(seed):
    # Synthetic bcl.Guid fixed64=1, fixed64=2 -> backendPb.UserId.Uid=1.
    guid = b"\x09" + bytes([seed])*8 + b"\x11" + bytes([seed+1])*8
    return blob(1, guid)


def public_data_lookup():
    # IPossibleUserService_GetUsersPublicData.users field1 repeated:
    # 22 bytes per UserId, hence two users -> 44 bytes exactly.
    return blob(1, fake_user_id(7)) + blob(1, fake_user_id(9))


class PostMatchShapeTests(unittest.TestCase):
    def test_two_user_ids_fit_exactly_44_bytes_and_shape_has_no_identifiers(self):
        raw = public_data_lookup()
        self.assertEqual(44, len(raw))
        self.assertTrue(eligible(POST_MATCH_USER_LOOKUP_CANDIDATE))
        summary = unknown_request_summary(POST_MATCH_USER_LOOKUP_CANDIDATE, raw)
        self.assertEqual(44, summary["bytes"])
        self.assertEqual("protobuf", summary["format"])
        self.assertEqual([1, 1], [field["field"] for field in summary["fields"]])
        for outer in summary["fields"]:
            self.assertEqual(2, outer["wire"])
            self.assertEqual(20, outer["size"])
            nested = outer["children"][0]
            self.assertEqual((1, 2, 18),
                             (nested["field"], nested["wire"], nested["size"]))
            self.assertEqual([1, 2],
                             [x["field"] for x in nested["children"]])
            self.assertEqual([1, 1],
                             [x["wire"] for x in nested["children"]])
        self.assertNotIn("070707", str(summary))
        self.assertNotIn("090909", str(summary))
        self.assertNotIn("token", str(summary))

    def test_other_methods_stay_within_old_logging_scope(self):
        raw = public_data_lookup()
        different = POST_MATCH_USER_LOOKUP_CANDIDATE[:-1] + "a"
        self.assertFalse(eligible(different))
        self.assertIsNone(unknown_request_summary(different, raw))
        self.assertNotIn("children", str(unknown_request_summary(
            "/b89429154e224660837a4a307391b0b4.svc/"
            "b2a1ab68eb464d7796c4e9f49247d3c8", raw)))

    def test_invalid_and_oversized_data_never_echo_contents(self):
        self.assertEqual("unknown",
                         unknown_request_summary(
                             POST_MATCH_USER_LOOKUP_CANDIDATE, b"\x0a\x20\xff")["format"])
        summary = unknown_request_summary(
            POST_MATCH_USER_LOOKUP_CANDIDATE, blob(1, b"x"*2050))
        self.assertEqual("over_limit", summary["format"])
        self.assertNotIn("xxxxx", str(summary))


if __name__ == "__main__":
    unittest.main()
