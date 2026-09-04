#!/usr/bin/env python3
import json
import pathlib
import sys
import unittest

BOOTSTRAP = pathlib.Path(__file__).resolve().parent
if str(BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(BOOTSTRAP))

import command_port  # noqa: E402
import issue_inbox  # noqa: E402


INTENT = "MIG045_V1351_ROLLOUT_AND_FRESH_READ"
TARGET = "mig045-v1351-rollout-and-fresh-read"
GOOD_URL = "https://sdmntprnortheu.oaiusercontent.com/files/qualified-v1351.zip?sig=test"


def issue(context):
    return {
        "number": 999,
        "title": "EN-INTENT — MIG045 v1.3.51 rollout and fresh read",
        "body": json.dumps({"intent_code": INTENT, "context": context}),
        "user": {"login": issue_inbox.ISSUE_AUTHOR},
    }


class Mig045V1351RolloutFreshReadContractTest(unittest.TestCase):
    def test_exact_closed_intent_is_accepted(self):
        parsed = issue_inbox.parse_issue_intent(issue({"target": TARGET, "artifact_url": GOOD_URL}))
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["intent_code"], INTENT)
        self.assertEqual(parsed["context"], {"target": TARGET, "artifact_url": GOOD_URL})

    def test_non_oai_url_and_any_broader_control_are_rejected(self):
        self.assertIsNone(issue_inbox.parse_issue_intent(issue({"target": TARGET, "artifact_url": "https://example.com/release.zip"})))
        for extra in (
            {"version": "1.3.52"},
            {"source_commit": "0" * 40},
            {"sha256": "0" * 64},
            {"size": 1},
            {"template": "other"},
            {"sql": "select 1"},
            {"phase": "FRESH_READ"},
        ):
            context = {"target": TARGET, "artifact_url": GOOD_URL, **extra}
            self.assertIsNone(issue_inbox.parse_issue_intent(issue(context)), extra)

    def test_release_and_read_contract_are_hard_pinned(self):
        self.assertEqual(command_port.MIG045_TARGET_VERSION, "1.3.51")
        self.assertEqual(command_port.MIG045_SOURCE_COMMIT, "275118ca38cd36cdbfc25c9cf9c72d1fca09b89f")
        self.assertEqual(command_port.MIG045_QUALIFIED_TRANSFER_SHA256, "4825b62c4df34806c98d1379f1df325fbc3f571bceea20e5f05e17bccfd790e0")
        self.assertEqual(command_port.MIG045_QUALIFIED_TRANSFER_SIZE, 63986974)
        self.assertEqual(command_port.MIG045_READ_TEMPLATE, "en033_m1_mig045_editorial_readback_v1")
        self.assertEqual(command_port.MIG045_EXPECTED_FIELDS, {
            "plan_count",
            "occurrence_count",
            "publication_state_counts",
            "observation_state_counts",
        })


if __name__ == "__main__":
    unittest.main(verbosity=2)
