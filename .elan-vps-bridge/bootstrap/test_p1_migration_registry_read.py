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

    def _request_fn(self, *, wrong_id=False):
        calls = []
        rows = {
            "MIG-044": {"migration_id": "MIG-044", "state": "PASS", "baseline": True},
            "MIG-045": {"migration_id": "MIG-045", "state": "NOT_STARTED"},
            "MIG-046": {"migration_id": "MIG-046", "state": "NOT_STARTED"},
            "MIG-050": {"migration_id": "MIG-050", "state": "NOT_STARTED"},
        }

        def request_fn(payload):
            calls.append(payload)
            if payload["operation"] == "prepare_procedure":
                steps = payload["procedure"]["steps"]
                self.assertEqual(len(steps), 5)
                self.assertEqual(steps[0]["args"], {
                    "profile": "business",
                    "template": "en033_m1_mig037_registry_read_all_v1",
                    "parameters": [],
                })
                for index, migration_id in enumerate(("MIG-044", "MIG-045", "MIG-046", "MIG-050"), start=1):
                    self.assertEqual(steps[index]["primitive"], "postgres_query_template")
                    self.assertEqual(steps[index]["args"], {
                        "profile": "business",
                        "template": "en033_m1_mig037_registry_read_v1",
                        "parameters": [migration_id],
                    })
                return {"plan": {
                    "risk": "read_only",
                    "plan_id": "p1-read-plan",
                    "execution_token": "token",
                    "procedure_sha256": "sha",
                }}
            receipt_steps = [{
                "step_id": "migration-registry-read-all",
                "status": "success",
                "result": {
                    "template": "en033_m1_mig037_registry_read_all_v1",
                    "values": ['[{"migration_id":"MIG-001"}' + ("x" * 5000) + "...[truncated]"],
                },
            }]
            for migration_id in ("MIG-044", "MIG-045", "MIG-046", "MIG-050"):
                row = dict(rows[migration_id])
                if wrong_id and migration_id == "MIG-046":
                    row["migration_id"] = "MIG-047"
                receipt_steps.append({
                    "step_id": f"migration-registry-read-{migration_id.lower()}",
                    "status": "success",
                    "result": {
                        "template": "en033_m1_mig037_registry_read_v1",
                        "values": [json.dumps(row)],
                    },
                })
            return {"receipt": {
                "status": "succeeded",
                "execution_class": "read_only",
                "run_id": "run-p1-read",
                "replayed": False,
                "steps": receipt_steps,
            }}

        return calls, rows, request_fn

    def test_read_preserves_canonical_read_all_then_recovers_bounded_entries(self):
        calls, rows, request_fn = self._request_fn()
        result = command_port.read_en2_p1_migration_registry_v1("gh-issue-999", request_fn=request_fn)
        self.assertEqual(result["execution_class"], "read_only")
        self.assertEqual(result["entries"], [rows[mid] for mid in ("MIG-044", "MIG-045", "MIG-046", "MIG-050")])
        self.assertEqual(result["template"], "en033_m1_mig037_registry_read_all_v1")
        self.assertEqual(result["entry_template"], "en033_m1_mig037_registry_read_v1")
        self.assertEqual(result["read_all_transport"], "SANITIZER_TRUNCATED_BOUNDED_FALLBACK")
        self.assertFalse(result["external_action_allowed"])
        self.assertEqual([call["operation"] for call in calls], ["prepare_procedure", "start_run"])

    def test_bounded_entry_identity_mismatch_fails_closed(self):
        _, _, request_fn = self._request_fn(wrong_id=True)
        with self.assertRaisesRegex(command_port.CommandPortError, "broker_p1_registry_entry_identity_mismatch"):
            command_port.read_en2_p1_migration_registry_v1("gh-issue-999", request_fn=request_fn)


# Verification-only trigger after the bot-published runtime v2 commit.
if __name__ == "__main__":
    unittest.main(verbosity=2)
