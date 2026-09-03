from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMAND_PORT = ROOT / "command_port.py"
ISSUE_INBOX = ROOT / "issue_inbox.py"
BRIDGE_WORKER = ROOT / "bridge_worker.py"
MANIFEST = ROOT / "runtime-manifest.json"
BASE_COMMAND_SHA256 = "8ffa9d596b008ddda56e827860fbbcec3e2cb07f546eac58f05116418dcce4a7"
RELEASE_ID = "en2-g6-schema-read-v3-97db06ef"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch() -> None:
    source = COMMAND_PORT.read_text(encoding="utf-8")
    if 'G6_SCHEMA_CONSTRAINTS_TEMPLATE = "en029_m6_schema_constraints_indexes_chunks_v2"' in source:
        return
    if sha(COMMAND_PORT) != BASE_COMMAND_SHA256:
        raise RuntimeError(f"unexpected_v2_baseline:{sha(COMMAND_PORT)}")

    marker = 'G6_SCHEMA_FUNCTIONS_TEMPLATE = "en029_m6_schema_functions_chunks_v2"\n'
    if marker not in source:
        raise RuntimeError("g6_function_template_marker_missing")
    source = source.replace(marker, marker + 'G6_SCHEMA_CONSTRAINTS_TEMPLATE = "en029_m6_schema_constraints_indexes_chunks_v2"\n', 1)

    old_steps = '''                {
                    "step_id": "schema-functions",
                    "primitive": "postgres_query_template",
                    "args": {
                        "profile": "business",
                        "template": G6_SCHEMA_FUNCTIONS_TEMPLATE,
                        "parameters": [],
                    },
                    "timeout_seconds": 30,
                },
            ],
'''
    new_steps = '''                {
                    "step_id": "schema-functions",
                    "primitive": "postgres_query_template",
                    "args": {
                        "profile": "business",
                        "template": G6_SCHEMA_FUNCTIONS_TEMPLATE,
                        "parameters": [],
                    },
                    "timeout_seconds": 30,
                },
                {
                    "step_id": "schema-constraints",
                    "primitive": "postgres_query_template",
                    "args": {
                        "profile": "business",
                        "template": G6_SCHEMA_CONSTRAINTS_TEMPLATE,
                        "parameters": [],
                    },
                    "timeout_seconds": 30,
                },
            ],
'''
    if old_steps not in source:
        raise RuntimeError("g6_steps_marker_missing")
    source = source.replace(old_steps, new_steps, 1)
    source = source.replace('if not isinstance(steps, list) or len(steps) != 2:', 'if not isinstance(steps, list) or len(steps) != 3:', 1)
    source = source.replace('if set(by_id) != {"schema-columns", "schema-functions"}:', 'if set(by_id) != {"schema-columns", "schema-functions", "schema-constraints"}:', 1)

    old_reconstruct = '''    functions_all = _reconstruct_g6_capture(
        by_id["schema-functions"].get("result"),
        G6_SCHEMA_FUNCTIONS_TEMPLATE,
        "functions",
    )
    allowed_tables = {"dossiers", "dossier_decisions", "dossier_events", "parties"}
'''
    new_reconstruct = '''    functions_all = _reconstruct_g6_capture(
        by_id["schema-functions"].get("result"),
        G6_SCHEMA_FUNCTIONS_TEMPLATE,
        "functions",
    )
    constraints_all = _reconstruct_g6_capture(
        by_id["schema-constraints"].get("result"),
        G6_SCHEMA_CONSTRAINTS_TEMPLATE,
        "constraints_indexes",
    )
    allowed_tables = {"dossiers", "dossier_decisions", "dossier_events", "parties"}
'''
    if old_reconstruct not in source:
        raise RuntimeError("g6_reconstruct_marker_missing")
    source = source.replace(old_reconstruct, new_reconstruct, 1)

    old_functions = '''    functions = [
        item
        for item in functions_all
        if item.get("kind") == "function"
        and item.get("name") == "record_human_decision_v1"
    ]
    if not any(item.get("table") == "dossier_decisions" for item in columns):
'''
    new_functions = '''    functions = [
        item
        for item in functions_all
        if item.get("kind") == "function"
        and item.get("name") == "record_human_decision_v1"
    ]
    constraints_indexes = [
        item
        for item in constraints_all
        if item.get("kind") in {"constraint", "index"}
        and item.get("table") in allowed_tables
    ]
    if not any(item.get("table") == "dossier_decisions" for item in columns):
'''
    if old_functions not in source:
        raise RuntimeError("g6_functions_marker_missing")
    source = source.replace(old_functions, new_functions, 1)

    old_return = '''        "columns": columns,
        "functions": functions,
        "business_rows_emitted": False,
'''
    new_return = '''        "columns": columns,
        "functions": functions,
        "constraints_indexes": constraints_indexes,
        "business_rows_emitted": False,
'''
    if old_return not in source:
        raise RuntimeError("g6_return_marker_missing")
    source = source.replace(old_return, new_return, 1)
    COMMAND_PORT.write_text(source, encoding="utf-8")


def main() -> int:
    patch()
    files = {}
    for name in ("issue_inbox.py", "bridge_worker.py", "command_port.py"):
        path = ROOT / name
        files[name] = {"path": f".elan-vps-bridge/bootstrap/{name}", "sha256": sha(path)}
    manifest = {"files": files, "release_id": RELEASE_ID, "schema_version": "1.0"}
    MANIFEST.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"status":"PASS","release_id":RELEASE_ID,"files":files}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
