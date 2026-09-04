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

    def test_rollout_ready_cleanup_happen_before_exactly_one_fresh_read(self):
        events = []
        aggregate = {
            "plan_count": 8,
            "occurrence_count": 8,
            "publication_state_counts": {"PLANNED": 1, "PROGRAMMED": 7, "PUBLISHED": 0},
            "observation_state_counts": {
                "NOT_OBSERVED": 8,
                "AMBIGUOUS": 0,
                "CONFIRMED_NOT_FOUND": 0,
                "CONFIRMED_PUBLISHED": 0,
            },
        }
        prepare_count = 0

        def request_fn(payload):
            nonlocal prepare_count
            operation = payload["operation"]
            events.append(operation)
            if operation == "stage_https":
                self.assertEqual(payload["expected_sha256"], command_port.MIG045_QUALIFIED_TRANSFER_SHA256)
                self.assertEqual(payload["expected_size_bytes"], command_port.MIG045_QUALIFIED_TRANSFER_SIZE)
                return {"artifact": {"artifact_id": "qualified-artifact"}}
            if operation == "prepare_procedure":
                prepare_count += 1
                step = payload["procedure"]["steps"][0]
                if prepare_count == 1:
                    self.assertEqual(step["primitive"], "qualified_release_install")
                    self.assertEqual(step["args"], {
                        "artifact_id": "qualified-artifact",
                        "expected_version": "1.3.51",
                        "expected_source_commit": command_port.MIG045_SOURCE_COMMIT,
                    })
                    return {"plan": {"risk": "reversible_technical_change", "plan_id": "rollout-plan", "execution_token": "rollout-token", "procedure_sha256": "rollout-sha"}}
                self.assertEqual(step["primitive"], "postgres_query_template")
                self.assertEqual(step["args"], {"profile": "business", "template": command_port.MIG045_READ_TEMPLATE, "parameters": []})
                return {"plan": {"risk": "read_only", "plan_id": "read-plan", "execution_token": "read-token", "procedure_sha256": "read-sha"}}
            if operation == "start_run" and payload["plan_id"] == "rollout-plan":
                self.assertEqual(payload["execution_class"], "reversible_technical_change")
                return {"receipt": {"status": "succeeded", "run_id": "rollout-run", "steps": [{"step_id": "qualified-release-install", "status": "success", "result": {"version": "1.3.51"}}]}}
            if operation == "cleanup_artifact":
                return {"result": {"status": "cleaned"}}
            if operation == "start_run" and payload["plan_id"] == "read-plan":
                return {"receipt": {"status": "succeeded", "execution_class": "read_only", "run_id": "read-run", "replayed": False, "steps": [{"step_id": "mig045-editorial-fresh-read", "status": "success", "result": {"template": command_port.MIG045_READ_TEMPLATE, "rows": 1, "sha256": "fresh-sha", "values": [json.dumps(aggregate, sort_keys=True)]}}]}}
            self.fail(payload)

        def ready_fn():
            events.append("ready-proof")
            return {"status": "ready", "version": "1.3.51"}

        result = command_port.run_mig045_v1351_rollout_and_fresh_read_v1(
            "gh-issue-999",
            GOOD_URL,
            request_fn=request_fn,
            ready_fn=ready_fn,
        )
        self.assertEqual(result["ready_proof"]["version"], "1.3.51")
        self.assertEqual(result["fresh_read"]["aggregate"], aggregate)
        self.assertEqual(result["fresh_read"]["rows"], 1)
        self.assertFalse(result["free_sql"])
        self.assertFalse(result["external_action_allowed"])
        self.assertEqual(events, [
            "stage_https",
            "prepare_procedure",
            "start_run",
            "ready-proof",
            "cleanup_artifact",
            "prepare_procedure",
            "start_run",
        ])
        self.assertEqual(sum(1 for event in events if event == "prepare_procedure"), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
