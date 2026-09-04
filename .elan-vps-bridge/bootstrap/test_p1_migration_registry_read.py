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


EXPECTED_WINDOW = tuple(f"MIG-{number:03d}" for number in range(42, 51))


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

    def _request_fn(self, *, wrong_id=False, read_all_raw=None):
        calls = []
        rows = {
            "MIG-042": {"migration_id": "MIG-042", "state": "PASS", "baseline": True},
            "MIG-043": {"migration_id": "MIG-043", "state": "PASS", "baseline": True},
            "MIG-044": {"migration_id": "MIG-044", "state": "PASS", "baseline": True},
            "MIG-045": None,
            "MIG-046": None,
            "MIG-047": None,
            "MIG-048": None,
            "MIG-049": None,
            "MIG-050": None,
        }
        if read_all_raw is None:
            read_all_raw = '[{"migration_id":"MIG-001"}' + ("x" * 5000) + "...[truncated]"

        def request_fn(payload):
            calls.append(payload)
            if payload["operation"] == "prepare_procedure":
                steps = payload["procedure"]["steps"]
                self.assertGreaterEqual(len(steps), 1)
                self.assertEqual(steps[0]["args"], {
                    "profile": "business",
                    "template": "en033_m1_mig037_registry_read_all_v1",
                    "parameters": [],
                })
                for step in steps[1:]:
                    self.assertEqual(step["primitive"], "postgres_query_template")
                    self.assertEqual(step["args"]["profile"], "business")
                    self.assertEqual(step["args"]["template"], "en033_m1_mig037_registry_read_v1")
                    self.assertEqual(len(step["args"]["parameters"]), 1)
                    self.assertIn(step["args"]["parameters"][0], EXPECTED_WINDOW)
                return {"plan": {
                    "risk": "read_only",
                    "plan_id": "p1-read-plan",
                    "execution_token": "token",
                    "procedure_sha256": "sha",
                }}

            prepared_steps = calls[0]["procedure"]["steps"]
            receipt_steps = [{
                "step_id": "migration-registry-read-all",
                "status": "success",
                "result": {
                    "template": "en033_m1_mig037_registry_read_all_v1",
                    "values": [read_all_raw],
                },
            }]
            for step in prepared_steps[1:]:
                migration_id = step["args"]["parameters"][0]
                row = rows[migration_id]
                if row is None:
                    values = []
                else:
                    row = dict(row)
                    if wrong_id and migration_id == "MIG-046":
                        row["migration_id"] = "MIG-047"
                    values = [json.dumps(row)]
                receipt_steps.append({
                    "step_id": step["step_id"],
                    "status": "success",
                    "result": {
                        "template": "en033_m1_mig037_registry_read_v1",
                        "values": values,
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

    def test_bounded_window_covers_mig042_through_mig050(self):
        self.assertEqual(command_port.P1_MIGRATION_REGISTRY_IDS, EXPECTED_WINDOW)

    def test_read_preserves_canonical_read_all_then_recovers_bounded_entries(self):
        calls, rows, request_fn = self._request_fn()
        result = command_port.read_en2_p1_migration_registry_v1("gh-issue-999", request_fn=request_fn)
        present_ids = ("MIG-042", "MIG-043", "MIG-044")
        self.assertEqual(result["execution_class"], "read_only")
        self.assertEqual(result["entries"], [rows[mid] for mid in present_ids])
        self.assertEqual(result["template"], "en033_m1_mig037_registry_read_all_v1")
        self.assertEqual(result["entry_template"], "en033_m1_mig037_registry_read_v1")
        self.assertEqual(result["read_all_transport"], "SANITIZER_TRUNCATED_BOUNDED_FALLBACK")
        self.assertEqual(result["database_profile"], "business")
        self.assertEqual(result["latest_migration"], "MIG-044")
        self.assertEqual(result["migration_presence"]["MIG-042"], True)
        self.assertEqual(result["migration_presence"]["MIG-043"], True)
        self.assertEqual(result["missing_migration_ids"], list(EXPECTED_WINDOW[3:]))
        self.assertFalse(result["business_rows_emitted"])
        self.assertFalse(result["external_action_allowed"])
        self.assertEqual([call["operation"] for call in calls], ["prepare_procedure", "start_run"])

    def test_unparseable_canonical_read_all_uses_bounded_fallback(self):
        _, _, request_fn = self._request_fn(read_all_raw='[{"migration_id":"MIG-001"}')
        result = command_port.read_en2_p1_migration_registry_v1("gh-issue-999", request_fn=request_fn)
        self.assertEqual(result["read_all_transport"], "UNPARSEABLE_BOUNDED_FALLBACK")
        self.assertEqual(result["latest_migration"], "MIG-044")
        self.assertTrue(result["migration_presence"]["MIG-042"])
        self.assertTrue(result["migration_presence"]["MIG-043"])

    def test_bounded_entry_identity_mismatch_fails_closed(self):
        _, rows, request_fn = self._request_fn(wrong_id=True)
        rows["MIG-046"] = {"migration_id": "MIG-046", "state": "NOT_STARTED"}
        with self.assertRaisesRegex(command_port.CommandPortError, "broker_p1_registry_entry_identity_mismatch"):
            command_port.read_en2_p1_migration_registry_v1("gh-issue-999", request_fn=request_fn)


if __name__ == "__main__":
    unittest.main(verbosity=2)
