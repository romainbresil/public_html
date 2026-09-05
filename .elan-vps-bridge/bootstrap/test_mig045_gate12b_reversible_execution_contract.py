#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys
import unittest

BOOTSTRAP = pathlib.Path(__file__).resolve().parent
if str(BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(BOOTSTRAP))

import command_port  # noqa: E402


OWNER_BACKED_PLAN_RISK = "reversible_technical_change"


def owner_backed_plan(risk: object = OWNER_BACKED_PLAN_RISK) -> dict:
    return {
        "risk": risk,
        "plan_id": "gate12b-owner-backed-plan",
        "execution_token": "gate12b-owner-backed-token",
        "procedure_sha256": "a" * 64,
    }


class Gate12BReversibleExecutionContractTests(unittest.TestCase):
    def test_owner_backed_plan_level_risk_is_accepted(self):
        prepared = {"plan": owner_backed_plan()}
        plan = command_port._mig045_gate12b_reversible_plan(prepared, "contract")
        self.assertEqual(plan["risk"], OWNER_BACKED_PLAN_RISK)

    def test_primitive_or_nonreversible_plan_risks_are_rejected_fail_closed(self):
        for risk in ("reversible", "read_only", "mutating_technical_change", "mutating", "", None):
            with self.subTest(risk=risk):
                with self.assertRaises(command_port.CommandPortError):
                    command_port._mig045_gate12b_reversible_plan(
                        {"plan": owner_backed_plan(risk)},
                        "contract",
                    )

    def test_malformed_owner_backed_plan_is_rejected_fail_closed(self):
        for field in ("plan_id", "execution_token", "procedure_sha256"):
            with self.subTest(field=field):
                plan = owner_backed_plan()
                plan[field] = ""
                with self.assertRaises(command_port.CommandPortError):
                    command_port._mig045_gate12b_reversible_plan({"plan": plan}, "contract")

    def test_start_run_matches_generated_broker_wire_and_receipt_contract(self):
        plan = owner_backed_plan()
        observed: list[dict] = []

        def request_fn(payload: dict) -> dict:
            observed.append(payload)
            return {
                "receipt": {
                    "status": "succeeded",
                    "risk": OWNER_BACKED_PLAN_RISK,
                    "execution_class": OWNER_BACKED_PLAN_RISK,
                    "run_id": "gate12b-owner-backed-run",
                    "steps": [],
                }
            }

        receipt = command_port._mig045_gate12b_run_plan(request_fn, plan, "contract")
        self.assertEqual(receipt["run_id"], "gate12b-owner-backed-run")
        self.assertEqual(
            observed,
            [{
                "operation": "start_run",
                "plan_id": plan["plan_id"],
                "execution_token": plan["execution_token"],
                "procedure_sha256": plan["procedure_sha256"],
                "execution_class": OWNER_BACKED_PLAN_RISK,
                "mode": "sync",
            }],
        )

    def test_receipt_risk_must_match_owner_backed_plan_level_contract(self):
        plan = owner_backed_plan()

        def request_fn(_: dict) -> dict:
            return {
                "receipt": {
                    "status": "succeeded",
                    "risk": "reversible",
                    "execution_class": OWNER_BACKED_PLAN_RISK,
                    "run_id": "gate12b-wrong-risk-run",
                    "steps": [],
                }
            }

        with self.assertRaises(command_port.CommandPortError):
            command_port._mig045_gate12b_run_plan(request_fn, plan, "contract")

    def test_receipt_execution_class_must_match_owner_backed_plan_level_contract(self):
        plan = owner_backed_plan()

        def request_fn(_: dict) -> dict:
            return {
                "receipt": {
                    "status": "succeeded",
                    "risk": OWNER_BACKED_PLAN_RISK,
                    "execution_class": "legacy_full",
                    "run_id": "gate12b-wrong-class-run",
                    "steps": [],
                }
            }

        with self.assertRaises(command_port.CommandPortError):
            command_port._mig045_gate12b_run_plan(request_fn, plan, "contract")


if __name__ == "__main__":
    unittest.main(verbosity=2)
