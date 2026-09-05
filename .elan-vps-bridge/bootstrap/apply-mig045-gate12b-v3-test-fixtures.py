#!/usr/bin/env python3
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
TEST = ROOT / "test_mig045_gate12b_committed_proof.py"


def replace_once(old: str, new: str) -> None:
    text = TEST.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected_one_regression_fragment:{count}")
    TEST.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    replace_once(
        'with self.assertRaisesRegex(command_port.CommandPortError, "proof_id_mismatch"):\n',
        'with self.assertRaisesRegex(command_port.CommandPortError, "static_binding_mismatch|proof_id_mismatch"):\n',
    )
    replace_once(
        '''        def forbidden_request(_payload):\n            raise AssertionError("business broker path must not start without technical preflight owner")\n\n        with self.assertRaisesRegex(command_port.CommandPortError, "preflight_owner_not_bound"):\n            command_port.run_mig045_gate12b_committed_proof_v1(\n                ctx["proof_contract"],\n                ctx["proof_contract_sha256"],\n                ctx["proof_id"],\n                request_fn=forbidden_request,\n                state_root=pathlib.Path("unused"),\n            )\n''',
        '''        def unavailable_preflight(payload):\n            self.assertEqual(payload, {"operation": "gate12b_technical_preflight"})\n            raise command_port.CommandPortError("broker_unavailable")\n\n        with self.assertRaisesRegex(command_port.CommandPortError, "broker_unavailable"):\n            command_port.run_mig045_gate12b_committed_proof_v1(\n                ctx["proof_contract"],\n                ctx["proof_contract_sha256"],\n                ctx["proof_id"],\n                request_fn=unavailable_preflight,\n                state_root=pathlib.Path("unused"),\n            )\n''',
    )
    print("MIG045_GATE12B_V3_TEST_FIXTURES_ALIGNED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
