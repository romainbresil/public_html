#!/usr/bin/env python3
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

import command_port  # noqa: E402
import issue_inbox  # noqa: E402


INTENT = "MIG045_GATE12B_COMMITTED_PROOF_V1"
TARGET = "mig045-gate12b-committed-proof"
TEMPLATE = "en033_m1_mig045_gate12b_committed_proof_v1"
EXPECTED_IDENTITY_SET_SHA256 = "dc731702f983999e083563477216054bfcee5674eff03a5d6ef8cb479b0c2cc1"
PROOF_ID = "11" * 32
CONTRACT_A = "22" * 32
CONTRACT_B = "33" * 32


def context(*, proof_id=PROOF_ID, proof_contract_sha256=CONTRACT_A, expected=EXPECTED_IDENTITY_SET_SHA256):
    return {
        "target": TARGET,
        "proof_id": proof_id,
        "proof_contract_sha256": proof_contract_sha256,
        "expected_identity_set_sha256": expected,
    }


def issue(number: int, ctx: dict):
    return {
        "number": number,
        "title": "EN-INTENT — MIG045 Gate12B committed proof",
        "body": json.dumps({"intent_code": INTENT, "context": ctx}),
        "user": {"login": issue_inbox.ISSUE_AUTHOR},
        "html_url": f"https://github.com/romainbresil/public_html/issues/{number}",
    }


def succeeded_receipt(input_sha256: str, *, replayed: bool = False):
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
                "command_result": {"outcome": "COMMITTED"},
                "verification": {"status_code": "COMMITTED"},
            },
        }],
    }


class FakeBroker:
    def __init__(self):
        self.calls = []
        self.input_sha256 = None

    def __call__(self, payload: dict) -> dict:
        self.calls.append(payload)
        operation = payload["operation"]
        if operation == "stage_text":
            self.input_sha256 = hashlib.sha256(payload["content"].encode("utf-8")).hexdigest()
            self.assert_stage(payload)
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
            return {"receipt": succeeded_receipt(self.input_sha256)}
        if operation == "cleanup_artifact":
            return {"result": {"artifact_id": payload["artifact_id"], "removed": True}}
        raise AssertionError(payload)

    def assert_stage(self, payload: dict):
        if payload["expected_sha256"] != self.input_sha256:
            raise AssertionError("stage checksum mismatch")


class Gate12BProofIdentityContractTest(unittest.TestCase):
    def test_two_issues_keep_transport_ids_but_preserve_same_proof_id(self):
        first = issue_inbox.parse_issue_intent(issue(101, context()))
        second = issue_inbox.parse_issue_intent(issue(202, context()))
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(first["id"], "gh-issue-101")
        self.assertEqual(second["id"], "gh-issue-202")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["context"]["proof_id"], PROOF_ID)
        self.assertEqual(second["context"]["proof_id"], PROOF_ID)

    def test_gate12b_context_is_closed_and_proof_id_is_lossless_sha256(self):
        self.assertIsNotNone(issue_inbox.parse_issue_intent(issue(1, context())))
        bad_contexts = [
            {k: v for k, v in context().items() if k != "proof_id"},
            context(proof_id=""),
            context(proof_id="AB" * 32),
            context(proof_id="a" * 63),
            context(proof_contract_sha256="A" * 64),
            context(expected="00" * 32),
            {**context(), "target": "other"},
            {**context(), "extra": "not-allowed"},
        ]
        for bad in bad_contexts:
            self.assertIsNone(issue_inbox.parse_issue_intent(issue(2, bad)), bad)

    def test_issue_dispatch_passes_proof_id_not_issue_job_id(self):
        job = issue_inbox.parse_issue_intent(issue(303, context()))
        self.assertIsNotNone(job)
        expected = {
            "proof_id": PROOF_ID,
            "proof_contract_sha256": CONTRACT_A,
            "expected_identity_set_sha256": EXPECTED_IDENTITY_SET_SHA256,
            "broker_template": TEMPLATE,
            "broker_run_id": "run",
            "broker_result_sha256": "55" * 32,
            "committed": True,
            "replayed": False,
            "external_action_allowed": False,
        }
        with mock.patch.object(
            issue_inbox.command_port,
            "run_mig045_gate12b_committed_proof_v1",
            return_value=expected,
        ) as run:
            result = issue_inbox._execute_job(job)
        run.assert_called_once_with(PROOF_ID, CONTRACT_A, EXPECTED_IDENTITY_SET_SHA256)
        self.assertEqual(result["id"], "gh-issue-303")
        self.assertEqual(result["result"]["proof_id"], PROOF_ID)

    def test_command_port_broker_identity_is_proof_id_and_receipt_preserves_bindings(self):
        broker = FakeBroker()
        with tempfile.TemporaryDirectory() as tmp:
            result = command_port.run_mig045_gate12b_committed_proof_v1(
                PROOF_ID,
                CONTRACT_A,
                EXPECTED_IDENTITY_SET_SHA256,
                request_fn=broker,
                state_root=pathlib.Path(tmp),
            )
        stage = next(call for call in broker.calls if call["operation"] == "stage_text")
        prepare = next(call for call in broker.calls if call["operation"] == "prepare_procedure")
        canonical = json.dumps(
            context(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        self.assertEqual(stage["content"], canonical)
        self.assertEqual(stage["expected_sha256"], hashlib.sha256(canonical.encode("utf-8")).hexdigest())
        self.assertEqual(prepare["idempotency_key"], f"mig045-gate12b-proof-{PROOF_ID}")
        self.assertEqual(prepare["procedure"]["procedure_id"], f"mig045-gate12b-proof-{PROOF_ID}")
        self.assertNotIn("gh-issue", json.dumps(prepare, sort_keys=True))
        step = prepare["procedure"]["steps"][0]
        self.assertEqual(step["primitive"], "postgres_command_template")
        self.assertEqual(step["args"]["template"], TEMPLATE)
        self.assertEqual(step["args"]["mode"], "commit")
        self.assertEqual(result["proof_id"], PROOF_ID)
        self.assertEqual(result["proof_contract_sha256"], CONTRACT_A)
        self.assertEqual(result["expected_identity_set_sha256"], EXPECTED_IDENTITY_SET_SHA256)
        self.assertEqual(result["broker_template"], TEMPLATE)
        self.assertEqual(result["broker_run_id"], "gate12b-run-identity")
        self.assertRegex(result["broker_result_sha256"], r"^[a-f0-9]{64}$")
        self.assertTrue(result["committed"])
        self.assertFalse(result["replayed"])

    def test_same_proof_id_second_transport_reuses_committed_execution_without_broker_call(self):
        broker = FakeBroker()
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            first = command_port.run_mig045_gate12b_committed_proof_v1(
                PROOF_ID, CONTRACT_A, EXPECTED_IDENTITY_SET_SHA256,
                request_fn=broker, state_root=root,
            )

            def forbidden_request(_payload):
                raise AssertionError("same proof_id replay must not create another broker execution")

            second = command_port.run_mig045_gate12b_committed_proof_v1(
                PROOF_ID, CONTRACT_A, EXPECTED_IDENTITY_SET_SHA256,
                request_fn=forbidden_request, state_root=root,
            )
        self.assertEqual(second["proof_id"], first["proof_id"])
        self.assertEqual(second["broker_run_id"], first["broker_run_id"])
        self.assertEqual(second["broker_result_sha256"], first["broker_result_sha256"])
        self.assertTrue(second["replayed"])
        self.assertTrue(second["committed"])

    def test_same_proof_id_changed_contract_fails_before_broker(self):
        broker = FakeBroker()
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            command_port.run_mig045_gate12b_committed_proof_v1(
                PROOF_ID, CONTRACT_A, EXPECTED_IDENTITY_SET_SHA256,
                request_fn=broker, state_root=root,
            )

            def forbidden_request(_payload):
                raise AssertionError("binding conflict must fail before broker")

            with self.assertRaisesRegex(command_port.CommandPortError, "proof_binding_conflict"):
                command_port.run_mig045_gate12b_committed_proof_v1(
                    PROOF_ID, CONTRACT_B, EXPECTED_IDENTITY_SET_SHA256,
                    request_fn=forbidden_request, state_root=root,
                )

    def test_restart_after_start_run_receipt_loss_recovers_existing_run(self):
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
                    PROOF_ID, CONTRACT_A, EXPECTED_IDENTITY_SET_SHA256,
                    request_fn=first_broker, state_root=root,
                )
            stage = next(call for call in first_broker.calls if call["operation"] == "stage_text")
            input_sha256 = stage["expected_sha256"]
            recovery_calls = []

            def recovery_request(payload: dict) -> dict:
                recovery_calls.append(payload)
                if payload["operation"] == "get_run":
                    return {"receipt": succeeded_receipt(input_sha256, replayed=True)}
                if payload["operation"] == "cleanup_artifact":
                    return {"result": {"artifact_id": payload["artifact_id"], "removed": True}}
                raise AssertionError(payload)

            recovered = command_port.run_mig045_gate12b_committed_proof_v1(
                PROOF_ID, CONTRACT_A, EXPECTED_IDENTITY_SET_SHA256,
                request_fn=recovery_request, state_root=root,
            )
        self.assertEqual([call["operation"] for call in recovery_calls], ["get_run", "cleanup_artifact"])
        self.assertEqual(recovered["broker_run_id"], "gate12b-run-identity")
        self.assertTrue(recovered["replayed"])
        self.assertTrue(recovered["committed"])

    def test_legacy_mig045_intent_contract_remains_available(self):
        self.assertEqual(issue_inbox.MIG045_V1351_INTENT, "MIG045_V1351_ROLLOUT_AND_FRESH_READ")
        self.assertTrue(callable(command_port.run_mig045_v1351_rollout_and_fresh_read_v1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
