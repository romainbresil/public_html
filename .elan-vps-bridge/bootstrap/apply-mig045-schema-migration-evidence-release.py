#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / ".elan-vps-bridge" / "bootstrap"
COMMAND_PORT = BOOTSTRAP / "command_port.py"
ISSUE_INBOX = BOOTSTRAP / "issue_inbox.py"
MANIFEST = BOOTSTRAP / "runtime-manifest.json"

RELEASE_ID = "bridge-mig045-schema-migration-evidence-20260904-v1"

CONSTANT_ANCHOR = 'READ_STATUS_TEMPLATE = "en029_m6_schema_migrations_v1"\n'
CONSTANT_BLOCK = '''READ_STATUS_TEMPLATE = "en029_m6_schema_migrations_v1"
SCHEMA_MIGRATION_EVIDENCE_CONTRACT = "schema_migration_membership_v1"
SCHEMA_MIGRATION_EVIDENCE_IDS = (
    "EN033_M1_MIG042_001",
    "EN033_M1_MIG042_002",
)
SCHEMA_MIGRATION_EVIDENCE_PUBLIC_FIELDS = (
    "migration_id",
    "description",
    "applied_at",
)
SCHEMA_MIGRATION_EVIDENCE_SOURCE_FIELDS = {
    "kind",
    "migration_id",
    "description",
    "applied_at",
}
'''

READ_FUNCTION = r'''def _project_schema_migration_membership_v1(values: object, requested_ids: object) -> dict:
    if (
        not isinstance(requested_ids, list)
        or len(requested_ids) < 1
        or len(requested_ids) > 2
        or tuple(requested_ids) != SCHEMA_MIGRATION_EVIDENCE_IDS
    ):
        raise CommandPortError("schema_migration_evidence_requested_ids_invalid")
    if not isinstance(values, list):
        raise CommandPortError("schema_migration_evidence_values_invalid")

    matched_by_id = {}
    requested = set(requested_ids)
    for raw in values:
        if not isinstance(raw, str) or raw.endswith("...[truncated]"):
            raise CommandPortError("schema_migration_evidence_value_invalid")
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CommandPortError("schema_migration_evidence_json_invalid") from exc
        if (
            not isinstance(row, dict)
            or set(row) != SCHEMA_MIGRATION_EVIDENCE_SOURCE_FIELDS
            or row.get("kind") != "migration"
            or not isinstance(row.get("migration_id"), str)
            or not isinstance(row.get("description"), str)
            or not isinstance(row.get("applied_at"), str)
        ):
            raise CommandPortError("schema_migration_evidence_source_contract_invalid")
        migration_id = row["migration_id"]
        if migration_id not in requested:
            continue
        if migration_id in matched_by_id:
            raise CommandPortError("schema_migration_evidence_duplicate_id")
        matched_by_id[migration_id] = {
            field: row[field]
            for field in SCHEMA_MIGRATION_EVIDENCE_PUBLIC_FIELDS
        }

    return {
        "evidence_contract": SCHEMA_MIGRATION_EVIDENCE_CONTRACT,
        "requested_ids": list(requested_ids),
        "matched_rows": [
            matched_by_id[migration_id]
            for migration_id in requested_ids
            if migration_id in matched_by_id
        ],
        "missing_ids": [
            migration_id
            for migration_id in requested_ids
            if migration_id not in matched_by_id
        ],
    }


def read_en_core_status_v1(
    request_id: str,
    request_fn: Callable[[dict], dict] = broker_request,
    *,
    evidence_contract: str | None = None,
    requested_ids: list[str] | None = None,
) -> dict:
    evidence_requested = evidence_contract is not None or requested_ids is not None
    if evidence_requested:
        if evidence_contract != SCHEMA_MIGRATION_EVIDENCE_CONTRACT:
            raise CommandPortError("schema_migration_evidence_contract_invalid")
        if (
            not isinstance(requested_ids, list)
            or len(requested_ids) < 1
            or len(requested_ids) > 2
            or tuple(requested_ids) != SCHEMA_MIGRATION_EVIDENCE_IDS
        ):
            raise CommandPortError("schema_migration_evidence_requested_ids_invalid")

    key = _safe_key(request_id)
    prepared = request_fn({
        "operation": "prepare_procedure",
        "mission_id": "EN-033/M1",
        "work_id": "SPRINT-PRO-G1",
        "technical_authority": "JA-023",
        "idempotency_key": f"bridge-g1-read-{key}",
        "procedure": {
            "procedure_id": f"bridge-g1-read-{key}",
            "title": "Bridge read-only EN Core status",
            "run_budget_seconds": 60,
            "steps": [{
                "step_id": "read-en-core-status-source",
                "primitive": "postgres_query_template",
                "args": {"profile": "business", "template": READ_STATUS_TEMPLATE, "parameters": []},
                "timeout_seconds": 30,
            }],
        },
    })
    plan = prepared.get("plan")
    if not isinstance(plan, dict) or plan.get("risk") != "read_only":
        raise CommandPortError("broker_plan_not_read_only")
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
        raise CommandPortError("broker_read_failed")
    steps = receipt.get("steps")
    if not isinstance(steps, list) or len(steps) != 1 or not isinstance(steps[0], dict):
        raise CommandPortError("broker_read_receipt_invalid")
    result = steps[0].get("result")
    if not isinstance(result, dict) or result.get("template") != READ_STATUS_TEMPLATE:
        raise CommandPortError("broker_read_result_invalid")
    latest = None
    values = result.get("values")
    if isinstance(values, list) and values:
        try:
            parsed = json.loads(values[-1])
            if isinstance(parsed, dict):
                latest = parsed.get("migration_id")
        except (TypeError, json.JSONDecodeError):
            latest = None

    summary = {
        "status": "succeeded",
        "execution_class": "read_only",
        "template": READ_STATUS_TEMPLATE,
        "rows": result.get("rows"),
        "sha256": result.get("sha256"),
        "latest_migration": latest,
        "run_id": receipt.get("run_id"),
        "replayed": bool(receipt.get("replayed")),
    }
    if not evidence_requested:
        return summary

    evidence = _project_schema_migration_membership_v1(values, requested_ids)
    bounded_receipt = {
        **summary,
        "database_profile": "business",
        "surface": "elan_naturel.schema_migrations",
        "free_sql": False,
        "external_action_allowed": False,
        **evidence,
    }
    canonical = json.dumps(
        bounded_receipt,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    bounded_receipt["receipt_sha256"] = hashlib.sha256(canonical).hexdigest()
    return bounded_receipt
'''

ISSUE_CONSTANT_ANCHOR = 'SPRINT_PRO_READ_INTENT = "EN_CORE_STATUS_READ"\n'
ISSUE_CONSTANT_BLOCK = '''SPRINT_PRO_READ_INTENT = "EN_CORE_STATUS_READ"
SPRINT_PRO_SCHEMA_MIGRATION_EVIDENCE_CONTEXT = {
    "target": "en-core",
    "evidence_contract": command_port.SCHEMA_MIGRATION_EVIDENCE_CONTRACT,
    "requested_ids": list(command_port.SCHEMA_MIGRATION_EVIDENCE_IDS),
}
'''

ISSUE_PARSE_OLD = '''    if job["intent_code"] == SPRINT_PRO_READ_INTENT:\n        if job["context"] != {"target": "en-core"}:\n            return None\n        return job\n'''
ISSUE_PARSE_NEW = '''    if job["intent_code"] == SPRINT_PRO_READ_INTENT:\n        if job["context"] == {"target": "en-core"}:\n            return job\n        if job["context"] == SPRINT_PRO_SCHEMA_MIGRATION_EVIDENCE_CONTEXT:\n            return job\n        return None\n'''

ISSUE_EXEC_OLD = '''    if job["intent_code"] == SPRINT_PRO_READ_INTENT:\n        try:\n            payload = command_port.read_en_core_status_v1(job["id"])\n            return _completed(job, started, {"status": "HEALTHY", **payload})\n        except command_port.CommandPortError as exc:\n            return _failed(job, started, str(exc))\n'''
ISSUE_EXEC_NEW = '''    if job["intent_code"] == SPRINT_PRO_READ_INTENT:\n        try:\n            if job["context"] == SPRINT_PRO_SCHEMA_MIGRATION_EVIDENCE_CONTEXT:\n                payload = command_port.read_en_core_status_v1(\n                    job["id"],\n                    evidence_contract=job["context"]["evidence_contract"],\n                    requested_ids=job["context"]["requested_ids"],\n                )\n            else:\n                payload = command_port.read_en_core_status_v1(job["id"])\n            return _completed(job, started, {"status": "HEALTHY", **payload})\n        except command_port.CommandPortError as exc:\n            return _failed(job, started, str(exc))\n'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}_count_invalid:{count}")
    return text.replace(old, new, 1)


def main() -> int:
    command = COMMAND_PORT.read_text(encoding="utf-8")
    command = replace_once(command, CONSTANT_ANCHOR, CONSTANT_BLOCK, "constant_anchor")
    start_marker = "def read_en_core_status_v1("
    end_marker = "\n\ndef build_en2_g4_canary_payload_v1"
    if command.count(start_marker) != 1 or command.count(end_marker) != 1:
        raise SystemExit("read_function_marker_invalid")
    start = command.index(start_marker)
    end = command.index(end_marker, start)
    command = command[:start] + READ_FUNCTION + command[end:]
    COMMAND_PORT.write_text(command, encoding="utf-8")

    inbox = ISSUE_INBOX.read_text(encoding="utf-8")
    inbox = replace_once(inbox, ISSUE_CONSTANT_ANCHOR, ISSUE_CONSTANT_BLOCK, "issue_constant_anchor")
    inbox = replace_once(inbox, ISSUE_PARSE_OLD, ISSUE_PARSE_NEW, "issue_parse")
    inbox = replace_once(inbox, ISSUE_EXEC_OLD, ISSUE_EXEC_NEW, "issue_exec")
    ISSUE_INBOX.write_text(inbox, encoding="utf-8")

    runtime_files = {
        "bridge_worker.py": BOOTSTRAP / "bridge_worker.py",
        "command_port.py": COMMAND_PORT,
        "issue_inbox.py": ISSUE_INBOX,
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
        "release_id": RELEASE_ID,
        "schema_version": "1.0",
    }
    MANIFEST.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print("MANIFEST_SHA256=" + hashlib.sha256(MANIFEST.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
