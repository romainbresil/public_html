#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / ".elan-vps-bridge" / "bootstrap"
COMMAND_PORT = BOOTSTRAP / "command_port.py"
ISSUE_INBOX = BOOTSTRAP / "issue_inbox.py"
MANIFEST = BOOTSTRAP / "runtime-manifest.json"

COMMAND_MARKER = 'P1_MIGRATION_REGISTRY_TEMPLATE = "en033_m1_mig037_registry_read_all_v1"'
COMMAND_APPEND = r'''

# EN2-P1 bounded canonical migration-registry read. This reuses the
# previously deployed MIG-037 broker query template; callers cannot supply SQL.
P1_MIGRATION_REGISTRY_TEMPLATE = "en033_m1_mig037_registry_read_all_v1"


def read_en2_p1_migration_registry_v1(
    request_id: str,
    request_fn: Callable[[dict], dict] = broker_request,
) -> dict:
    key = _safe_key(request_id).lower()
    prepared = request_fn({
        "operation": "prepare_procedure",
        "mission_id": "EN2-P1",
        "work_id": "MIGRATION-REGISTRY-PREFLIGHT-READ",
        "technical_authority": "JA-023",
        "idempotency_key": f"en2-p1-migration-registry-read-{key}",
        "procedure": {
            "procedure_id": f"en2-p1-migration-registry-read-{key}",
            "title": "EN2-P1 bounded canonical migration registry read",
            "run_budget_seconds": 60,
            "steps": [{
                "step_id": "migration-registry-read",
                "primitive": "postgres_query_template",
                "args": {
                    "profile": "business",
                    "template": P1_MIGRATION_REGISTRY_TEMPLATE,
                    "parameters": [],
                },
                "timeout_seconds": 30,
            }],
        },
    })
    plan = prepared.get("plan")
    if not isinstance(plan, dict) or plan.get("risk") != "read_only":
        raise CommandPortError("broker_p1_registry_plan_not_read_only")
    executed = request_fn({
        "operation": "start_run",
        "plan_id": plan.get("plan_id"),
        "execution_token": plan.get("execution_token"),
        "procedure_sha256": plan.get("procedure_sha256"),
        "execution_class": "read_only",
        "mode": "sync",
    })
    receipt = executed.get("receipt")
    if (
        not isinstance(receipt, dict)
        or receipt.get("status") != "succeeded"
        or receipt.get("execution_class") != "read_only"
    ):
        raise CommandPortError("broker_p1_registry_read_failed")
    steps = receipt.get("steps")
    if not isinstance(steps, list) or len(steps) != 1 or not isinstance(steps[0], dict):
        raise CommandPortError("broker_p1_registry_receipt_invalid")
    step = steps[0]
    if step.get("step_id") != "migration-registry-read" or step.get("status") != "success":
        raise CommandPortError("broker_p1_registry_step_invalid")
    result = step.get("result")
    if not isinstance(result, dict) or result.get("template") != P1_MIGRATION_REGISTRY_TEMPLATE:
        raise CommandPortError("broker_p1_registry_result_invalid")
    values = result.get("values")
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], str):
        raise CommandPortError("broker_p1_registry_values_invalid")
    try:
        entries = json.loads(values[0])
    except json.JSONDecodeError as exc:
        raise CommandPortError("broker_p1_registry_json_invalid") from exc
    if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
        raise CommandPortError("broker_p1_registry_contract_invalid")
    return {
        "status": "succeeded",
        "execution_class": "read_only",
        "template": P1_MIGRATION_REGISTRY_TEMPLATE,
        "entries": entries,
        "run_id": receipt.get("run_id"),
        "replayed": bool(receipt.get("replayed")),
        "external_action_allowed": False,
    }
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    command = COMMAND_PORT.read_text(encoding="utf-8")
    if COMMAND_MARKER not in command:
        command = command.rstrip() + "\n" + COMMAND_APPEND.lstrip("\n")
        COMMAND_PORT.write_text(command, encoding="utf-8")

    inbox = ISSUE_INBOX.read_text(encoding="utf-8")
    if 'P1_MIGRATION_REGISTRY_INTENT = "EN2_P1_MIGRATION_REGISTRY_READ"' not in inbox:
        inbox = replace_once(
            inbox,
            'G6_SCHEMA_READ_CONTEXT = {"target": "en2-g6-decision-schema"}\n',
            'G6_SCHEMA_READ_CONTEXT = {"target": "en2-g6-decision-schema"}\n'
            'P1_MIGRATION_REGISTRY_INTENT = "EN2_P1_MIGRATION_REGISTRY_READ"\n'
            'P1_MIGRATION_REGISTRY_CONTEXT = {"target": "en2-p1-migration-registry"}\n',
            "p1_constants",
        )
        parse_anchor = (
            '    if job["intent_code"] == G6_SCHEMA_READ_INTENT:\n'
            '        if job["context"] != G6_SCHEMA_READ_CONTEXT:\n'
            '            return None\n'
            '        return job\n'
            '    if job["intent_code"] == G6_DECISION_ABSORPTION_INTENT:\n'
        )
        parse_replacement = (
            '    if job["intent_code"] == G6_SCHEMA_READ_INTENT:\n'
            '        if job["context"] != G6_SCHEMA_READ_CONTEXT:\n'
            '            return None\n'
            '        return job\n'
            '    if job["intent_code"] == P1_MIGRATION_REGISTRY_INTENT:\n'
            '        if job["context"] != P1_MIGRATION_REGISTRY_CONTEXT:\n'
            '            return None\n'
            '        return job\n'
            '    if job["intent_code"] == G6_DECISION_ABSORPTION_INTENT:\n'
        )
        inbox = replace_once(inbox, parse_anchor, parse_replacement, "p1_parse")
        execute_anchor = (
            '    if job["intent_code"] == G6_DECISION_ABSORPTION_INTENT:\n'
            '        try:\n'
            '            payload = command_port.execute_en2_g6_decision_absorption_canary_v1(job["id"])\n'
            '            return _completed(job, started, {"status": "PASS", **payload})\n'
            '        except command_port.CommandPortError as exc:\n'
            '            return _failed(job, started, str(exc))\n'
            '    if job["intent_code"] == SELF_UPDATE_INTENT:\n'
        )
        execute_replacement = (
            '    if job["intent_code"] == G6_DECISION_ABSORPTION_INTENT:\n'
            '        try:\n'
            '            payload = command_port.execute_en2_g6_decision_absorption_canary_v1(job["id"])\n'
            '            return _completed(job, started, {"status": "PASS", **payload})\n'
            '        except command_port.CommandPortError as exc:\n'
            '            return _failed(job, started, str(exc))\n'
            '    if job["intent_code"] == P1_MIGRATION_REGISTRY_INTENT:\n'
            '        try:\n'
            '            payload = command_port.read_en2_p1_migration_registry_v1(job["id"])\n'
            '            return _completed(job, started, {"status": "PASS", **payload})\n'
            '        except command_port.CommandPortError as exc:\n'
            '            return _failed(job, started, str(exc))\n'
            '    if job["intent_code"] == SELF_UPDATE_INTENT:\n'
        )
        inbox = replace_once(inbox, execute_anchor, execute_replacement, "p1_execute")
        ISSUE_INBOX.write_text(inbox, encoding="utf-8")

    runtime_files = {
        "bridge_worker.py": BOOTSTRAP / "bridge_worker.py",
        "command_port.py": BOOTSTRAP / "command_port.py",
        "issue_inbox.py": BOOTSTRAP / "issue_inbox.py",
    }
    files = {
        name: {
            "path": f".elan-vps-bridge/bootstrap/{name}",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for name, path in runtime_files.items()
    }
    payload = {
        "files": files,
        "release_id": "bridge-en2-p1-registry-read-20260903-v1",
        "schema_version": "1.0",
    }
    MANIFEST.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print("MANIFEST_SHA256=" + hashlib.sha256(MANIFEST.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
