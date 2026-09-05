#!/usr/bin/env python3
from __future__ import annotations

import copy
import pathlib
import sys
import unittest
from unittest import mock

BOOTSTRAP = pathlib.Path(__file__).resolve().parent
if str(BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(BOOTSTRAP))

import command_port  # noqa: E402
import issue_inbox  # noqa: E402

A_HEAD = "b8a5672d090fb0ddceb552e5029cf04b736da44d"
A_RUNTIME_VERSION = "1.3.52"
A_CAPABILITY_SHA256 = "b51a4bf09041f42af28b737f868710d5377123eb0747ae4fd6e2fd290a006729"
A_COMMAND_TEMPLATE_SHA256 = "6fff7e691aaa4cbc7d3b789e8b111988bc08d2680e911e6298c4d16fcceb123a"
A_SQL_OWNER_SHA256 = "77c7c90c25f2eefe7827a1c0c469b5a1343ca0646aa9c29d485e3dc1edd2fa25"
EXPECTED_IDENTITY_SET_SHA256 = "dc731702f983999e083563477216054bfcee5674eff03a5d6ef8cb479b0c2cc1"
CORPUS = [f"CON-{number:03d}" for number in range(20, 28)]

# Negative-only evidence. These values must never become production runtime constants.
EPHEMERAL_POLICY_SHA256 = "47b5f89d5d007551041e89bcce99bddeba3b465cf30e60f7b49b52b8a0618b30"
EPHEMERAL_TARGET_SHA256 = "ceb47bf767e2ea4b361aba0701f97a601bde5b6a01b7d9de1efc9adcbb5e6368"
QUALIFICATION_PROOF_CONTRACT_SHA256 = "71f8f4a3e95710cf3bb510a47c6b788a6479d79903ede0728b7accd557fbc0d9"

PRODUCTION_POLICY_A = "10" * 32
PRODUCTION_TARGET_A = "20" * 32
PRODUCTION_POLICY_B = "30" * 32
PRODUCTION_TARGET_B = "40" * 32


def production_preflight(*, policy_sha=PRODUCTION_POLICY_A, target_sha=PRODUCTION_TARGET_A):
    return {
        "business_reads": 0,
        "proof_executed": False,
        "runtime_version": A_RUNTIME_VERSION,
        "runtime_source_commit": A_HEAD,
        "capability_sha256": A_CAPABILITY_SHA256,
        "effective_policy_sha256": policy_sha,
        "command_template_sha256": A_COMMAND_TEMPLATE_SHA256,
        "sql_owner_sha256": A_SQL_OWNER_SHA256,
        "target_binding_sha256": target_sha,
        "resolved_database": "postgres",
        "resolved_role": "en_gate12b_executor",
        "postgres_profile": "business",
        "schema": "elan_naturel",
        "expected_identity_set_sha256": EXPECTED_IDENTITY_SET_SHA256,
        "corpus": list(CORPUS),
    }


def raw_a_broker_preflight(*, policy_sha=PRODUCTION_POLICY_A, target_sha=PRODUCTION_TARGET_A):
    return {
        "status": "ok",
        "operation": "gate12b_technical_preflight",
        "preflight": {
            "runtime_version": A_RUNTIME_VERSION,
            "runtime_source_commit": A_HEAD,
            "capability_sha256": A_CAPABILITY_SHA256,
            "effective_policy_sha256": policy_sha,
            "command_template_sha256": A_COMMAND_TEMPLATE_SHA256,
            "sql_owner_sha256": A_SQL_OWNER_SHA256,
            "target_binding_sha256": target_sha,
        },
        "provenance": {
            "resolved_database": "postgres",
            "resolved_role": "en_gate12b_executor",
            "session_user": "postgres",
            "postgres_profile": "business",
            "container": "elan-postgres-prod",
            "container_id": "50" * 32,
            "schema": "elan_naturel",
            "expected_identity_set_sha256": EXPECTED_IDENTITY_SET_SHA256,
            "corpus": "CON-020..CON-027",
            "corpus_sha256": "cd0f4bde395351cbdb99b9d6f342cc0718d2be5276ca06000e44162d00bebcef",
            "business_reads": 0,
            "free_sql": False,
            "generic_business_mutation": False,
            "effective_policy": {"owner_backed": True},
            "target_binding": {"owner_backed": True},
        },
    }


def freeze(preflight):
    fn = getattr(command_port, "freeze_mig045_gate12b_production_proof", None)
    if not callable(fn):
        raise AssertionError("freeze_mig045_gate12b_production_proof_missing")
    return fn(preflight)


def request_freeze(request_fn):
    fn = getattr(command_port, "request_mig045_gate12b_production_proof_freeze", None)
    if not callable(fn):
        raise AssertionError("request_mig045_gate12b_production_proof_freeze_missing")
    return fn(request_fn=request_fn)


class Gate12BABStaticOwnerIntegrationTests(unittest.TestCase):
    def test_a_static_owner_hashes_are_integrated_exactly(self):
        expected = {
            "MIG045_GATE12B_A_TECHNICAL_HEAD": A_HEAD,
            "MIG045_GATE12B_RUNTIME_VERSION": A_RUNTIME_VERSION,
            "MIG045_GATE12B_CAPABILITY_SHA256": A_CAPABILITY_SHA256,
            "MIG045_GATE12B_COMMAND_TEMPLATE_SHA256": A_COMMAND_TEMPLATE_SHA256,
            "MIG045_GATE12B_SQL_OWNER_SHA256": A_SQL_OWNER_SHA256,
            "MIG045_GATE12B_EXPECTED_IDENTITY_SET_SHA256": EXPECTED_IDENTITY_SET_SHA256,
        }
        for name, value in expected.items():
            self.assertEqual(getattr(command_port, name, None), value, name)
        self.assertEqual(list(command_port.MIG045_GATE12B_CORPUS), CORPUS)

    def test_exact_10_field_contract_is_built_from_production_preflight(self):
        result = freeze(production_preflight())
        contract = result["proof_contract"]
        self.assertEqual(
            set(contract),
            {
                "observation_semantics",
                "expected_identity_set_sha256",
                "corpus",
                "runtime_version",
                "runtime_source_commit",
                "capability_sha256",
                "effective_policy_sha256",
                "command_template_sha256",
                "sql_owner_sha256",
                "target_binding_sha256",
            },
        )
        self.assertEqual(contract["runtime_source_commit"], A_HEAD)
        self.assertEqual(contract["effective_policy_sha256"], PRODUCTION_POLICY_A)
        self.assertEqual(contract["target_binding_sha256"], PRODUCTION_TARGET_A)
        self.assertEqual(result["proof_contract_sha256"], command_port.mig045_gate12b_proof_contract_sha256(contract))
        self.assertEqual(result["proof_id"], command_port.derive_mig045_gate12b_proof_id(result["proof_contract_sha256"]))

    def test_wrong_a_static_bindings_fail_closed(self):
        mutations = {
            "runtime_version": "1.3.53",
            "runtime_source_commit": "a" * 40,
            "capability_sha256": "a" * 64,
            "command_template_sha256": "b" * 64,
            "sql_owner_sha256": "c" * 64,
            "expected_identity_set_sha256": "d" * 64,
            "corpus": CORPUS[:-1],
        }
        for field, bad in mutations.items():
            value = production_preflight()
            value[field] = bad
            with self.subTest(field=field):
                with self.assertRaisesRegex(command_port.CommandPortError, "mismatch|invalid"):
                    freeze(value)


class Gate12BProductionPreflightValidationTests(unittest.TestCase):
    def test_missing_or_malformed_production_hashes_fail_closed(self):
        for field in ("effective_policy_sha256", "target_binding_sha256"):
            missing = production_preflight()
            missing.pop(field)
            malformed = production_preflight()
            malformed[field] = "not-a-sha"
            with self.subTest(field=field, case="missing"):
                with self.assertRaises(command_port.CommandPortError):
                    freeze(missing)
            with self.subTest(field=field, case="malformed"):
                with self.assertRaises(command_port.CommandPortError):
                    freeze(malformed)

    def test_business_read_or_proof_execution_rejects_freeze(self):
        business_read = production_preflight()
        business_read["business_reads"] = 1
        proof_ran = production_preflight()
        proof_ran["proof_executed"] = True
        with self.assertRaisesRegex(command_port.CommandPortError, "business_reads"):
            freeze(business_read)
        with self.assertRaisesRegex(command_port.CommandPortError, "proof_executed"):
            freeze(proof_ran)

    def test_target_semantics_are_exact_and_fail_closed(self):
        mutations = {
            "resolved_database": "otherdb",
            "resolved_role": "postgres",
            "postgres_profile": "other",
            "schema": "public",
        }
        for field, bad in mutations.items():
            value = production_preflight()
            value[field] = bad
            with self.subTest(field=field):
                with self.assertRaisesRegex(command_port.CommandPortError, "target|mismatch|invalid"):
                    freeze(value)

    def test_raw_a_runtime_preflight_is_consumed_without_business_proof(self):
        calls = []

        def request_fn(payload):
            calls.append(payload)
            return raw_a_broker_preflight()

        result = request_freeze(request_fn)
        self.assertEqual(calls, [{"operation": "gate12b_technical_preflight"}])
        self.assertEqual(result["technical_preflight"]["business_reads"], 0)
        self.assertIs(result["technical_preflight"]["proof_executed"], False)
        self.assertEqual(result["proof_contract"]["effective_policy_sha256"], PRODUCTION_POLICY_A)
        self.assertEqual(result["proof_contract"]["target_binding_sha256"], PRODUCTION_TARGET_A)


class Gate12BProductionFreezeIdentityTests(unittest.TestCase):
    def test_production_binding_drift_changes_contract_hash_and_proof_id(self):
        first = freeze(production_preflight(policy_sha=PRODUCTION_POLICY_A, target_sha=PRODUCTION_TARGET_A))
        second = freeze(production_preflight(policy_sha=PRODUCTION_POLICY_B, target_sha=PRODUCTION_TARGET_A))
        third = freeze(production_preflight(policy_sha=PRODUCTION_POLICY_A, target_sha=PRODUCTION_TARGET_B))
        self.assertNotEqual(first["proof_contract_sha256"], second["proof_contract_sha256"])
        self.assertNotEqual(first["proof_id"], second["proof_id"])
        self.assertNotEqual(first["proof_contract_sha256"], third["proof_contract_sha256"])
        self.assertNotEqual(first["proof_id"], third["proof_id"])

    def test_qualification_proof_hash_is_never_trusted_as_production_hash(self):
        value = production_preflight()
        value["proof_contract_sha256"] = QUALIFICATION_PROOF_CONTRACT_SHA256
        frozen = freeze(value)
        self.assertNotEqual(frozen["proof_contract_sha256"], QUALIFICATION_PROOF_CONTRACT_SHA256)
        self.assertEqual(
            frozen["proof_contract_sha256"],
            command_port.mig045_gate12b_proof_contract_sha256(frozen["proof_contract"]),
        )

    def test_ephemeral_qualification_hashes_are_not_runtime_constants(self):
        source = pathlib.Path(command_port.__file__).read_text(encoding="utf-8")
        self.assertNotIn(EPHEMERAL_POLICY_SHA256, source)
        self.assertNotIn(EPHEMERAL_TARGET_SHA256, source)
        self.assertNotIn(QUALIFICATION_PROOF_CONTRACT_SHA256, source)

    def test_context_static_owner_drift_is_rejected_before_any_proof_path(self):
        frozen = freeze(production_preflight())
        context = {
            "target": command_port.MIG045_GATE12B_TARGET,
            "proof_contract": frozen["proof_contract"],
            "proof_contract_sha256": frozen["proof_contract_sha256"],
            "proof_id": frozen["proof_id"],
        }
        self.assertEqual(command_port.validate_mig045_gate12b_context(context), context)
        drifted = copy.deepcopy(context)
        drifted["proof_contract"]["runtime_source_commit"] = "a" * 40
        drifted["proof_contract_sha256"] = command_port.mig045_gate12b_proof_contract_sha256(drifted["proof_contract"])
        drifted["proof_id"] = command_port.derive_mig045_gate12b_proof_id(drifted["proof_contract_sha256"])
        with self.assertRaisesRegex(command_port.CommandPortError, "runtime_source_commit.*mismatch|static.*mismatch"):
            command_port.validate_mig045_gate12b_context(drifted)


class Gate12BPreflightMailboxSurfaceTests(unittest.TestCase):
    def test_preflight_freeze_intent_is_distinct_and_has_no_proof_identity_input(self):
        intent = getattr(issue_inbox, "MIG045_GATE12B_PREFLIGHT_INTENT", None)
        context = getattr(issue_inbox, "MIG045_GATE12B_PREFLIGHT_CONTEXT", None)
        self.assertEqual(intent, "MIG045_GATE12B_TECHNICAL_PREFLIGHT_FREEZE_V1")
        self.assertEqual(context, {"target": "mig045-gate12b-technical-preflight-freeze"})
        self.assertNotEqual(intent, issue_inbox.MIG045_GATE12B_INTENT)
        self.assertNotEqual(intent, issue_inbox.MIG045_V1351_INTENT)
        self.assertNotIn("proof_id", context)
        self.assertNotIn("proof_contract_sha256", context)

    def test_preflight_freeze_dispatch_never_falls_back_to_proof_or_old_fresh_read(self):
        intent = getattr(issue_inbox, "MIG045_GATE12B_PREFLIGHT_INTENT", None)
        context = getattr(issue_inbox, "MIG045_GATE12B_PREFLIGHT_CONTEXT", None)
        self.assertIsNotNone(intent)
        self.assertIsNotNone(context)
        job = {
            "id": "gh-issue-990",
            "intent_code": intent,
            "context": context,
            "read_token": "x" * 32,
        }
        frozen = {
            "proof_contract": {"safe": True},
            "proof_contract_sha256": "1" * 64,
            "proof_id": "2" * 64,
            "technical_preflight": {"business_reads": 0, "proof_executed": False},
        }
        with mock.patch.object(
            issue_inbox.command_port,
            "request_mig045_gate12b_production_proof_freeze",
            return_value=frozen,
        ) as preflight_run, mock.patch.object(
            issue_inbox.command_port,
            "run_mig045_gate12b_committed_proof_v1",
        ) as proof_run, mock.patch.object(
            issue_inbox.command_port,
            "run_mig045_v1351_rollout_and_fresh_read_v1",
        ) as old_run:
            result = issue_inbox._execute_job(job)
        self.assertEqual(result["state"], "COMPLETED")
        self.assertEqual(result["result"]["status"], "PASS")
        self.assertEqual(result["result"]["proof_id"], "2" * 64)
        preflight_run.assert_called_once()
        proof_run.assert_not_called()
        old_run.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
