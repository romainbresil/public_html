from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMAND_PORT = ROOT / "command_port.py"
ISSUE_INBOX = ROOT / "issue_inbox.py"
BRIDGE_WORKER = ROOT / "bridge_worker.py"
MANIFEST = ROOT / "runtime-manifest.json"

EXPECTED = {
    "issue_inbox.py": "0c20b527f8fb0333becbf7f81df4b564861629c956bf45c8b93443bac3740769",
    "bridge_worker.py": "7d7f7839cf0c5931bf8af29c78adef59a4e1a0bab10dfb064150942975635cd4",
    "command_port.py": "fcfd6a473eb920b58a4de1eb79e251fa22d4406083a1c4f26d0e6deac69715bd",
}
RELEASE_ID = "en2-g6-schema-read-cf92ed80"


def patch_command_port() -> None:
    source = COMMAND_PORT.read_text(encoding="utf-8")
    if "G6_SCHEMA_COLUMNS_TEMPLATE" not in source:
        marker = 'READ_STATUS_TEMPLATE = "en029_m6_schema_migrations_v1"\n'
        replacement = (
            'READ_STATUS_TEMPLATE = "en029_m6_schema_migrations_v1"\n'
            'G6_SCHEMA_COLUMNS_TEMPLATE = "en029_m6_schema_columns_v1"\n'
            'G6_SCHEMA_FUNCTIONS_TEMPLATE = "en029_m6_schema_functions_v1"\n'
        )
        if marker not in source:
            raise RuntimeError("command_port_constant_marker_missing")
        source = source.replace(marker, replacement, 1)
        source += '''


def _parse_g6_values(result: dict, expected_template: str) -> list[dict]:
    if not isinstance(result, dict) or result.get("template") != expected_template:
        raise CommandPortError("broker_g6_schema_result_invalid")
    values = result.get("values")
    if not isinstance(values, list):
        raise CommandPortError("broker_g6_schema_values_invalid")
    parsed = []
    for value in values:
        if not isinstance(value, str):
            raise CommandPortError("broker_g6_schema_value_invalid")
        try:
            item = json.loads(value)
        except json.JSONDecodeError as exc:
            raise CommandPortError("broker_g6_schema_json_invalid") from exc
        if not isinstance(item, dict):
            raise CommandPortError("broker_g6_schema_json_invalid")
        parsed.append(item)
    return parsed


def read_en2_g6_decision_schema_v1(
    request_id: str,
    request_fn: Callable[[dict], dict] = broker_request,
) -> dict:
    key = _safe_key(request_id).lower()
    prepared = request_fn({
        "operation": "prepare_procedure",
        "mission_id": "EN2-G6",
        "work_id": "DECISION-SCHEMA-READ",
        "technical_authority": "JA-023",
        "idempotency_key": f"en2-g6-schema-read-{key}",
        "procedure": {
            "procedure_id": f"en2-g6-schema-read-{key}",
            "title": "EN2-G6 bounded decision schema read",
            "run_budget_seconds": 90,
            "steps": [
                {
                    "step_id": "schema-columns",
                    "primitive": "postgres_query_template",
                    "args": {"profile": "business", "template": G6_SCHEMA_COLUMNS_TEMPLATE, "parameters": []},
                    "timeout_seconds": 30,
                },
                {
                    "step_id": "schema-functions",
                    "primitive": "postgres_query_template",
                    "args": {"profile": "business", "template": G6_SCHEMA_FUNCTIONS_TEMPLATE, "parameters": []},
                    "timeout_seconds": 30,
                },
            ],
        },
    })
    plan = prepared.get("plan")
    if not isinstance(plan, dict) or plan.get("risk") != "read_only":
        raise CommandPortError("broker_g6_schema_plan_not_read_only")
    executed = request_fn({
        "operation": "start_run",
        "plan_id": plan.get("plan_id"),
        "execution_token": plan.get("execution_token"),
        "procedure_sha256": plan.get("procedure_sha256"),
        "execution_class": "read_only",
        "mode": "sync",
    })
    receipt = executed.get("receipt")
    if not isinstance(receipt, dict) or receipt.get("status") != "succeeded" or receipt.get("execution_class") != "read_only":
        raise CommandPortError("broker_g6_schema_read_failed")
    steps = receipt.get("steps")
    if not isinstance(steps, list) or len(steps) != 2:
        raise CommandPortError("broker_g6_schema_receipt_invalid")
    by_id = {step.get("step_id"): step for step in steps if isinstance(step, dict) and isinstance(step.get("step_id"), str)}
    if set(by_id) != {"schema-columns", "schema-functions"}:
        raise CommandPortError("broker_g6_schema_step_mismatch")
    if any(by_id[name].get("status") != "success" for name in by_id):
        raise CommandPortError("broker_g6_schema_step_failed")
    columns_all = _parse_g6_values(by_id["schema-columns"].get("result"), G6_SCHEMA_COLUMNS_TEMPLATE)
    functions_all = _parse_g6_values(by_id["schema-functions"].get("result"), G6_SCHEMA_FUNCTIONS_TEMPLATE)
    allowed_tables = {"dossiers", "dossier_decisions", "dossier_events", "parties"}
    columns = [item for item in columns_all if item.get("kind") == "column" and item.get("table") in allowed_tables]
    functions = [item for item in functions_all if item.get("kind") == "function" and item.get("name") == "record_human_decision_v1"]
    if not any(item.get("table") == "dossier_decisions" for item in columns):
        raise CommandPortError("g6_decision_columns_missing")
    if not functions:
        raise CommandPortError("g6_record_human_decision_missing")
    return {
        "status": "succeeded",
        "execution_class": "read_only",
        "run_id": receipt.get("run_id"),
        "columns": columns,
        "functions": functions,
        "business_rows_emitted": False,
        "external_action_allowed": False,
    }
'''
        COMMAND_PORT.write_text(source, encoding="utf-8")


def patch_issue_inbox() -> None:
    source = ISSUE_INBOX.read_text(encoding="utf-8")
    if "G6_SCHEMA_READ_INTENT" in source:
        return
    marker = 'G5_KNOWLEDGE_CONTEXT = {"target": "en2-g5-knowledge-capture"}\n'
    replacement = marker + 'G6_SCHEMA_READ_INTENT = "EN2_G6_DECISION_SCHEMA_READ"\nG6_SCHEMA_READ_CONTEXT = {"target": "en2-g6-decision-schema"}\n'
    if marker not in source:
        raise RuntimeError("issue_inbox_constant_marker_missing")
    source = source.replace(marker, replacement, 1)
    marker = '''    if job["intent_code"] == G5_KNOWLEDGE_INTENT:\n        if job["context"] != G5_KNOWLEDGE_CONTEXT:\n            return None\n        return job\n'''
    replacement = marker + '''    if job["intent_code"] == G6_SCHEMA_READ_INTENT:\n        if job["context"] != G6_SCHEMA_READ_CONTEXT:\n            return None\n        return job\n'''
    if marker not in source:
        raise RuntimeError("issue_inbox_parse_marker_missing")
    source = source.replace(marker, replacement, 1)
    marker = '''    if job["intent_code"] == G5_KNOWLEDGE_INTENT:\n        try:\n            payload = command_port.run_en2_g5_knowledge_capture_v1(job["id"])\n            return _completed(job, started, {"status": "PASS", **payload})\n        except command_port.CommandPortError as exc:\n            return _failed(job, started, str(exc))\n'''
    replacement = marker + '''    if job["intent_code"] == G6_SCHEMA_READ_INTENT:\n        try:\n            payload = command_port.read_en2_g6_decision_schema_v1(job["id"])\n            return _completed(job, started, {"status": "PASS", **payload})\n        except command_port.CommandPortError as exc:\n            return _failed(job, started, str(exc))\n'''
    if marker not in source:
        raise RuntimeError("issue_inbox_execute_marker_missing")
    ISSUE_INBOX.write_text(source.replace(marker, replacement, 1), encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    patch_command_port()
    patch_issue_inbox()
    actual = {
        "issue_inbox.py": sha(ISSUE_INBOX),
        "bridge_worker.py": sha(BRIDGE_WORKER),
        "command_port.py": sha(COMMAND_PORT),
    }
    if actual != EXPECTED:
        raise RuntimeError(f"runtime_hash_mismatch:{actual}")
    manifest = {
        "files": {
            name: {"path": f".elan-vps-bridge/bootstrap/{name}", "sha256": digest}
            for name, digest in actual.items()
        },
        "release_id": RELEASE_ID,
        "schema_version": "1.0",
    }
    MANIFEST.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"status":"PASS","release_id":RELEASE_ID,"files":actual}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
