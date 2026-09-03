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


class P1MigrationRegistryReadContractTest(unittest.TestCase):
    def test_issue_contract_is_exact_and_bounded(self):
        issue = {
            "number": 999,
            "title": "EN-INTENT — EN2_P1_MIGRATION_REGISTRY_READ contract",
            "body": json.dumps({
                "intent_code": "EN2_P1_MIGRATION_REGISTRY_READ",
                "context": {"target": "en2-p1-migration-registry"},
            }),
            "user": {"login": issue_inbox.ISSUE_AUTHOR},
        }
        job = issue_inbox.parse_issue_intent(issue)
        self.assertIsNotNone(job)
        self.assertEqual(job["intent_code"], "EN2_P1_MIGRATION_REGISTRY_READ")
        bad = dict(issue)
        bad["body"] = json.dumps({
            "intent_code": "EN2_P1_MIGRATION_REGISTRY_READ",
            "context": {"target": "en2-p1-migration-registry", "sql": "select 1"},
        })
        self.assertIsNone(issue_inbox.parse_issue_intent(bad))

    def test_read_uses_existing_fixed_registry_template_only(self):
        calls = []
        rows = [
            {"migration_id": "MIG-044", "state": "PASS", "baseline": True},
            {"migration_id": "MIG-045", "state": "NOT_STARTED"},
            {"migration_id": "MIG-046", "state": "NOT_STARTED"},
            {"migration_id": "MIG-050", "state": "NOT_STARTED"},
        ]

        def request_fn(payload):
            calls.append(payload)
            if payload["operation"] == "prepare_procedure":
                step = payload["procedure"]["steps"][0]
                self.assertEqual(step["primitive"], "postgres_query_template")
                self.assertEqual(step["args"], {
                    "profile": "business",
                    "template": "en033_m1_mig037_registry_read_all_v1",
                    "parameters": [],
                })
                return {"plan": {
                    "risk": "read_only",
                    "plan_id": "p1-read-plan",
                    "execution_token": "token",
                    "procedure_sha256": "sha",
                }}
            return {"receipt": {
                "status": "succeeded",
                "execution_class": "read_only",
                "run_id": "run-p1-read",
                "replayed": False,
                "steps": [{
                    "step_id": "migration-registry-read",
                    "status": "success",
                    "result": {
                        "template": "en033_m1_mig037_registry_read_all_v1",
                        "values": [json.dumps(rows)],
                    },
                }],
            }}

        result = command_port.read_en2_p1_migration_registry_v1("gh-issue-999", request_fn=request_fn)
        self.assertEqual(result["execution_class"], "read_only")
        self.assertEqual(result["entries"], rows)
        self.assertEqual(result["template"], "en033_m1_mig037_registry_read_all_v1")
        self.assertFalse(result["external_action_allowed"])
        self.assertEqual([call["operation"] for call in calls], ["prepare_procedure", "start_run"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
