#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / ".elan-vps-bridge" / "bootstrap"
COMMAND_PORT = BOOTSTRAP / "command_port.py"
MANIFEST = BOOTSTRAP / "runtime-manifest.json"

P1_MARKER = "# EN2-P1 bounded canonical migration-registry read."

P1_SECTION = r'''# EN2-P1 bounded canonical migration-registry read.
# The canonical read-all call is preserved. Mission Control sanitizes individual
# strings at 4096 bytes, so a large registry JSON can arrive intentionally
# truncated. In that exact case, the four P1 preflight identities are recovered
# with the already deployed single-entry MIG-037 template. No caller SQL exists.
P1_MIGRATION_REGISTRY_TEMPLATE = "en033_m1_mig037_registry_read_all_v1"
P1_MIGRATION_REGISTRY_ENTRY_TEMPLATE = "en033_m1_mig037_registry_read_v1"
P1_MIGRATION_REGISTRY_IDS = ("MIG-044", "MIG-045", "MIG-046", "MIG-050")


def _p1_registry_entry_from_result(result: object, expected_migration_id: str):
    if not isinstance(result, dict) or result.get("template") != P1_MIGRATION_REGISTRY_ENTRY_TEMPLATE:
        raise CommandPortError("broker_p1_registry_entry_result_invalid")
    values = result.get("values")
    if values == []:
        return None
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], str):
        raise CommandPortError("broker_p1_registry_entry_values_invalid")
    raw = values[0]
    if raw.endswith("...[truncated]"):
        raise CommandPortError("broker_p1_registry_entry_truncated")
    try:
        entry = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CommandPortError("broker_p1_registry_entry_json_invalid") from exc
    if not isinstance(entry, dict):
        raise CommandPortError("broker_p1_registry_entry_contract_invalid")
    if entry.get("migration_id") != expected_migration_id:
        raise CommandPortError("broker_p1_registry_entry_identity_mismatch")
    return entry


def read_en2_p1_migration_registry_v1(
    request_id: str,
    request_fn: Callable[[dict], dict] = broker_request,
) -> dict:
    key = _safe_key(request_id).lower()
    steps = [{
        "step_id": "migration-registry-read-all",
        "primitive": "postgres_query_template",
        "args": {
            "profile": "business",
            "template": P1_MIGRATION_REGISTRY_TEMPLATE,
            "parameters": [],
        },
        "timeout_seconds": 30,
    }]
    for migration_id in P1_MIGRATION_REGISTRY_IDS:
        steps.append({
            "step_id": f"migration-registry-read-{migration_id.lower()}",
            "primitive": "postgres_query_template",
            "args": {
                "profile": "business",
                "template": P1_MIGRATION_REGISTRY_ENTRY_TEMPLATE,
                "parameters": [migration_id],
            },
            "timeout_seconds": 30,
        })

    prepared = request_fn({
        "operation": "prepare_procedure",
        "mission_id": "EN2-P1",
        "work_id": "MIGRATION-REGISTRY-PREFLIGHT-READ",
        "technical_authority": "JA-023",
        "idempotency_key": f"en2-p1-migration-registry-read-{key}",
        "procedure": {
            "procedure_id": f"en2-p1-migration-registry-read-{key}",
            "title": "EN2-P1 canonical registry read with bounded sanitizer-safe recovery",
            "run_budget_seconds": 180,
            "steps": steps,
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
    receipt_steps = receipt.get("steps")
    if not isinstance(receipt_steps, list) or len(receipt_steps) != 5:
        raise CommandPortError("broker_p1_registry_receipt_invalid")
    by_id = {
        step.get("step_id"): step
        for step in receipt_steps
        if isinstance(step, dict) and isinstance(step.get("step_id"), str)
    }
    expected_step_ids = {"migration-registry-read-all"} | {
        f"migration-registry-read-{migration_id.lower()}"
        for migration_id in P1_MIGRATION_REGISTRY_IDS
    }
    if set(by_id) != expected_step_ids:
        raise CommandPortError("broker_p1_registry_step_mismatch")
    if any(by_id[step_id].get("status") != "success" for step_id in expected_step_ids):
        raise CommandPortError("broker_p1_registry_step_invalid")

    read_all_result = by_id["migration-registry-read-all"].get("result")
    if not isinstance(read_all_result, dict) or read_all_result.get("template") != P1_MIGRATION_REGISTRY_TEMPLATE:
        raise CommandPortError("broker_p1_registry_result_invalid")
    read_all_values = read_all_result.get("values")
    if not isinstance(read_all_values, list) or len(read_all_values) != 1 or not isinstance(read_all_values[0], str):
        raise CommandPortError("broker_p1_registry_values_invalid")
    read_all_raw = read_all_values[0]
    complete_entries = None
    if read_all_raw.endswith("...[truncated]"):
        read_all_transport = "SANITIZER_TRUNCATED_BOUNDED_FALLBACK"
    else:
        try:
            complete_entries = json.loads(read_all_raw)
        except json.JSONDecodeError as exc:
            raise CommandPortError("broker_p1_registry_json_invalid") from exc
        if not isinstance(complete_entries, list) or any(not isinstance(item, dict) for item in complete_entries):
            raise CommandPortError("broker_p1_registry_contract_invalid")
        read_all_transport = "COMPLETE_CROSSCHECKED"

    entries = []
    missing_migration_ids = []
    bounded_by_id = {}
    for migration_id in P1_MIGRATION_REGISTRY_IDS:
        entry = _p1_registry_entry_from_result(
            by_id[f"migration-registry-read-{migration_id.lower()}"].get("result"),
            migration_id,
        )
        bounded_by_id[migration_id] = entry
        if entry is None:
            missing_migration_ids.append(migration_id)
        else:
            entries.append(entry)

    if complete_entries is not None:
        full_by_id = {
            item.get("migration_id"): item
            for item in complete_entries
            if isinstance(item.get("migration_id"), str)
        }
        for migration_id in P1_MIGRATION_REGISTRY_IDS:
            if full_by_id.get(migration_id) != bounded_by_id[migration_id]:
                raise CommandPortError("broker_p1_registry_crosscheck_mismatch")

    return {
        "status": "succeeded",
        "execution_class": "read_only",
        "template": P1_MIGRATION_REGISTRY_TEMPLATE,
        "entry_template": P1_MIGRATION_REGISTRY_ENTRY_TEMPLATE,
        "canonical_read_all_invoked": True,
        "read_all_transport": read_all_transport,
        "entries": entries,
        "missing_migration_ids": missing_migration_ids,
        "run_id": receipt.get("run_id"),
        "replayed": bool(receipt.get("replayed")),
        "free_sql": False,
        "external_action_allowed": False,
    }
'''


def main() -> int:
    command = COMMAND_PORT.read_text(encoding="utf-8")
    if command.count(P1_MARKER) != 1:
        raise SystemExit(f"p1_marker_count_invalid:{command.count(P1_MARKER)}")
    prefix = command.split(P1_MARKER, 1)[0].rstrip()
    COMMAND_PORT.write_text(prefix + "\n" + P1_SECTION, encoding="utf-8")

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
        "release_id": "bridge-en2-p1-registry-read-20260903-v2",
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
