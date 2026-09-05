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
RELEASE_ID = "bridge-mig045-gate12b-production-materialization-route-20260905-v1"
BRIDGE_WORKER_SHA256 = "7d7f7839cf0c5931bf8af29c78adef59a4e1a0bab10dfb064150942975635cd4"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}_anchor_invalid:{count}")
    return text.replace(old, new)


def patch_runtime(text: str, prefix: str) -> str:
    text = replace_once(
        text,
        'MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS = "reversible_technical_change"\n',
        "",
        f"{prefix}_execution_class_constant",
    )
    text = replace_once(
        text,
        '        or plan.get("risk") not in {"reversible", MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS}\n',
        '        or plan.get("risk") != "reversible"\n',
        f"{prefix}_risk_validation",
    )
    text = replace_once(
        text,
        '        "execution_class": MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS,\n',
        '        "execution_class": plan["risk"],\n',
        f"{prefix}_start_run_execution_class",
    )
    text = replace_once(
        text,
        '        or receipt.get("execution_class") != MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS\n',
        '        or receipt.get("execution_class") != plan["risk"]\n',
        f"{prefix}_receipt_execution_class",
    )
    return text


def patch_command_port() -> None:
    text = COMMAND.read_text(encoding="utf-8")
    COMMAND.write_text(patch_runtime(text, "command_port"), encoding="utf-8")


def patch_original_release() -> None:
    text = ORIGINAL_RELEASE.read_text(encoding="utf-8")
    ORIGINAL_RELEASE.write_text(patch_runtime(text, "original_release"), encoding="utf-8")


def patch_technical_test() -> None:
    text = TECHNICAL_TEST.read_text(encoding="utf-8")
    old = '"reversible_technical_change"'
    count = text.count(old)
    if count != 6:
        raise SystemExit(f"technical_test_reversible_anchor_invalid:{count}")
    TECHNICAL_TEST.write_text(text.replace(old, '"reversible"'), encoding="utf-8")


def write_manifest() -> str:
    files = {}
    for name in RUNTIME_FILES:
        raw = (ROOT / name).read_bytes()
        files[name] = {
            "path": f".elan-vps-bridge/bootstrap/{name}",
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
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
    print(f"RUNTIME_MANIFEST_SHA256={manifest_sha}")
    for name in RUNTIME_FILES:
        print(f"RUNTIME_{name.upper().replace('.', '_')}_SHA256={manifest['files'][name]['sha256']}")


if __name__ == "__main__":
    main()
