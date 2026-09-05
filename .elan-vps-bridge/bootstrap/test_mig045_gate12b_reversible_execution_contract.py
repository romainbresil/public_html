#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys
import unittest

BOOTSTRAP = pathlib.Path(__file__).resolve().parent
if str(BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(BOOTSTRAP))

import command_port  # noqa: E402


class Gate12BReversibleExecutionContractTests(unittest.TestCase):
    def test_execution_class_is_broker_plan_owned_not_hardcoded_by_gate12b(self):
        self.assertFalse(hasattr(command_port, "MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS"))
        prepared = {
            "plan": {
                "risk": "reversible",
                "plan_id": "gate12b-reversible-plan",
                "execution_token": "gate12b-reversible-token",
                "procedure_sha256": "a" * 64,
            }
        }
        plan = command_port._mig045_gate12b_reversible_plan(prepared, "contract")
        self.assertEqual(plan["risk"], "reversible")

        observed = []

        def request_fn(payload: dict) -> dict:
            observed.append(payload)
            self.assertEqual(payload["operation"], "start_run")
            self.assertEqual(payload["execution_class"], plan["risk"])
            return {
                "receipt": {
                    "status": "succeeded",
                    "execution_class": plan["risk"],
                    "run_id": "gate12b-reversible-run",
                    "steps": [],
                }
            }

        receipt = command_port._mig045_gate12b_run_plan(request_fn, plan, "contract")
        self.assertEqual(receipt["run_id"], "gate12b-reversible-run")
        self.assertEqual(len(observed), 1)

    def test_noncanonical_reversible_class_is_rejected_fail_closed(self):
        for risk in ("reversible_technical_change", "mutating", "read_only", ""):
            with self.subTest(risk=risk):
                with self.assertRaises(command_port.CommandPortError):
                    command_port._mig045_gate12b_reversible_plan(
                        {
                            "plan": {
                                "risk": risk,
                                "plan_id": "p",
                                "execution_token": "t",
                                "procedure_sha256": "b" * 64,
                            }
                        },
                        "contract",
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
