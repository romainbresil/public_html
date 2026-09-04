#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
COMMAND = ROOT / "command_port.py"
MANIFEST = ROOT / "runtime-manifest.json"
RUNTIME_FILES = ("issue_inbox.py", "bridge_worker.py", "command_port.py")
RELEASE_ID = "bridge-mig045-v1351-risk-contract-hotfix-20260904-v2"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}_anchor_invalid:{count}")
    return text.replace(old, new)


def main() -> None:
    text = COMMAND.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '    if not isinstance(rollout_plan, dict) or rollout_plan.get("risk") != "reversible":\n',
        '    if not isinstance(rollout_plan, dict) or rollout_plan.get("risk") not in {"reversible", "reversible_technical_change"}:\n',
        "mig045_rollout_risk_contract",
    )
    text = replace_once(
        text,
        '        "execution_class": "reversible",\n',
        '        "execution_class": "reversible_technical_change",\n',
        "mig045_rollout_execution_class",
    )
    COMMAND.write_text(text, encoding="utf-8")

    files = {}
    for name in RUNTIME_FILES:
        path = ROOT / name
        files[name] = {
            "path": f".elan-vps-bridge/bootstrap/{name}",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    manifest = {
        "files": files,
        "release_id": RELEASE_ID,
        "schema_version": "1.0",
    }
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    print(f"RUNTIME_MANIFEST_SHA256={digest}")
    print(f"RELEASE_ID={RELEASE_ID}")


if __name__ == "__main__":
    main()
