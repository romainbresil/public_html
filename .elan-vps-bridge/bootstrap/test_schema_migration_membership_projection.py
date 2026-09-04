#!/usr/bin/env python3
import hashlib
import json
import pathlib
import sys
import unittest

BOOTSTRAP = pathlib.Path(__file__).resolve().parent
if str(BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(BOOTSTRAP))

import command_port  # noqa: E402
import issue_inbox  # noqa: E402


REQUESTED_IDS = [
    "EN033_M1_MIG042_001",
    "EN033_M1_MIG042_002",
]
EVIDENCE_CONTRACT = "schema_migration_membership_v1"


def canonical_sha256(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SchemaMigrationMembershipProjectionTest(unittest.TestCase):
    def _request_fn(self, *, extra_source_field=False, missing_second=False):
        calls = []
        values = []
        for index in range(1, 19):
            if index == 7:
                migration_id = REQUESTED_IDS[0]
                description = "MIG-042 editorial schema/calendar"
                applied_at = "2026-08-31T10:00:00+00:00"
            elif index == 8:
                migration_id = REQUESTED_IDS[1]
                description = "MIG-042 EXP-009 import"
                applied_at = "2026-08-31T10:05:00+00:00"
                if missing_second:
                    migration_id = "EN033_M1_OTHER_008"
            else:
                migration_id = f"EN033_M1_OTHER_{index:03d}"
                description = f"other migration {index}"
                applied_at = f"2026-08-30T{index:02d}:00:00+00:00"
            row = {
                "kind": "migration",
                "migration_id": migration_id,
                "description": description,
                "applied_at": applied_at,
            }
            if extra_source_field and index == 7:
                row["not_allowlisted"] = "must fail closed"
            values.append(json.dumps(row, sort_keys=True))

        def request_fn(payload):
            calls.append(payload)
            if payload["operation"] == "prepare_procedure":
                step = payload["procedure"]["steps"][0]
                self.assertEqual(step["primitive"], "postgres_query_template")
                self.assertEqual(step["args"], {
                    "profile": "business",
                    "template": "en029_m6_schema_migrations_v1",
                    "parameters": [],
                })
                return {"plan": {
                    "risk": "read_only",
                    "plan_id": "membership-plan",
                    "execution_token": "token",
                    "procedure_sha256": "procedure-sha",
                }}
            return {"receipt": {
                "status": "succeeded",
                "execution_class": "read_only",
                "run_id": "run-membership",
                "replayed": False,
                "steps": [{
                    "step_id": "read-en-core-status-source",
                    "status": "success",
                    "result": {
                        "template": "en029_m6_schema_migrations_v1",
                        "rows": 18,
                        "sha256": "raw-result-sha256",
                        "values": values,
                    },
                }],
            }}

        return calls, request_fn

    def test_red_detailed_rows_are_projected_only_for_requested_ids(self):
        calls, request_fn = self._request_fn()
        result = command_port.read_en_core_status_v1(
            "gh-issue-999",
            request_fn=request_fn,
            evidence_contract=EVIDENCE_CONTRACT,
            requested_ids=REQUESTED_IDS,
        )
        self.assertEqual(result["evidence_contract"], EVIDENCE_CONTRACT)
        self.assertEqual(result["requested_ids"], REQUESTED_IDS)
        self.assertEqual([row["migration_id"] for row in result["matched_rows"]], REQUESTED_IDS)
        self.assertEqual(result["missing_ids"], [])
        self.assertEqual(result["rows"], 18)
        self.assertEqual(result["sha256"], "raw-result-sha256")
        self.assertEqual(result["database_profile"], "business")
        self.assertEqual(result["surface"], "elan_naturel.schema_migrations")
        self.assertFalse(result["free_sql"])
        self.assertNotIn("values", result)
        self.assertEqual(set(result["matched_rows"][0]), {"migration_id", "description", "applied_at"})
        self.assertEqual([call["operation"] for call in calls], ["prepare_procedure", "start_run"])

        covered = dict(result)
        receipt_sha256 = covered.pop("receipt_sha256")
        self.assertEqual(receipt_sha256, canonical_sha256(covered))

    def test_missing_id_is_reported_separately(self):
        _, request_fn = self._request_fn(missing_second=True)
        result = command_port.read_en_core_status_v1(
            "gh-issue-999",
            request_fn=request_fn,
            evidence_contract=EVIDENCE_CONTRACT,
            requested_ids=REQUESTED_IDS,
        )
        self.assertEqual([row["migration_id"] for row in result["matched_rows"]], [REQUESTED_IDS[0]])
        self.assertEqual(result["missing_ids"], [REQUESTED_IDS[1]])

    def test_unexpected_source_field_fails_closed(self):
        _, request_fn = self._request_fn(extra_source_field=True)
        with self.assertRaisesRegex(command_port.CommandPortError, "schema_migration_evidence_source_contract_invalid"):
            command_port.read_en_core_status_v1(
                "gh-issue-999",
                request_fn=request_fn,
                evidence_contract=EVIDENCE_CONTRACT,
                requested_ids=REQUESTED_IDS,
            )

    def test_issue_contract_is_exact_and_rejects_broader_requests(self):
        good = {
            "number": 999,
            "title": "EN-INTENT — bounded schema migration membership",
            "body": json.dumps({
                "intent_code": "EN_CORE_STATUS_READ",
                "context": {
                    "target": "en-core",
                    "evidence_contract": EVIDENCE_CONTRACT,
                    "requested_ids": REQUESTED_IDS,
                },
            }),
            "user": {"login": issue_inbox.ISSUE_AUTHOR},
        }
        parsed = issue_inbox.parse_issue_intent(good)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["context"]["requested_ids"], REQUESTED_IDS)

        too_many = dict(good)
        too_many["body"] = json.dumps({
            "intent_code": "EN_CORE_STATUS_READ",
            "context": {
                "target": "en-core",
                "evidence_contract": EVIDENCE_CONTRACT,
                "requested_ids": REQUESTED_IDS + ["EN033_M1_MIG043_001"],
            },
        })
        self.assertIsNone(issue_inbox.parse_issue_intent(too_many))

        extra_field = dict(good)
        extra_field["body"] = json.dumps({
            "intent_code": "EN_CORE_STATUS_READ",
            "context": {
                "target": "en-core",
                "evidence_contract": EVIDENCE_CONTRACT,
                "requested_ids": REQUESTED_IDS,
                "sql": "select 1",
            },
        })
        self.assertIsNone(issue_inbox.parse_issue_intent(extra_field))

    def test_legacy_status_read_remains_summary_compatible(self):
        _, request_fn = self._request_fn()
        result = command_port.read_en_core_status_v1("gh-issue-999", request_fn=request_fn)
        self.assertEqual(set(result), {
            "status",
            "execution_class",
            "template",
            "rows",
            "sha256",
            "latest_migration",
            "run_id",
            "replayed",
        })
        self.assertNotIn("matched_rows", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
