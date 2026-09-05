#!/usr/bin/env python3
import copy
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

BOOTSTRAP = pathlib.Path(__file__).resolve().parent
if str(BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(BOOTSTRAP))

import bridge_worker  # noqa: E402
import command_port  # noqa: E402
import issue_inbox  # noqa: E402


INTENT = "MIG045_GATE12B_COMMITTED_PROOF_V1"
OLD_INTENT = "MIG045_V1351_ROLLOUT_AND_FRESH_READ"
TARGET = "mig045-gate12b-committed-proof"
TEMPLATE = "en033_m1_mig045_gate12b_committed_proof_v1"
OBSERVATION_SEMANTICS = "COMMITTED_PROOF_TRANSACTION_V1"
PROOF_ID_DOMAIN = "EN033/M1:MIG045:G12B:COMMITTED_PROOF_TRANSACTION_V1:"
EXPECTED_IDENTITY_SET_SHA256 = "dc731702f983999e083563477216054bfcee5674eff03a5d6ef8cb479b0c2cc1"
CORPUS = [f"CON-{number:03d}" for number in range(20, 28)]

RUNTIME_VERSION = "1.3.52"
RUNTIME_SOURCE_COMMIT = "b8a5672d090fb0ddceb552e5029cf04b736da44d"
CAPABILITY_SHA256 = "b51a4bf09041f42af28b737f868710d5377123eb0747ae4fd6e2fd290a006729"
EFFECTIVE_POLICY_SHA256 = "cc" * 32
COMMAND_TEMPLATE_SHA256 = "6fff7e691aaa4cbc7d3b789e8b111988bc08d2680e911e6298c4d16fcceb123a"
SQL_OWNER_SHA256 = "77c7c90c25f2eefe7827a1c0c469b5a1343ca0646aa9c29d485e3dc1edd2fa25"
TARGET_BINDING_SHA256 = "ff" * 32

DECISION_IDS = {
    "CON-020": 391072,
    "CON-021": 391076,
    "CON-022": 391080,
    "CON-023": 391084,
    "CON-024": 391088,
    "CON-025": 391092,
    "CON-026": 391096,
    "CON-027": 391100,
}
DATES = {
    "CON-020": "2026-08-12",
    "CON-021": "2026-08-14",
    "CON-022": "2026-08-18",
    "CON-023": "2026-08-21",
    "CON-024": "2026-08-25",
    "CON-025": "2026-08-28",
    "CON-026": "2026-09-01",
    "CON-027": "2026-09-04",
}
PLAN_IDS = {
    "CON-020": "6416bcd3-28c3-50a9-9fab-9b62994c9603",
    "CON-021": "fe08fe7a-7e88-58a6-b40d-6c99b3eedbcc",
    "CON-022": "f358ad14-47ec-534e-abe5-e249d8498966",
    "CON-023": "2cd20dfb-a78a-586e-a21c-28b7ed6f7f10",
    "CON-024": "9b3f455b-d8d9-53a8-8f29-60b05642a3fa",
    "CON-025": "9eb9efea-564f-544b-a802-641107701e80",
    "CON-026": "15212ff1-c7a3-5450-b464-cdbd2ed27266",
    "CON-027": "ce1cdaf2-ee35-5cbc-93b1-05e35f4431ab",
}
OCCURRENCE_IDS = {
    "CON-020": "20ef6b3c-6a02-5ebe-bb3b-3054bf88ea90",
    "CON-021": "3115ca79-ba64-531b-9f24-a103e6bec9fd",
    "CON-022": "4c1bdb49-adc5-5dc8-876c-0dfc17754885",
    "CON-023": "63cef0ef-2123-5c9c-9248-50fd9e4f4bd8",
    "CON-024": "bfd57fe9-5b0b-5974-9ce6-8dcc649ca2af",
    "CON-025": "febdea64-2a0c-5ded-a1a6-f62a99334659",
    "CON-026": "81e340dc-1acf-5f29-bd95-11d8afed29e8",
    "CON-027": "57c5bb41-b0e7-59bd-8ab4-d9ceb5c26391",
}


def canonical_bytes(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256(value) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def proof_contract(**overrides):
    value = {
        "observation_semantics": OBSERVATION_SEMANTICS,
        "expected_identity_set_sha256": EXPECTED_IDENTITY_SET_SHA256,
        "corpus": list(CORPUS),
        "runtime_version": RUNTIME_VERSION,
        "runtime_source_commit": RUNTIME_SOURCE_COMMIT,
        "capability_sha256": CAPABILITY_SHA256,
        "effective_policy_sha256": EFFECTIVE_POLICY_SHA256,
        "command_template_sha256": COMMAND_TEMPLATE_SHA256,
        "sql_owner_sha256": SQL_OWNER_SHA256,
        "target_binding_sha256": TARGET_BINDING_SHA256,
    }
    value.update(overrides)
    return value


def expected_proof_id(contract_sha256: str) -> str:
    return hashlib.sha256((PROOF_ID_DOMAIN + contract_sha256).encode("utf-8")).hexdigest()


def context(contract=None, *, asserted_contract_sha=None, asserted_proof_id=None):
    contract = proof_contract() if contract is None else contract
    contract_sha = sha256(contract) if asserted_contract_sha is None else asserted_contract_sha
    proof_id = expected_proof_id(contract_sha) if asserted_proof_id is None else asserted_proof_id
    return {
        "target": TARGET,
        "proof_contract": contract,
        "proof_contract_sha256": contract_sha,
        "proof_id": proof_id,
    }


def issue(number: int, ctx=None):
    return {
        "number": number,
        "title": "EN-INTENT — MIG045 Gate12B committed proof",
        "body": json.dumps({"intent_code": INTENT, "context": context() if ctx is None else ctx}),
        "user": {"login": issue_inbox.ISSUE_AUTHOR},
        "html_url": f"https://github.com/romainbresil/public_html/issues/{number}",
    }


def preflight_for(contract=None):
    contract = proof_contract() if contract is None else contract
    return {
        key: contract[key]
        for key in (
            "runtime_version",
            "runtime_source_commit",
            "capability_sha256",
            "effective_policy_sha256",
            "command_template_sha256",
            "sql_owner_sha256",
            "target_binding_sha256",
        )
    }


def expected_identity_result():
    plans = []
    occurrences = []
    for content_id in CORPUS:
        plan_id = PLAN_IDS[content_id]
        plans.append({
            "authorization_decision_ref": DECISION_IDS[content_id],
            "channel": "LinkedIn",
            "content_ref": content_id,
            "plan_id": plan_id,
            "scheduled_on": DATES[content_id],
            "source_payload": {
                "authorization_source": "Programmée manuellement par Romain le 2026-08-11",
                "publication_evidence": False,
                "publication_link": None,
                "source_status": "Programmé dans LinkedIn — exécution à confirmer",
                "time_precision": "date",
            },
        })
        occurrences.append({
            "channel_readback_state": "NOT_OBSERVED",
            "occurrence_id": OCCURRENCE_IDS[content_id],
            "plan_id": plan_id,
            "programmed_on": DATES[content_id],
        })
    return {
        "schema_version": "en033-m1-mig045-gate12b-expected-identity-v1",
        "authorization_authority": {
            "decision_family": "PUBLICATION_AUTHORIZATION",
            "normalized_status": "AUTHORIZED",
            "current_required": True,
            "decision_ids_by_content": dict(DECISION_IDS),
            "owner_path": "docs/en-core-migration/CHECKPOINT-TERMINAL-MIG042-PROD-VALIDATED-2026-08-31.md",
            "owner_ref": "18b12254438573f862861ccd9280dc137f83b051",
            "legacy_sentence_used_to_infer_authorization": False,
        },
        "source_contract": {
            "fixture_path": "en-033/mig042/fixtures/contenus-programmed-con020-con027-2026-08-31.json",
            "fixture_ref": "18b12254438573f862861ccd9280dc137f83b051",
            "source_read": {
                "spreadsheet_id": "1MTgjR38FYMeaZwSk-eULvgSYAbvPm1hoLE_aCvxp7XI",
                "sheet": "Contenus",
                "range": "A1:V28",
                "read_on": "2026-08-31",
                "rule": "PROGRAMMED != PUBLISHED",
            },
            "gate12b_normalization": {
                "authorization_source": "fixture.authorization_evidence (documentary payload only; never authorization authority)",
                "publication_link": "fixture.publication_url",
                "publication_evidence": False,
                "occurrence_programmed_on": "fixture.scheduled_on per active MIG-042 projector",
                "non_projected_fixture_fields": ["title", "programmed_on", "source_updated_on"],
            },
        },
        "plans": sorted(plans, key=lambda item: item["plan_id"]),
        "occurrences": sorted(occurrences, key=lambda item: item["occurrence_id"]),
    }


def persisted_wrapper(*, replayed=False, committed_at="2026-09-05T00:00:00Z", run_id=None):
    contract_sha = sha256(proof_contract())
    wrapper = {
        "proof_id": expected_proof_id(contract_sha),
        "proof_contract_sha256": contract_sha,
        "replayed": replayed,
        "result": expected_identity_result(),
        "committed_at": committed_at,
    }
    if run_id is not None:
        wrapper["run_id"] = run_id
    return wrapper


def succeeded_receipt(input_sha256: str, *, replayed=False, ledger_replayed=False):
    wrapper = persisted_wrapper(replayed=ledger_replayed)
    return {
        "status": "succeeded",
        "execution_class": "mutating_technical_change",
        "run_id": "gate12b-run-identity",
        "replayed": replayed,
        "steps": [{
            "step_id": "mig045-gate12b-committed-proof",
            "status": "success",
            "result": {
                "template": TEMPLATE,
                "mode": "commit",
                "committed": True,
                "input_sha256": input_sha256,
                "command_result": wrapper,
                "verification": {
                    "proof_id": wrapper["proof_id"],
                    "proof_contract_sha256": wrapper["proof_contract_sha256"],
                },
            },
        }],
    }


class FakeBroker:
    def __init__(self, *, ledger_replayed=False):
        self.calls = []
        self.input_sha256 = None
        self.ledger_replayed = ledger_replayed

    def __call__(self, payload: dict) -> dict:
        self.calls.append(payload)
        operation = payload["operation"]
        if operation == "stage_text":
            self.input_sha256 = hashlib.sha256(payload["content"].encode("utf-8")).hexdigest()
            self.assertEqualChecksum(payload)
            return {"artifact": {"artifact_id": "00000000-0000-0000-0000-000000000001"}}
        if operation == "prepare_procedure":
            return {"plan": {
                "risk": "mutating_technical_change",
                "plan_id": "00000000-0000-0000-0000-000000000002",
                "execution_token": "test-execution-token",
                "procedure_sha256": "44" * 32,
                "replayed": False,
                "may_execute_same_turn": True,
            }}
        if operation == "start_run":
            return {"receipt": succeeded_receipt(
                self.input_sha256,
                ledger_replayed=self.ledger_replayed,
            )}
        if operation == "cleanup_artifact":
            return {"result": {"artifact_id": payload["artifact_id"], "removed": True}}
        raise AssertionError(payload)

    def assertEqualChecksum(self, payload):
        if payload["expected_sha256"] != self.input_sha256:
            raise AssertionError("stage checksum mismatch")


class Gate12BCanonicalProofContractTests(unittest.TestCase):
    def test_owner_fixture_hash_is_the_frozen_expected_identity_hash(self):
        self.assertEqual(sha256(expected_identity_result()), EXPECTED_IDENTITY_SET_SHA256)

    def test_proof_contract_sha256_and_proof_id_use_exact_owner_formula(self):
        contract = proof_contract()
        expected_contract_sha = sha256(contract)
        expected_id = expected_proof_id(expected_contract_sha)
        self.assertEqual(command_port.mig045_gate12b_proof_contract_sha256(contract), expected_contract_sha)
        self.assertEqual(command_port.derive_mig045_gate12b_proof_id(expected_contract_sha), expected_id)
        self.assertRegex(expected_id, r"^[a-f0-9]{64}$")

    def test_arbitrary_caller_proof_id_and_second_id_for_same_contract_are_rejected(self):
        good = context()
        arbitrary = {**good, "proof_id": "11" * 32}
        second = {**good, "proof_id": "22" * 32}
        self.assertIsNotNone(issue_inbox.parse_issue_intent(issue(10, good)))
        self.assertIsNone(issue_inbox.parse_issue_intent(issue(11, arbitrary)))
        self.assertIsNone(issue_inbox.parse_issue_intent(issue(12, second)))

    def test_proof_id_has_no_lossy_normalization_surface(self):
        good = context()
        expected = good["proof_id"]
        for asserted in (
            f" {expected}",
            f"{expected} ",
            expected.upper(),
            expected[:-1],
            expected + "0",
        ):
            self.assertIsNone(issue_inbox.parse_issue_intent(issue(20, {**good, "proof_id": asserted})))
        self.assertEqual(command_port.derive_mig045_gate12b_proof_id(good["proof_contract_sha256"]), expected)

    def test_closed_context_rejects_contract_sha_mismatch_and_extra_keys(self):
        good = context()
        changed = copy.deepcopy(good)
        changed["proof_contract"]["runtime_version"] = "9.9.9"
        self.assertIsNone(issue_inbox.parse_issue_intent(issue(30, changed)))
        self.assertIsNone(issue_inbox.parse_issue_intent(issue(31, {**good, "extra": "no"})))

    def test_two_issues_same_contract_have_different_transport_id_but_same_logical_proof(self):
        first = issue_inbox.parse_issue_intent(issue(101))
        second = issue_inbox.parse_issue_intent(issue(202))
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(first["id"], "gh-issue-101")
        self.assertEqual(second["id"], "gh-issue-202")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["context"]["proof_id"], second["context"]["proof_id"])
        self.assertEqual(first["context"]["proof_id"], expected_proof_id(sha256(proof_contract())))

    def test_command_port_uses_exact_proof_id_as_broker_and_postgres_identity(self):
        broker = FakeBroker()
        contract = proof_contract()
        contract_sha = sha256(contract)
        proof_id = expected_proof_id(contract_sha)
        with tempfile.TemporaryDirectory() as tmp:
            result = command_port.run_mig045_gate12b_committed_proof_v1(
                contract,
                contract_sha,
                proof_id,
                request_fn=broker,
                preflight_fn=lambda: preflight_for(contract),
                state_root=pathlib.Path(tmp),
            )
        stage = next(call for call in broker.calls if call["operation"] == "stage_text")
        prepare = next(call for call in broker.calls if call["operation"] == "prepare_procedure")
        self.assertEqual(prepare["idempotency_key"], proof_id)
        self.assertEqual(prepare["procedure"]["procedure_id"], proof_id)
        self.assertNotIn("gh-issue", json.dumps(prepare, sort_keys=True))
        self.assertNotIn("_safe_key", json.dumps(prepare, sort_keys=True))
        staged_payload = json.loads(stage["content"])
        self.assertEqual(staged_payload, {
            "proof_id": proof_id,
            "proof_contract_sha256": contract_sha,
        })
        self.assertEqual(result["proof_id"], proof_id)
        self.assertEqual(result["broker_idempotency_key"], proof_id)
        self.assertEqual(result["postgres_proof_id"], proof_id)

    def test_same_proof_id_with_changed_contract_fails_before_broker(self):
        contract = proof_contract()
        contract_sha = sha256(contract)
        proof_id = expected_proof_id(contract_sha)
        changed = proof_contract(runtime_version="9.9.9")
        changed_sha = sha256(changed)

        def forbidden_request(_payload):
            raise AssertionError("contract collision must fail before broker")

        with self.assertRaisesRegex(command_port.CommandPortError, "static_binding_mismatch|proof_id_mismatch"):
            command_port.run_mig045_gate12b_committed_proof_v1(
                changed,
                changed_sha,
                proof_id,
                request_fn=forbidden_request,
                preflight_fn=lambda: preflight_for(changed),
                state_root=pathlib.Path("unused"),
            )


class Gate12BPreflightTests(unittest.TestCase):
    def test_missing_runtime_preflight_owner_fails_closed_before_broker(self):
        ctx = context()

        def unavailable_preflight(payload):
            self.assertEqual(payload, {"operation": "gate12b_technical_preflight"})
            raise command_port.CommandPortError("broker_unavailable")

        with self.assertRaisesRegex(command_port.CommandPortError, "broker_unavailable"):
            command_port.run_mig045_gate12b_committed_proof_v1(
                ctx["proof_contract"],
                ctx["proof_contract_sha256"],
                ctx["proof_id"],
                request_fn=unavailable_preflight,
                state_root=pathlib.Path("unused"),
            )

    def test_any_preflight_binding_drift_fails_closed_before_broker(self):
        for field in preflight_for():
            actual = preflight_for()
            actual[field] = "drift"

            def forbidden_request(_payload):
                raise AssertionError(f"broker reached despite preflight drift: {field}")

            ctx = context()
            with self.assertRaisesRegex(command_port.CommandPortError, "preflight_binding_mismatch"):
                command_port.run_mig045_gate12b_committed_proof_v1(
                    ctx["proof_contract"],
                    ctx["proof_contract_sha256"],
                    ctx["proof_id"],
                    request_fn=forbidden_request,
                    preflight_fn=lambda actual=actual: actual,
                    state_root=pathlib.Path("unused"),
                )


class Gate12BReplayAndResultTests(unittest.TestCase):
    def test_commit_receipt_loss_retry_reaches_same_canonical_primitive_and_ledger_replay(self):
        contract = proof_contract()
        contract_sha = sha256(contract)
        proof_id = expected_proof_id(contract_sha)

        class ReceiptLossBroker(FakeBroker):
            def __call__(self, payload: dict) -> dict:
                if payload["operation"] == "start_run":
                    self.calls.append(payload)
                    raise command_port.CommandPortError("broker_unavailable")
                return super().__call__(payload)

        first_broker = ReceiptLossBroker()
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            with self.assertRaisesRegex(command_port.CommandPortError, "broker_unavailable"):
                command_port.run_mig045_gate12b_committed_proof_v1(
                    contract,
                    contract_sha,
                    proof_id,
                    request_fn=first_broker,
                    preflight_fn=lambda: preflight_for(contract),
                    state_root=root,
                )

            first_prepare = next(call for call in first_broker.calls if call["operation"] == "prepare_procedure")
            input_sha = next(call for call in first_broker.calls if call["operation"] == "stage_text")["expected_sha256"]
            recovery_calls = []

            def recovery_request(payload: dict) -> dict:
                recovery_calls.append(payload)
                if payload["operation"] == "prepare_procedure":
                    self.assertEqual(payload["idempotency_key"], proof_id)
                    self.assertEqual(payload["procedure"], first_prepare["procedure"])
                    return {"plan": {
                        "risk": "mutating_technical_change",
                        "plan_id": "00000000-0000-0000-0000-000000000002",
                        "execution_token": "rotated-execution-token",
                        "procedure_sha256": "44" * 32,
                        "replayed": True,
                        "may_execute_same_turn": True,
                    }}
                if payload["operation"] == "start_run":
                    return {"receipt": succeeded_receipt(input_sha, replayed=True, ledger_replayed=True)}
                if payload["operation"] == "cleanup_artifact":
                    return {"result": {"artifact_id": payload["artifact_id"], "removed": True}}
                raise AssertionError(payload)

            recovered = command_port.run_mig045_gate12b_committed_proof_v1(
                contract,
                contract_sha,
                proof_id,
                request_fn=recovery_request,
                preflight_fn=lambda: preflight_for(contract),
                state_root=root,
            )

        self.assertEqual(
            [call["operation"] for call in recovery_calls],
            ["prepare_procedure", "start_run", "cleanup_artifact"],
        )
        self.assertEqual(recovered["proof_id"], proof_id)
        self.assertTrue(recovered["ledger_replayed"])
        self.assertTrue(recovered["committed"])
        self.assertEqual(recovered["result_sha256"], EXPECTED_IDENTITY_SET_SHA256)

    def test_existing_issue_claim_does_not_block_incomplete_gate12b_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bridge_worker.create_claim(root, "gh-issue-701", "source-sha")
            gate_issue = issue(701)
            completed = {
                "id": "gh-issue-701",
                "read_token": "x" * 32,
                "intent_code": INTENT,
                "context": context(),
                "state": "COMPLETED",
                "result": {"status": "PASS"},
                "started_at": "start",
                "finished_at": "finish",
            }
            with mock.patch.object(issue_inbox, "_execute_job", return_value=completed) as execute, \
                 mock.patch.object(issue_inbox.bridge_worker, "store_result"), \
                 mock.patch.object(issue_inbox.bridge_worker, "post_result"):
                status = issue_inbox.process_issue(root, gate_issue)
            self.assertEqual(status, "COMPLETED")
            execute.assert_called_once()

    def test_result_hash_is_only_canonical_wrapper_result(self):
        first = persisted_wrapper(
            replayed=False,
            committed_at="2026-09-05T00:00:00Z",
            run_id="transport-run-a",
        )
        second = persisted_wrapper(
            replayed=True,
            committed_at="2099-01-01T00:00:00Z",
            run_id="transport-run-b",
        )
        self.assertNotEqual(sha256(first), EXPECTED_IDENTITY_SET_SHA256)
        self.assertNotEqual(sha256(second), EXPECTED_IDENTITY_SET_SHA256)
        self.assertEqual(command_port.mig045_gate12b_persisted_result_sha256(first), EXPECTED_IDENTITY_SET_SHA256)
        self.assertEqual(command_port.mig045_gate12b_persisted_result_sha256(second), EXPECTED_IDENTITY_SET_SHA256)


class Gate12BOldIntentIsolationTests(unittest.TestCase):
    def test_new_intent_is_distinct_and_failure_never_falls_back_to_old_fresh_read(self):
        self.assertNotEqual(INTENT, OLD_INTENT)
        job = {
            "id": "gh-issue-900",
            "intent_code": INTENT,
            "context": context(),
            "read_token": "r" * 32,
        }
        with mock.patch.object(
            issue_inbox.command_port,
            "run_mig045_gate12b_committed_proof_v1",
            side_effect=command_port.CommandPortError("preflight_binding_mismatch"),
        ) as new_run, mock.patch.object(
            issue_inbox.command_port,
            "run_mig045_v1351_rollout_and_fresh_read_v1",
        ) as old_run:
            result = issue_inbox._execute_job(job)
        self.assertEqual(result["state"], "FAILED")
        self.assertIn("preflight_binding_mismatch", result["result"]["stderr"])
        new_run.assert_called_once()
        old_run.assert_not_called()

    def test_legacy_intent_contract_remains_available(self):
        self.assertEqual(issue_inbox.MIG045_V1351_INTENT, OLD_INTENT)
        self.assertTrue(callable(command_port.run_mig045_v1351_rollout_and_fresh_read_v1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
