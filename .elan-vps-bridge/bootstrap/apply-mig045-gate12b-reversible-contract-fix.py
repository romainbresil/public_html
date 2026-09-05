#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
COMMAND = ROOT / "command_port.py"
ORIGINAL_RELEASE = ROOT / "apply-mig045-gate12b-materialization-route.py"
TECHNICAL_TEST = ROOT / "test_mig045_gate12b_technical_materialization.py"
MANIFEST = ROOT / "runtime-manifest.json"
RUNTIME_FILES = ("issue_inbox.py", "bridge_worker.py", "command_port.py")
PREVIOUS_RELEASE_ID = "bridge-mig045-gate12b-production-materialization-route-20260905-v1"
RELEASE_ID = "bridge-mig045-gate12b-plan-risk-contract-fix-20260905-v1"
EXECUTION_CLASS = "reversible_technical_change"
ISSUE_INBOX_SHA256 = "da64818986b268ac961dcac2a07669853aef0ad99619a4ae34b17e5c9bf64453"
BRIDGE_WORKER_SHA256 = "7d7f7839cf0c5931bf8af29c78adef59a4e1a0bab10dfb064150942975635cd4"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}_anchor_invalid:{count}")
    return text.replace(old, new)


def replace_exact_count(text: str, old: str, new: str, expected: int, label: str) -> str:
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"{label}_anchor_invalid:{count}")
    return text.replace(old, new)


def patch_runtime(text: str, prefix: str) -> str:
    text = replace_once(
        text,
        'MIG045_GATE12B_TECHNICAL_RESOURCE_LOCK = "postgres-business-en033-mig045-gate12b"\n',
        'MIG045_GATE12B_TECHNICAL_RESOURCE_LOCK = "postgres-business-en033-mig045-gate12b"\n'
        'MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS = "reversible_technical_change"\n',
        f"{prefix}_execution_class_constant",
    )
    text = replace_once(
        text,
        '        or plan.get("risk") != "reversible"\n',
        '        or plan.get("risk") != MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS\n',
        f"{prefix}_risk_validation",
    )
    text = replace_once(
        text,
        '        "execution_class": plan["risk"],\n',
        '        "execution_class": MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS,\n',
        f"{prefix}_start_run_execution_class",
    )
    text = replace_once(
        text,
        '        or receipt.get("execution_class") != plan["risk"]\n',
        '        or receipt.get("execution_class") != MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS\n',
        f"{prefix}_receipt_execution_class",
    )
    text = replace_once(
        text,
        '        or receipt.get("status") != "succeeded"\n'
        '        or receipt.get("execution_class") != MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS\n',
        '        or receipt.get("status") != "succeeded"\n'
        '        or receipt.get("risk") != MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS\n'
        '        or receipt.get("execution_class") != MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS\n',
        f"{prefix}_receipt_risk",
    )
    return text


def patch_command_port() -> None:
    text = COMMAND.read_text(encoding="utf-8")
    COMMAND.write_text(patch_runtime(text, "command_port"), encoding="utf-8")


def patch_original_release() -> None:
    text = ORIGINAL_RELEASE.read_text(encoding="utf-8")
    text = patch_runtime(text, "original_release")
    text = replace_once(
        text,
        f'RELEASE_ID = "{PREVIOUS_RELEASE_ID}"\n',
        f'RELEASE_ID = "{RELEASE_ID}"\n',
        "original_release_release_id",
    )
    ORIGINAL_RELEASE.write_text(text, encoding="utf-8")


def patch_technical_test() -> None:
    text = TECHNICAL_TEST.read_text(encoding="utf-8")
    text = replace_exact_count(
        text,
        '"risk": "reversible",',
        f'"risk": "{EXECUTION_CLASS}",',
        2,
        "technical_test_plan_risk",
    )
    text = replace_exact_count(
        text,
        'self.assertEqual(payload["execution_class"], "reversible")',
        f'self.assertEqual(payload["execution_class"], "{EXECUTION_CLASS}")',
        2,
        "technical_test_start_run_class",
    )
    text = replace_exact_count(
        text,
        '"execution_class": "reversible",',
        f'"execution_class": "{EXECUTION_CLASS}",',
        2,
        "technical_test_receipt_class",
    )
    text = replace_exact_count(
        text,
        '                    "status": "succeeded",\n'
        f'                    "execution_class": "{EXECUTION_CLASS}",\n',
        '                    "status": "succeeded",\n'
        f'                    "risk": "{EXECUTION_CLASS}",\n'
        f'                    "execution_class": "{EXECUTION_CLASS}",\n',
        2,
        "technical_test_receipt_risk",
    )
    TECHNICAL_TEST.write_text(text, encoding="utf-8")


def write_manifest() -> str:
    files = {}
    for name in RUNTIME_FILES:
        raw = (ROOT / name).read_bytes()
        files[name] = {
            "path": f".elan-vps-bridge/bootstrap/{name}",
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    if files["issue_inbox.py"]["sha256"] != ISSUE_INBOX_SHA256:
        raise SystemExit("issue_inbox_hash_changed")
    if files["bridge_worker.py"]["sha256"] != BRIDGE_WORKER_SHA256:
        raise SystemExit("bridge_worker_hash_changed")
    payload = {
        "schema_version": "1.0",
        "release_id": RELEASE_ID,
        "files": files,
    }
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    MANIFEST.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    patch_command_port()
    patch_original_release()
    patch_technical_test()
    manifest_sha = write_manifest()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    print(f"RELEASE_ID={RELEASE_ID}")
    print(f"RUNTIME_MANIFEST_SHA256={manifest_sha}")
    for name in RUNTIME_FILES:
        print(f"RUNTIME_{name.upper().replace('.', '_')}_SHA256={manifest['files'][name]['sha256']}")


if __name__ == "__main__":
    main()
