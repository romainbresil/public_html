from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMAND_PORT = ROOT / "command_port.py"
ISSUE_INBOX = ROOT / "issue_inbox.py"
BRIDGE_WORKER = ROOT / "bridge_worker.py"
MANIFEST = ROOT / "runtime-manifest.json"
CONTROL_ROOT = ROOT.parent
MIGRATION = CONTROL_ROOT / "packages/en2-g6/20260903_en2_g6_001_decision_absorption_canary.sql"
ROLLBACK = CONTROL_ROOT / "packages/en2-g6/20260903_en2_g6_001_decision_absorption_canary.rollback.sql"
BASE_COMMAND_SHA256 = "778bf8b7199ff9659112ed5ed05629606be20acb0f93f8cdc588629f60508d8a"
BASE_ISSUE_SHA256 = "0c20b527f8fb0333becbf7f81df4b564861629c956bf45c8b93443bac3740769"
BASE_BRIDGE_SHA256 = "7d7f7839cf0c5931bf8af29c78adef59a4e1a0bab10dfb064150942975635cd4"
MIGRATION_SHA256 = "87c2553e681d03fbf660ac2c342e6154dc9e8d12a9f8cc46400a1f70a1b37af3"
ROLLBACK_SHA256 = "07227ee51e9c05a5c9c26d10beaffb26139202cfc3014a4067be79b31b3021a0"
RELEASE_ID = "en2-g6-decision-absorption-0cd2ec29"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_packages() -> None:
    if sha(MIGRATION) != MIGRATION_SHA256:
        raise RuntimeError(f"g6_migration_sha256_mismatch:{sha(MIGRATION)}")
    if sha(ROLLBACK) != ROLLBACK_SHA256:
        raise RuntimeError(f"g6_rollback_sha256_mismatch:{sha(ROLLBACK)}")


def patch_command_port() -> None:
    source = COMMAND_PORT.read_text(encoding="utf-8")
    marker = "def execute_en2_g6_decision_absorption_canary_v1("
    if marker in source:
        return
    observed = sha(COMMAND_PORT)
    if observed != BASE_COMMAND_SHA256:
        raise RuntimeError(f"unexpected_command_baseline:{observed}")

    extension = r'''

# EN2-G6 bounded synthetic decision-absorption canary.
G6_EXECUTION_CLASS = "reversible_technical_change"
G6_EXPECTED_MIGRATION = "EN2_G6_001"
G6_MIGRATION_PATH = ".elan-vps-bridge/packages/en2-g6/20260903_en2_g6_001_decision_absorption_canary.sql"
G6_ROLLBACK_PATH = ".elan-vps-bridge/packages/en2-g6/20260903_en2_g6_001_decision_absorption_canary.rollback.sql"
G6_MIGRATION_SHA256 = "87c2553e681d03fbf660ac2c342e6154dc9e8d12a9f8cc46400a1f70a1b37af3"
G6_ROLLBACK_SHA256 = "07227ee51e9c05a5c9c26d10beaffb26139202cfc3014a4067be79b31b3021a0"
G6_SYNTHETIC_DOSSIER_LINEAGE_TEMPLATE = "en029_m6_chatgpt_voice_register_v1"
G6_DECISION_FACADE = "cockpit_business_command_v1"
G6_HISTORY_EVENT = "DECISION_RESOLVED"


def _verified_g6_package(fetch_fn):
    try:
        migration_raw = fetch_fn(G6_MIGRATION_PATH)
        rollback_raw = fetch_fn(G6_ROLLBACK_PATH)
    except CommandPortError:
        raise
    except Exception as exc:
        raise CommandPortError("g6_package_fetch_failed") from exc
    if not isinstance(migration_raw, bytes) or not isinstance(rollback_raw, bytes):
        raise CommandPortError("g6_package_fetch_invalid")
    if len(migration_raw) > _MAX_PACKAGE_BYTES or len(rollback_raw) > _MAX_PACKAGE_BYTES:
        raise CommandPortError("g6_package_too_large")
    if hashlib.sha256(migration_raw).hexdigest() != G6_MIGRATION_SHA256:
        raise CommandPortError("g6_migration_sha256_mismatch")
    if hashlib.sha256(rollback_raw).hexdigest() != G6_ROLLBACK_SHA256:
        raise CommandPortError("g6_rollback_sha256_mismatch")
    try:
        return migration_raw.decode("utf-8"), rollback_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CommandPortError("g6_package_not_utf8") from exc


def _g6_proof_from_migration_values(values):
    if not isinstance(values, list) or not values:
        raise CommandPortError("g6_proof_values_missing")
    matches = []
    for value in values:
        if not isinstance(value, str):
            continue
        try:
            row = json.loads(value)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("migration_id") == G6_EXPECTED_MIGRATION:
            matches.append(row)
    if len(matches) != 1:
        raise CommandPortError("g6_proof_migration_row_mismatch")
    description = matches[0].get("description")
    if not isinstance(description, str):
        raise CommandPortError("g6_proof_description_missing")
    try:
        proof = json.loads(description)
    except json.JSONDecodeError as exc:
        raise CommandPortError("g6_proof_description_invalid") from exc
    if not isinstance(proof, dict):
        raise CommandPortError("g6_proof_description_invalid")
    required = {
        "gate": "EN2-G6",
        "fixture": "synthetic_only",
        "active_queue_removed": True,
        "historical_retained": True,
        "resolution_event_count": 1,
        "idempotent_replay": True,
        "external_action_allowed": False,
    }
    for key, expected in required.items():
        if proof.get(key) != expected:
            raise CommandPortError(f"g6_proof_contract_mismatch:{key}")
    for key in ("dossier_id", "decision_id"):
        if not isinstance(proof.get(key), str) or not proof[key]:
            raise CommandPortError(f"g6_proof_identifier_missing:{key}")
    return proof


def execute_en2_g6_decision_absorption_canary_v1(
    request_id: str,
    request_fn=broker_request,
    fetch_fn=_fetch_control_path,
) -> dict:
    request_key = _safe_key(request_id).lower()
    migration_text, rollback_text = _verified_g6_package(fetch_fn)

    staged_migration = request_fn({
        "operation": "stage_text",
        "content": migration_text,
        "expected_sha256": G6_MIGRATION_SHA256,
        "media_type": "text/plain",
        "label": f"en2-g6-migration-{request_key}",
    })
    staged_rollback = request_fn({
        "operation": "stage_text",
        "content": rollback_text,
        "expected_sha256": G6_ROLLBACK_SHA256,
        "media_type": "text/plain",
        "label": f"en2-g6-rollback-{request_key}",
    })
    migration_artifact_id = _artifact_id(staged_migration)
    rollback_artifact_id = _artifact_id(staged_rollback)

    prepared = request_fn({
        "operation": "prepare_procedure",
        "mission_id": "EN2-G6",
        "work_id": "DECISION-ABSORPTION-PROD",
        "technical_authority": "JA-023",
        "idempotency_key": f"en2-g6-decision-absorption-{request_key}",
        "procedure": {
            "procedure_id": f"en2-g6-decision-absorption-{request_key}",
            "title": "EN2-G6 bounded synthetic decision absorption canary",
            "run_budget_seconds": 900,
            "steps": [
                {
                    "step_id": "backup",
                    "primitive": "postgres_backup",
                    "args": {"profile": "business", "label": f"en2-g6-pre-{request_key}"},
                    "timeout_seconds": 300,
                    "retry": 0,
                    "resource_lock": "postgres-business-en2-g6",
                },
                {
                    "step_id": "preflight",
                    "primitive": "postgres_migration_preflight",
                    "args": {
                        "profile": "business",
                        "artifact_id": migration_artifact_id,
                        "rollback_artifact_id": rollback_artifact_id,
                    },
                    "timeout_seconds": 120,
                    "retry": 0,
                    "resource_lock": "postgres-business-en2-g6",
                },
                {
                    "step_id": "apply",
                    "primitive": "postgres_migration_apply",
                    "args": {
                        "profile": "business",
                        "artifact_id": migration_artifact_id,
                        "rollback_artifact_id": rollback_artifact_id,
                        "expected_migration": G6_EXPECTED_MIGRATION,
                    },
                    "timeout_seconds": 300,
                    "retry": 0,
                    "resource_lock": "postgres-business-en2-g6",
                },
                {
                    "step_id": "proof-read",
                    "primitive": "postgres_query_template",
                    "args": {
                        "profile": "business",
                        "template": READ_STATUS_TEMPLATE,
                        "parameters": [],
                    },
                    "timeout_seconds": 60,
                    "retry": 0,
                    "resource_lock": "postgres-business-en2-g6",
                },
            ],
        },
    })
    plan = prepared.get("plan")
    if not isinstance(plan, dict) or plan.get("risk") not in {"reversible", G6_EXECUTION_CLASS}:
        raise CommandPortError("broker_g6_plan_not_reversible")

    executed = request_fn({
        "operation": "start_run",
        "plan_id": plan.get("plan_id"),
        "execution_token": plan.get("execution_token"),
        "procedure_sha256": plan.get("procedure_sha256"),
        "execution_class": G6_EXECUTION_CLASS,
        "mode": "sync",
    })
    receipt = executed.get("receipt")
    if (
        not isinstance(receipt, dict)
        or receipt.get("status") != "succeeded"
        or receipt.get("execution_class") != G6_EXECUTION_CLASS
    ):
        raise CommandPortError("broker_g6_run_failed")

    steps = receipt.get("steps")
    if not isinstance(steps, list) or len(steps) != 4:
        raise CommandPortError("broker_g6_receipt_invalid")
    by_id = {
        step.get("step_id"): step
        for step in steps
        if isinstance(step, dict) and isinstance(step.get("step_id"), str)
    }
    if set(by_id) != {"backup", "preflight", "apply", "proof-read"}:
        raise CommandPortError("broker_g6_receipt_step_mismatch")
    if any(by_id[name].get("status") != "success" for name in by_id):
        raise CommandPortError("broker_g6_step_failed")

    backup = by_id["backup"].get("result")
    preflight = by_id["preflight"].get("result")
    apply_result = by_id["apply"].get("result")
    proof_result = by_id["proof-read"].get("result")
    if not isinstance(backup, dict):
        raise CommandPortError("broker_g6_backup_readback_invalid")
    if (
        not isinstance(preflight, dict)
        or preflight.get("free_sql") is not False
        or preflight.get("rollback_present") is not True
    ):
        raise CommandPortError("broker_g6_preflight_readback_invalid")
    if (
        not isinstance(apply_result, dict)
        or apply_result.get("artifact_sha256") != G6_MIGRATION_SHA256
    ):
        raise CommandPortError("broker_g6_apply_readback_invalid")
    if (
        not isinstance(proof_result, dict)
        or proof_result.get("template") != READ_STATUS_TEMPLATE
    ):
        raise CommandPortError("broker_g6_proof_readback_invalid")
    proof = _g6_proof_from_migration_values(proof_result.get("values"))

    return {
        "status": "succeeded",
        "execution_class": G6_EXECUTION_CLASS,
        "expected_migration": G6_EXPECTED_MIGRATION,
        "migration_sha256": G6_MIGRATION_SHA256,
        "rollback_sha256": G6_ROLLBACK_SHA256,
        "run_id": receipt.get("run_id"),
        "backup": backup,
        "preflight": preflight,
        "apply": apply_result,
        "proof": proof,
        "transaction_assertions_embedded": True,
        "free_sql": False,
        "external_action_allowed": False,
    }
'''
    COMMAND_PORT.write_text(source.rstrip() + "\n" + extension.lstrip(), encoding="utf-8")


def patch_issue_inbox() -> None:
    source = ISSUE_INBOX.read_text(encoding="utf-8")
    if 'G6_DECISION_ABSORPTION_INTENT = "EN2_G6_DECISION_ABSORPTION_CANARY"' in source:
        return
    observed = sha(ISSUE_INBOX)
    if observed != BASE_ISSUE_SHA256:
        raise RuntimeError(f"unexpected_issue_baseline:{observed}")

    constants_marker = 'G6_SCHEMA_READ_CONTEXT = {"target": "en2-g6-decision-schema"}\n'
    constants = '''G6_DECISION_ABSORPTION_INTENT = "EN2_G6_DECISION_ABSORPTION_CANARY"\nG6_DECISION_ABSORPTION_CONTEXT = {\n    "target": "en2-g6-decision-absorption",\n    "synthetic": True,\n    "idempotency_key": "en2-g6-decision-resolved-20260903-v1",\n}\n'''
    if constants_marker not in source:
        raise RuntimeError("g6_issue_constants_marker_missing")
    source = source.replace(constants_marker, constants_marker + constants, 1)

    parser_marker = '''    if job["intent_code"] == G6_SCHEMA_READ_INTENT:\n        if job["context"] != G6_SCHEMA_READ_CONTEXT:\n            return None\n        return job\n'''
    parser_extension = '''    if job["intent_code"] == G6_DECISION_ABSORPTION_INTENT:\n        if job["context"] != G6_DECISION_ABSORPTION_CONTEXT:\n            return None\n        return job\n'''
    if parser_marker not in source:
        raise RuntimeError("g6_issue_parser_marker_missing")
    source = source.replace(parser_marker, parser_marker + parser_extension, 1)

    execute_marker = '''    if job["intent_code"] == G6_SCHEMA_READ_INTENT:\n        try:\n            payload = command_port.read_en2_g6_decision_schema_v1(job["id"])\n            return _completed(job, started, {"status": "PASS", **payload})\n        except command_port.CommandPortError as exc:\n            return _failed(job, started, str(exc))\n'''
    execute_extension = '''    if job["intent_code"] == G6_DECISION_ABSORPTION_INTENT:\n        try:\n            payload = command_port.execute_en2_g6_decision_absorption_canary_v1(job["id"])\n            return _completed(job, started, {"status": "PASS", **payload})\n        except command_port.CommandPortError as exc:\n            return _failed(job, started, str(exc))\n'''
    if execute_marker not in source:
        raise RuntimeError("g6_issue_execute_marker_missing")
    source = source.replace(execute_marker, execute_marker + execute_extension, 1)
    ISSUE_INBOX.write_text(source, encoding="utf-8")


def main() -> int:
    verify_packages()
    if sha(BRIDGE_WORKER) != BASE_BRIDGE_SHA256:
        raise RuntimeError(f"unexpected_bridge_baseline:{sha(BRIDGE_WORKER)}")
    patch_command_port()
    patch_issue_inbox()
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
