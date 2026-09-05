#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import unittest
from unittest import mock

BOOTSTRAP = pathlib.Path(__file__).resolve().parent
if str(BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(BOOTSTRAP))

import command_port  # noqa: E402
import issue_inbox  # noqa: E402

INTENT = "MIG045_GATE12B_TECHNICAL_MATERIALIZE_V1"
TARGET = "mig045-gate12b-technical-materialize"
A_HEAD = "b8a5672d090fb0ddceb552e5029cf04b736da44d"
TARGET_VERSION = "1.3.52"
TRANSPORT_SHA256 = "9fcdc39f7e963b5b352384814130d25d51277b9ba2978970faa7e3e5df531597"
TRANSPORT_SIZE = 187942520
EXPECTED_MIGRATION = "EN033_M1_MIG045_GATE12B_PROOF_LEDGER_V1"
RESOURCE_LOCK = "postgres-business-en033-mig045-gate12b"
GOOD_URL = (
    "https://sdmntprnortheu.oaiusercontent.com/files/qualified-v1352.zip/raw"
    "?sp=r&se=2026-09-06T01%3A00%3A00Z&sig=test-signature"
)
MIGRATION_RELATIVE_PATH = (
    ".elan-vps-bridge/packages/mig045-gate12b/"
    "20260905_en033_m1_mig045_gate12b_proof_ledger.sql"
)
ROLLBACK_RELATIVE_PATH = (
    ".elan-vps-bridge/packages/mig045-gate12b/"
    "20260905_en033_m1_mig045_gate12b_proof_ledger.rollback.sql"
)
REPO_ROOT = BOOTSTRAP.parent.parent
MIGRATION_PATH = REPO_ROOT / "packages/mig045-gate12b/20260905_en033_m1_mig045_gate12b_proof_ledger.sql"
ROLLBACK_PATH = REPO_ROOT / "packages/mig045-gate12b/20260905_en033_m1_mig045_gate12b_proof_ledger.rollback.sql"


def issue(context: dict) -> dict:
    return {
        "number": 1201,
        "title": "EN-INTENT — MIG045 Gate12B technical materialization",
        "body": json.dumps({"intent_code": INTENT, "context": context}),
        "user": {"login": issue_inbox.ISSUE_AUTHOR},
    }


class Gate12BTechnicalMaterializationStaticContractTests(unittest.TestCase):
    def test_owner_backed_constants_and_package_hashes_are_exact(self):
        expected = {
            "MIG045_GATE12B_TECHNICAL_TARGET_VERSION": TARGET_VERSION,
            "MIG045_GATE12B_TECHNICAL_SOURCE_COMMIT": A_HEAD,
            "MIG045_GATE12B_TRANSPORT_SHA256": TRANSPORT_SHA256,
            "MIG045_GATE12B_TRANSPORT_SIZE": TRANSPORT_SIZE,
            "MIG045_GATE12B_EXPECTED_MIGRATION": EXPECTED_MIGRATION,
            "MIG045_GATE12B_MIGRATION_PATH": MIGRATION_RELATIVE_PATH,
            "MIG045_GATE12B_ROLLBACK_PATH": ROLLBACK_RELATIVE_PATH,
        }
        for name, value in expected.items():
            self.assertEqual(getattr(command_port, name, None), value, name)
        migration_sha = hashlib.sha256(MIGRATION_PATH.read_bytes()).hexdigest()
        rollback_sha = hashlib.sha256(ROLLBACK_PATH.read_bytes()).hexdigest()
        self.assertEqual(getattr(command_port, "MIG045_GATE12B_MIGRATION_SHA256", None), migration_sha)
        self.assertEqual(getattr(command_port, "MIG045_GATE12B_ROLLBACK_SHA256", None), rollback_sha)

    def test_new_intent_is_distinct_from_all_existing_mig045_intents(self):
        self.assertEqual(
            getattr(issue_inbox, "MIG045_GATE12B_TECHNICAL_MATERIALIZE_INTENT", None),
            INTENT,
        )
        self.assertNotEqual(INTENT, issue_inbox.MIG045_V1351_INTENT)
        self.assertNotEqual(INTENT, issue_inbox.MIG045_GATE12B_INTENT)
        self.assertNotEqual(INTENT, issue_inbox.MIG045_GATE12B_PREFLIGHT_INTENT)


class Gate12BTechnicalMaterializationMailboxTests(unittest.TestCase):
    def test_exact_context_only_and_artifact_url_required(self):
        parsed = issue_inbox.parse_issue_intent(
            issue({"target": TARGET, "artifact_url": GOOD_URL})
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["intent_code"], INTENT)
        self.assertEqual(parsed["context"], {"target": TARGET, "artifact_url": GOOD_URL})
        self.assertIsNone(issue_inbox.parse_issue_intent(issue({"target": TARGET})))
        self.assertIsNone(issue_inbox.parse_issue_intent(issue({"artifact_url": GOOD_URL})))

    def test_caller_cannot_override_owner_backed_materialization_controls(self):
        forbidden = {
            "version": TARGET_VERSION,
            "source_commit": A_HEAD,
            "transport_sha256": TRANSPORT_SHA256,
            "transport_size": TRANSPORT_SIZE,
            "migration_id": EXPECTED_MIGRATION,
            "migration_sha256": "0" * 64,
            "rollback_sha256": "1" * 64,
            "execution_class": "mutating_technical_change",
            "sql": "SELECT 1",
        }
        for field, value in forbidden.items():
            with self.subTest(field=field):
                context = {"target": TARGET, "artifact_url": GOOD_URL, field: value}
                self.assertIsNone(issue_inbox.parse_issue_intent(issue(context)))

    def test_gate12b_url_validator_requires_signed_read_only_raw_oai_url(self):
        validator = getattr(command_port, "validate_mig045_gate12b_technical_artifact_url", None)
        self.assertTrue(callable(validator))
        self.assertEqual(validator(GOOD_URL), GOOD_URL)
        bad_urls = (
            "http://sdmntprnortheu.oaiusercontent.com/files/a/raw?sp=r&se=x&sig=y",
            "https://example.com/files/a/raw?sp=r&se=x&sig=y",
            "https://sdmntprnortheu.oaiusercontent.com/files/a?sp=r&se=x&sig=y",
            "https://sdmntprnortheu.oaiusercontent.com/files/a/raw?sp=w&se=x&sig=y",
            "https://sdmntprnortheu.oaiusercontent.com/files/a/raw?sp=r&sig=y",
            "https://sdmntprnortheu.oaiusercontent.com/files/a/raw?sp=r&se=x",
            "https://sdmntprnortheu.oaiusercontent.com/files/a/raw?sp=r&se=x&sig=y#fragment",
        )
        for value in bad_urls:
            with self.subTest(url=value):
                with self.assertRaises(command_port.CommandPortError):
                    validator(value)


class Gate12BTechnicalMaterializationExecutionTests(unittest.TestCase):
    def test_exact_bounded_broker_sequence_and_result_contract(self):
        run = getattr(command_port, "run_mig045_gate12b_technical_materialization_v1", None)
        self.assertTrue(callable(run))
        migration_bytes = MIGRATION_PATH.read_bytes()
        rollback_bytes = ROLLBACK_PATH.read_bytes()
        migration_sha = hashlib.sha256(migration_bytes).hexdigest()
        rollback_sha = hashlib.sha256(rollback_bytes).hexdigest()
        events: list[str] = []
        prepared: list[dict] = []

        def fetch_fn(path: str) -> bytes:
            if path == MIGRATION_RELATIVE_PATH:
                return migration_bytes
            if path == ROLLBACK_RELATIVE_PATH:
                return rollback_bytes
            self.fail(path)

        def request_fn(payload: dict) -> dict:
            operation = payload["operation"]
            events.append(operation)
            if operation == "stage_https":
                self.assertEqual(
                    payload,
                    {
                        "operation": "stage_https",
                        "url": GOOD_URL,
                        "expected_sha256": TRANSPORT_SHA256,
                        "expected_size_bytes": TRANSPORT_SIZE,
                        "media_type": "application/zip",
                        "label": "qualified-connector-transfer:elan-vps-1.3.52",
                    },
                )
                return {"artifact": {"artifact_id": "release-artifact"}}
            if operation == "stage_text":
                if payload["label"].startswith("mig045-gate12b-migration-"):
                    self.assertEqual(payload["content"], migration_bytes.decode("utf-8"))
                    self.assertEqual(payload["expected_sha256"], migration_sha)
                    self.assertEqual(payload["media_type"], "text/plain")
                    return {"artifact_id": "migration-artifact"}
                if payload["label"].startswith("mig045-gate12b-rollback-"):
                    self.assertEqual(payload["content"], rollback_bytes.decode("utf-8"))
                    self.assertEqual(payload["expected_sha256"], rollback_sha)
                    self.assertEqual(payload["media_type"], "text/plain")
                    return {"artifact_id": "rollback-artifact"}
                self.fail(payload)
            if operation == "prepare_procedure":
                prepared.append(payload)
                index = len(prepared)
                if index == 1:
                    steps = payload["procedure"]["steps"]
                    self.assertEqual(
                        [step["primitive"] for step in steps],
                        ["postgres_migration_preflight", "postgres_migration_apply"],
                    )
                    self.assertEqual(len(steps), 2)
                    self.assertEqual(steps[0]["args"], {
                        "profile": "business",
                        "artifact_id": "migration-artifact",
                        "rollback_artifact_id": "rollback-artifact",
                    })
                    self.assertEqual(steps[1]["args"], {
                        "profile": "business",
                        "artifact_id": "migration-artifact",
                        "rollback_artifact_id": "rollback-artifact",
                        "expected_migration": EXPECTED_MIGRATION,
                    })
                    self.assertTrue(all(step["resource_lock"] == RESOURCE_LOCK for step in steps))
                    forbidden_primitives = {
                        "postgres_command_template",
                        "postgres_query_template",
                        "gate12b_technical_preflight",
                    }
                    self.assertTrue(forbidden_primitives.isdisjoint({step["primitive"] for step in steps}))
                    return {"plan": {
                        "risk": "reversible_technical_change",
                        "plan_id": "migration-plan",
                        "execution_token": "migration-token",
                        "procedure_sha256": "a" * 64,
                    }}
                self.assertEqual(index, 2)
                steps = payload["procedure"]["steps"]
                self.assertEqual(len(steps), 1)
                self.assertEqual(steps[0]["primitive"], "qualified_release_install")
                self.assertEqual(steps[0]["args"], {
                    "artifact_id": "release-artifact",
                    "expected_version": TARGET_VERSION,
                    "expected_source_commit": A_HEAD,
                })
                self.assertEqual(steps[0]["resource_lock"], "qualified-release")
                return {"plan": {
                    "risk": "reversible_technical_change",
                    "plan_id": "release-plan",
                    "execution_token": "release-token",
                    "procedure_sha256": "b" * 64,
                }}
            if operation == "start_run" and payload["plan_id"] == "migration-plan":
                self.assertEqual(payload["execution_class"], "reversible_technical_change")
                return {"receipt": {
                    "status": "succeeded",
                    "execution_class": "reversible_technical_change",
                    "run_id": "migration-run",
                    "steps": [
                        {"step_id": "preflight", "status": "success", "result": {
                            "free_sql": False,
                            "rollback_present": True,
                        }},
                        {"step_id": "apply", "status": "success", "result": {
                            "artifact_sha256": migration_sha,
                            "migration_id": EXPECTED_MIGRATION,
                        }},
                    ],
                }}
            if operation == "start_run" and payload["plan_id"] == "release-plan":
                self.assertEqual(payload["execution_class"], "reversible_technical_change")
                return {"receipt": {
                    "status": "succeeded",
                    "execution_class": "reversible_technical_change",
                    "run_id": "release-run",
                    "steps": [{
                        "step_id": "qualified-release-install",
                        "status": "success",
                        "result": {"version": TARGET_VERSION},
                    }],
                }}
            self.fail(payload)

        def ready_fn() -> dict:
            events.append("readyz")
            return {"status": "ready", "version": TARGET_VERSION, "source_commit": A_HEAD}

        result = run(
            "gh-issue-1201",
            GOOD_URL,
            request_fn=request_fn,
            fetch_fn=fetch_fn,
            ready_fn=ready_fn,
        )
        self.assertEqual(events, [
            "stage_https",
            "stage_text",
            "stage_text",
            "prepare_procedure",
            "start_run",
            "prepare_procedure",
            "start_run",
            "readyz",
        ])
        self.assertEqual(set(result), {
            "status",
            "migration_id",
            "migration_run_id",
            "release_run_id",
            "target_version",
            "source_commit",
            "transport_sha256",
            "transport_size",
            "migration_sha256",
            "rollback_sha256",
            "ready_proof",
        })
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["migration_id"], EXPECTED_MIGRATION)
        self.assertEqual(result["migration_run_id"], "migration-run")
        self.assertEqual(result["release_run_id"], "release-run")
        self.assertEqual(result["target_version"], TARGET_VERSION)
        self.assertEqual(result["source_commit"], A_HEAD)
        self.assertEqual(result["transport_sha256"], TRANSPORT_SHA256)
        self.assertEqual(result["transport_size"], TRANSPORT_SIZE)
        self.assertEqual(result["migration_sha256"], migration_sha)
        self.assertEqual(result["rollback_sha256"], rollback_sha)
        for forbidden in ("fresh_read", "business", "proof_id", "proof_contract", "technical_preflight"):
            self.assertNotIn(forbidden, result)

    def test_package_hash_mismatch_fails_closed_before_postgres_or_release(self):
        run = getattr(command_port, "run_mig045_gate12b_technical_materialization_v1", None)
        self.assertTrue(callable(run))
        events = []

        def request_fn(payload: dict) -> dict:
            events.append(payload["operation"])
            if payload["operation"] == "stage_https":
                return {"artifact_id": "release-artifact"}
            self.fail(payload)

        def fetch_fn(path: str) -> bytes:
            if path == MIGRATION_RELATIVE_PATH:
                return b"tampered\n"
            return ROLLBACK_PATH.read_bytes()

        with self.assertRaisesRegex(command_port.CommandPortError, "migration_sha256"):
            run("gh-issue-1202", GOOD_URL, request_fn=request_fn, fetch_fn=fetch_fn)
        self.assertEqual(events, ["stage_https"])

    def test_readyz_requires_v1352_ready_status_and_checks_source_when_exposed(self):
        validator = getattr(command_port, "_validate_mig045_gate12b_technical_ready_proof", None)
        self.assertTrue(callable(validator))
        self.assertEqual(
            validator({"status": "ready", "version": TARGET_VERSION}),
            {"status": "ready", "version": TARGET_VERSION},
        )
        self.assertEqual(
            validator({"status": "ok", "version": TARGET_VERSION, "source_commit": A_HEAD}),
            {"status": "ok", "version": TARGET_VERSION, "source_commit": A_HEAD},
        )
        invalid = (
            {"status": "ready", "version": "1.3.51"},
            {"status": "down", "version": TARGET_VERSION},
            {"status": "ready", "version": TARGET_VERSION, "source_commit": "0" * 40},
            {"status": "ready", "version": TARGET_VERSION, "runtime_source_commit": "0" * 40},
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(command_port.CommandPortError):
                    validator(value)


class Gate12BTechnicalMaterializationIsolationTests(unittest.TestCase):
    def test_dispatch_calls_only_new_owner_and_never_other_mig045_paths(self):
        job = issue_inbox.parse_issue_intent(issue({"target": TARGET, "artifact_url": GOOD_URL}))
        self.assertIsNotNone(job)
        receipt = {
            "status": "succeeded",
            "migration_id": EXPECTED_MIGRATION,
            "migration_run_id": "m-run",
            "release_run_id": "r-run",
            "target_version": TARGET_VERSION,
            "source_commit": A_HEAD,
            "transport_sha256": TRANSPORT_SHA256,
            "transport_size": TRANSPORT_SIZE,
            "migration_sha256": "1" * 64,
            "rollback_sha256": "2" * 64,
            "ready_proof": {"status": "ready", "version": TARGET_VERSION},
        }
        owner = getattr(issue_inbox.command_port, "run_mig045_gate12b_technical_materialization_v1", None)
        self.assertTrue(callable(owner))
        with mock.patch.object(
            issue_inbox.command_port,
            "run_mig045_gate12b_technical_materialization_v1",
            return_value=receipt,
        ) as new_run, mock.patch.object(
            issue_inbox.command_port,
            "run_mig045_v1351_rollout_and_fresh_read_v1",
        ) as old_run, mock.patch.object(
            issue_inbox.command_port,
            "run_mig045_gate12b_committed_proof_v1",
        ) as proof_run, mock.patch.object(
            issue_inbox.command_port,
            "request_mig045_gate12b_production_proof_freeze",
        ) as preflight_run:
            result = issue_inbox._execute_job(job)
        self.assertEqual(result["state"], "COMPLETED")
        self.assertEqual(result["result"]["migration_id"], EXPECTED_MIGRATION)
        new_run.assert_called_once_with(job["id"], GOOD_URL)
        old_run.assert_not_called()
        proof_run.assert_not_called()
        preflight_run.assert_not_called()

    def test_materialization_failure_is_failed_without_fallback(self):
        job = issue_inbox.parse_issue_intent(issue({"target": TARGET, "artifact_url": GOOD_URL}))
        self.assertIsNotNone(job)
        with mock.patch.object(
            issue_inbox.command_port,
            "run_mig045_gate12b_technical_materialization_v1",
            side_effect=command_port.CommandPortError("materialization_failed"),
        ) as new_run, mock.patch.object(
            issue_inbox.command_port,
            "run_mig045_v1351_rollout_and_fresh_read_v1",
        ) as old_run, mock.patch.object(
            issue_inbox.command_port,
            "run_mig045_gate12b_committed_proof_v1",
        ) as proof_run, mock.patch.object(
            issue_inbox.command_port,
            "request_mig045_gate12b_production_proof_freeze",
        ) as preflight_run:
            result = issue_inbox._execute_job(job)
        self.assertEqual(result["state"], "FAILED")
        self.assertIn("materialization_failed", result["result"]["stderr"])
        new_run.assert_called_once()
        old_run.assert_not_called()
        proof_run.assert_not_called()
        preflight_run.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
