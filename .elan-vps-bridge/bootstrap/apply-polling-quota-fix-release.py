#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / ".elan-vps-bridge" / "bootstrap"
INBOX = BOOTSTRAP / "issue_inbox.py"
INSTALL = BOOTSTRAP / "install.sh"
MANIFEST = BOOTSTRAP / "runtime-manifest.json"
REQUEST = BOOTSTRAP / "polling-fix-self-update-request.json"


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 0 and new in text:
        return text
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one old value, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    inbox_text = INBOX.read_text(encoding="utf-8")
    inbox_text = replace_exact(
        inbox_text,
        'POLL_SECONDS = max(60, int(os.environ.get("ELAN_BRIDGE_POLL_SECONDS", "60")))',
        'POLL_SECONDS = max(120, int(os.environ.get("ELAN_BRIDGE_POLL_SECONDS", "120")))',
        "poll_floor",
    )
    inbox_text = replace_exact(
        inbox_text,
        '"?state=open&sort=created&direction=asc&per_page=30"',
        '"?state=open&sort=created&direction=asc&per_page=30&labels=elan-cms-chatgpt"',
        "mailbox_label_filter",
    )
    INBOX.write_text(inbox_text, encoding="utf-8")

    install_text = INSTALL.read_text(encoding="utf-8")
    install_text = replace_exact(
        install_text,
        "Environment=ELAN_BRIDGE_POLL_SECONDS=60",
        "Environment=ELAN_BRIDGE_POLL_SECONDS=120",
        "install_poll_interval",
    )
    INSTALL.write_text(install_text, encoding="utf-8")

    runtime_files = {
        "bridge_worker.py": BOOTSTRAP / "bridge_worker.py",
        "command_port.py": BOOTSTRAP / "command_port.py",
        "issue_inbox.py": BOOTSTRAP / "issue_inbox.py",
    }
    files = {}
    for name, path in runtime_files.items():
        files[name] = {
            "path": f".elan-vps-bridge/bootstrap/{name}",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    manifest_payload = {
        "files": files,
        "release_id": "bridge-polling-quota-fix-20260903-v1",
        "schema_version": "1.0",
    }
    manifest_raw = (json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    MANIFEST.write_bytes(manifest_raw)
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    request_payload = {
        "intent_code": "BRIDGE_SELF_UPDATE",
        "context": {"target": "elan-bridge", "manifest_sha256": manifest_sha},
    }
    REQUEST.write_text(
        json.dumps(request_payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"MANIFEST_SHA256={manifest_sha}")
    print(f"ISSUE_INBOX_SHA256={files['issue_inbox.py']['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
