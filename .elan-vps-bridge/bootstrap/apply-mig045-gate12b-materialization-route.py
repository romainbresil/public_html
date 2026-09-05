#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
BRIDGE_ROOT = ROOT.parent
ISSUE = ROOT / "issue_inbox.py"
COMMAND = ROOT / "command_port.py"
MANIFEST = ROOT / "runtime-manifest.json"
RUNTIME_FILES = ("issue_inbox.py", "bridge_worker.py", "command_port.py")
RELEASE_ID = "bridge-mig045-gate12b-plan-risk-contract-fix-20260905-v1"
INTENT = "MIG045_GATE12B_TECHNICAL_MATERIALIZE_V1"
MIGRATION_RELATIVE_PATH = ".elan-vps-bridge/packages/mig045-gate12b/20260905_en033_m1_mig045_gate12b_proof_ledger.sql"
ROLLBACK_RELATIVE_PATH = ".elan-vps-bridge/packages/mig045-gate12b/20260905_en033_m1_mig045_gate12b_proof_ledger.rollback.sql"
MIGRATION_FILE = BRIDGE_ROOT / "packages/mig045-gate12b/20260905_en033_m1_mig045_gate12b_proof_ledger.sql"
ROLLBACK_FILE = BRIDGE_ROOT / "packages/mig045-gate12b/20260905_en033_m1_mig045_gate12b_proof_ledger.rollback.sql"
MIGRATION_SHA256 = "093fd0ff7898113219c148042f84121783d647f1a97806ea44110b9ce7aeec2a"
ROLLBACK_SHA256 = "c9169ef827336ddd9db96979c54cd97cbeaef020be1da23bd1948d34ce2cdbcb"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}_anchor_invalid:{count}")
    return text.replace(old, new)


def verify_packages() -> None:
    observed_migration = hashlib.sha256(MIGRATION_FILE.read_bytes()).hexdigest()
    observed_rollback = hashlib.sha256(ROLLBACK_FILE.read_bytes()).hexdigest()
    if observed_migration != MIGRATION_SHA256:
        raise SystemExit(f"migration_sha256_mismatch:{observed_migration}")
    if observed_rollback != ROLLBACK_SHA256:
        raise SystemExit(f"rollback_sha256_mismatch:{observed_rollback}")


def patch_issue_inbox() -> None:
    text = ISSUE.read_text(encoding="utf-8")
    if INTENT in text:
        raise SystemExit("mig045_gate12b_materialization_intent_already_present")

    constants_anchor = '''MIG045_GATE12B_PREFLIGHT_INTENT = "MIG045_GATE12B_TECHNICAL_PREFLIGHT_FREEZE_V1"\nMIG045_GATE12B_PREFLIGHT_CONTEXT = {"target": "mig045-gate12b-technical-preflight-freeze"}\n'''
    constants = '''MIG045_GATE12B_PREFLIGHT_INTENT = "MIG045_GATE12B_TECHNICAL_PREFLIGHT_FREEZE_V1"\nMIG045_GATE12B_PREFLIGHT_CONTEXT = {"target": "mig045-gate12b-technical-preflight-freeze"}\nMIG045_GATE12B_TECHNICAL_MATERIALIZE_INTENT = "MIG045_GATE12B_TECHNICAL_MATERIALIZE_V1"\nMIG045_GATE12B_TECHNICAL_MATERIALIZE_TARGET = "mig045-gate12b-technical-materialize"\n'''
    text = replace_once(text, constants_anchor, constants, "issue_constants")

    parser_anchor = '''    if job["intent_code"] == MIG045_GATE12B_PREFLIGHT_INTENT:\n        if job["context"] != MIG045_GATE12B_PREFLIGHT_CONTEXT:\n            return None\n        return job\n'''
    parser = '''    if job["intent_code"] == MIG045_GATE12B_TECHNICAL_MATERIALIZE_INTENT:\n        context = job["context"]\n        if not isinstance(context, dict) or set(context) != {"target", "artifact_url"}:\n            return None\n        if context.get("target") != MIG045_GATE12B_TECHNICAL_MATERIALIZE_TARGET:\n            return None\n        try:\n            command_port.validate_mig045_gate12b_technical_artifact_url(context.get("artifact_url"))\n        except command_port.CommandPortError:\n            return None\n        return job\n    if job["intent_code"] == MIG045_GATE12B_PREFLIGHT_INTENT:\n        if job["context"] != MIG045_GATE12B_PREFLIGHT_CONTEXT:\n            return None\n        return job\n'''
    text = replace_once(text, parser_anchor, parser, "issue_parser")

    execute_anchor = '''    if job["intent_code"] == MIG045_GATE12B_PREFLIGHT_INTENT:\n        try:\n            payload = command_port.request_mig045_gate12b_production_proof_freeze()\n'''
    execute = '''    if job["intent_code"] == MIG045_GATE12B_TECHNICAL_MATERIALIZE_INTENT:\n        try:\n            payload = command_port.run_mig045_gate12b_technical_materialization_v1(\n                job["id"],\n                job["context"]["artifact_url"],\n            )\n            return _completed(job, started, {"status": "PASS", **payload})\n        except command_port.CommandPortError as exc:\n            return _failed(job, started, str(exc))\n    if job["intent_code"] == MIG045_GATE12B_PREFLIGHT_INTENT:\n        try:\n            payload = command_port.request_mig045_gate12b_production_proof_freeze()\n'''
    text = replace_once(text, execute_anchor, execute, "issue_execute")
    ISSUE.write_text(text, encoding="utf-8")


def patch_command_port() -> None:
    text = COMMAND.read_text(encoding="utf-8")
    if "MIG045_GATE12B_TECHNICAL_TARGET_VERSION" in text:
        raise SystemExit("mig045_gate12b_materialization_command_surface_already_present")

    block = r'''

# BEGIN MIG045_GATE12B_TECHNICAL_MATERIALIZATION_V1
MIG045_GATE12B_TECHNICAL_TARGET_VERSION = "1.3.52"
MIG045_GATE12B_TECHNICAL_SOURCE_COMMIT = "b8a5672d090fb0ddceb552e5029cf04b736da44d"
MIG045_GATE12B_TRANSPORT_SHA256 = "9fcdc39f7e963b5b352384814130d25d51277b9ba2978970faa7e3e5df531597"
MIG045_GATE12B_TRANSPORT_SIZE = 187942520
MIG045_GATE12B_EXPECTED_MIGRATION = "EN033_M1_MIG045_GATE12B_PROOF_LEDGER_V1"
MIG045_GATE12B_MIGRATION_PATH = ".elan-vps-bridge/packages/mig045-gate12b/20260905_en033_m1_mig045_gate12b_proof_ledger.sql"
MIG045_GATE12B_ROLLBACK_PATH = ".elan-vps-bridge/packages/mig045-gate12b/20260905_en033_m1_mig045_gate12b_proof_ledger.rollback.sql"
MIG045_GATE12B_MIGRATION_SHA256 = "093fd0ff7898113219c148042f84121783d647f1a97806ea44110b9ce7aeec2a"
MIG045_GATE12B_ROLLBACK_SHA256 = "c9169ef827336ddd9db96979c54cd97cbeaef020be1da23bd1948d34ce2cdbcb"
MIG045_GATE12B_TECHNICAL_RESOURCE_LOCK = "postgres-business-en033-mig045-gate12b"
MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS = "reversible_technical_change"


def validate_mig045_gate12b_technical_artifact_url(value: object) -> str:
    if not isinstance(value, str) or len(value) < 32 or len(value) > 4096:
        raise CommandPortError("mig045_gate12b_artifact_url_invalid")
    try:
        parsed = urllib.parse.urlparse(value)
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    except (TypeError, ValueError) as exc:
        raise CommandPortError("mig045_gate12b_artifact_url_invalid") from exc
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if (
        parsed.scheme != "https"
        or not host.endswith(".oaiusercontent.com")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or not path.startswith("/files/")
        or not path.endswith("/raw")
        or len(path) <= len("/files//raw")
        or parsed.fragment
        or query.get("sp") != ["r"]
        or len(query.get("se", [])) != 1
        or not query["se"][0]
        or len(query.get("sig", [])) != 1
        or not query["sig"][0]
    ):
        raise CommandPortError("mig045_gate12b_artifact_url_invalid")
    return value


def _verified_mig045_gate12b_technical_package(
    fetch_fn: Callable[[str], bytes],
) -> tuple[str, str]:
    try:
        migration_raw = fetch_fn(MIG045_GATE12B_MIGRATION_PATH)
        rollback_raw = fetch_fn(MIG045_GATE12B_ROLLBACK_PATH)
    except CommandPortError:
        raise
    except Exception as exc:
        raise CommandPortError("mig045_gate12b_package_fetch_failed") from exc
    if not isinstance(migration_raw, bytes) or not isinstance(rollback_raw, bytes):
        raise CommandPortError("mig045_gate12b_package_bytes_invalid")
    if len(migration_raw) > _MAX_PACKAGE_BYTES or len(rollback_raw) > _MAX_PACKAGE_BYTES:
        raise CommandPortError("mig045_gate12b_package_too_large")
    if hashlib.sha256(migration_raw).hexdigest() != MIG045_GATE12B_MIGRATION_SHA256:
        raise CommandPortError("mig045_gate12b_migration_sha256_mismatch")
    if hashlib.sha256(rollback_raw).hexdigest() != MIG045_GATE12B_ROLLBACK_SHA256:
        raise CommandPortError("mig045_gate12b_rollback_sha256_mismatch")
    try:
        return migration_raw.decode("utf-8"), rollback_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CommandPortError("mig045_gate12b_package_not_utf8") from exc


def _validate_mig045_gate12b_technical_ready_proof(proof: object) -> dict:
    if (
        not isinstance(proof, dict)
        or proof.get("version") != MIG045_GATE12B_TECHNICAL_TARGET_VERSION
        or proof.get("status") not in {"ok", "ready"}
    ):
        raise CommandPortError("mig045_gate12b_ready_proof_invalid")
    for field in ("source_commit", "runtime_source_commit"):
        if field in proof and proof.get(field) != MIG045_GATE12B_TECHNICAL_SOURCE_COMMIT:
            raise CommandPortError("mig045_gate12b_ready_source_commit_mismatch")
    return dict(proof)


def _mig045_gate12b_wait_ready_v1352(timeout_seconds: int = 600) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(
                MIG045_READYZ_URL,
                headers={
                    "User-Agent": "elan-web-vps-bridge-mig045-gate12b/1",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                proof = json.load(response)
            return _validate_mig045_gate12b_technical_ready_proof(proof)
        except (CommandPortError, OSError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(2)
    raise CommandPortError("mig045_gate12b_readiness_timeout")


def _mig045_gate12b_reversible_plan(prepared: object, label: str) -> dict:
    if not isinstance(prepared, dict):
        raise CommandPortError(f"mig045_gate12b_{label}_prepare_invalid")
    plan = prepared.get("plan")
    if (
        not isinstance(plan, dict)
        or plan.get("risk") != MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS
        or not isinstance(plan.get("plan_id"), str)
        or not plan.get("plan_id")
        or not isinstance(plan.get("execution_token"), str)
        or not plan.get("execution_token")
        or not isinstance(plan.get("procedure_sha256"), str)
        or not plan.get("procedure_sha256")
    ):
        raise CommandPortError(f"mig045_gate12b_{label}_plan_not_reversible")
    return plan


def _mig045_gate12b_run_plan(
    request_fn: Callable[[dict], dict],
    plan: dict,
    label: str,
) -> dict:
    executed = request_fn({
        "operation": "start_run",
        "plan_id": plan["plan_id"],
        "execution_token": plan["execution_token"],
        "procedure_sha256": plan["procedure_sha256"],
        "execution_class": MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS,
        "mode": "sync",
    })
    if not isinstance(executed, dict):
        raise CommandPortError(f"mig045_gate12b_{label}_run_invalid")
    receipt = executed.get("receipt")
    if (
        not isinstance(receipt, dict)
        or receipt.get("status") != "succeeded"
        or receipt.get("risk") != MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS
        or receipt.get("execution_class") != MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS
        or not isinstance(receipt.get("run_id"), str)
        or not receipt.get("run_id")
    ):
        raise CommandPortError(f"mig045_gate12b_{label}_run_failed")
    return receipt


def run_mig045_gate12b_technical_materialization_v1(
    request_id: str,
    artifact_url: str,
    request_fn: Callable[[dict], dict] = broker_request,
    fetch_fn: Callable[[str], bytes] = _fetch_control_path,
    ready_fn: Callable[[], dict] = _mig045_gate12b_wait_ready_v1352,
) -> dict:
    request_key = _safe_key(request_id).lower()
    url = validate_mig045_gate12b_technical_artifact_url(artifact_url)

    staged_release = request_fn({
        "operation": "stage_https",
        "url": url,
        "expected_sha256": MIG045_GATE12B_TRANSPORT_SHA256,
        "expected_size_bytes": MIG045_GATE12B_TRANSPORT_SIZE,
        "media_type": "application/zip",
        "label": f"qualified-connector-transfer:elan-vps-{MIG045_GATE12B_TECHNICAL_TARGET_VERSION}",
    })
    release_artifact_id = _artifact_id(staged_release)

    migration_text, rollback_text = _verified_mig045_gate12b_technical_package(fetch_fn)
    staged_migration = request_fn({
        "operation": "stage_text",
        "content": migration_text,
        "expected_sha256": MIG045_GATE12B_MIGRATION_SHA256,
        "media_type": "text/plain",
        "label": f"mig045-gate12b-migration-{request_key}",
    })
    staged_rollback = request_fn({
        "operation": "stage_text",
        "content": rollback_text,
        "expected_sha256": MIG045_GATE12B_ROLLBACK_SHA256,
        "media_type": "text/plain",
        "label": f"mig045-gate12b-rollback-{request_key}",
    })
    migration_artifact_id = _artifact_id(staged_migration)
    rollback_artifact_id = _artifact_id(staged_rollback)

    migration_prepared = request_fn({
        "operation": "prepare_procedure",
        "mission_id": "EN-033/M1",
        "work_id": "MIG045-GATE12B-TECHNICAL-MATERIALIZE",
        "technical_authority": "JA-023",
        "idempotency_key": f"mig045-gate12b-migration-{request_key}",
        "procedure": {
            "procedure_id": f"mig045-gate12b-migration-{request_key}",
            "title": "MIG045 Gate12B bounded PostgreSQL technical migration",
            "run_budget_seconds": 900,
            "steps": [
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
                    "resource_lock": MIG045_GATE12B_TECHNICAL_RESOURCE_LOCK,
                },
                {
                    "step_id": "apply",
                    "primitive": "postgres_migration_apply",
                    "args": {
                        "profile": "business",
                        "artifact_id": migration_artifact_id,
                        "rollback_artifact_id": rollback_artifact_id,
                        "expected_migration": MIG045_GATE12B_EXPECTED_MIGRATION,
                    },
                    "timeout_seconds": 300,
                    "retry": 0,
                    "resource_lock": MIG045_GATE12B_TECHNICAL_RESOURCE_LOCK,
                },
            ],
        },
    })
    migration_plan = _mig045_gate12b_reversible_plan(migration_prepared, "migration")
    migration_receipt = _mig045_gate12b_run_plan(request_fn, migration_plan, "migration")
    migration_steps = migration_receipt.get("steps")
    if not isinstance(migration_steps, list) or len(migration_steps) != 2:
        raise CommandPortError("mig045_gate12b_migration_receipt_invalid")
    by_id = {
        step.get("step_id"): step
        for step in migration_steps
        if isinstance(step, dict) and isinstance(step.get("step_id"), str)
    }
    if set(by_id) != {"preflight", "apply"}:
        raise CommandPortError("mig045_gate12b_migration_receipt_step_mismatch")
    if by_id["preflight"].get("status") != "success" or by_id["apply"].get("status") != "success":
        raise CommandPortError("mig045_gate12b_migration_step_failed")
    preflight_result = by_id["preflight"].get("result")
    apply_result = by_id["apply"].get("result")
    if (
        not isinstance(preflight_result, dict)
        or preflight_result.get("free_sql") is not False
        or preflight_result.get("rollback_present") is not True
    ):
        raise CommandPortError("mig045_gate12b_postgres_preflight_readback_invalid")
    if (
        not isinstance(apply_result, dict)
        or apply_result.get("artifact_sha256") != MIG045_GATE12B_MIGRATION_SHA256
    ):
        raise CommandPortError("mig045_gate12b_postgres_apply_readback_invalid")
    if (
        "migration_id" in apply_result
        and apply_result.get("migration_id") != MIG045_GATE12B_EXPECTED_MIGRATION
    ):
        raise CommandPortError("mig045_gate12b_postgres_apply_migration_id_mismatch")

    release_prepared = request_fn({
        "operation": "prepare_procedure",
        "mission_id": "EN-033/M1",
        "work_id": "MIG045-GATE12B-TECHNICAL-MATERIALIZE",
        "technical_authority": "JA-023",
        "idempotency_key": f"mig045-gate12b-release-{request_key}",
        "procedure": {
            "procedure_id": f"mig045-gate12b-release-{request_key}",
            "title": "MIG045 Gate12B qualified VPS 1.3.52 install",
            "run_budget_seconds": 3600,
            "steps": [{
                "step_id": "qualified-release-install",
                "primitive": "qualified_release_install",
                "args": {
                    "artifact_id": release_artifact_id,
                    "expected_version": MIG045_GATE12B_TECHNICAL_TARGET_VERSION,
                    "expected_source_commit": MIG045_GATE12B_TECHNICAL_SOURCE_COMMIT,
                },
                "timeout_seconds": 3600,
                "resource_lock": "qualified-release",
            }],
        },
    })
    release_plan = _mig045_gate12b_reversible_plan(release_prepared, "release")
    release_receipt = _mig045_gate12b_run_plan(request_fn, release_plan, "release")
    release_steps = release_receipt.get("steps")
    if not isinstance(release_steps, list) or len(release_steps) != 1 or not isinstance(release_steps[0], dict):
        raise CommandPortError("mig045_gate12b_release_receipt_invalid")
    release_step = release_steps[0]
    if release_step.get("step_id") != "qualified-release-install" or release_step.get("status") != "success":
        raise CommandPortError("mig045_gate12b_qualified_release_install_failed")
    release_result = release_step.get("result")
    if isinstance(release_result, dict) and "version" in release_result:
        if release_result.get("version") != MIG045_GATE12B_TECHNICAL_TARGET_VERSION:
            raise CommandPortError("mig045_gate12b_qualified_release_version_mismatch")

    try:
        ready_proof = _validate_mig045_gate12b_technical_ready_proof(ready_fn())
    except CommandPortError:
        raise
    except Exception as exc:
        raise CommandPortError("mig045_gate12b_readiness_failed") from exc

    return {
        "status": "succeeded",
        "migration_id": MIG045_GATE12B_EXPECTED_MIGRATION,
        "migration_run_id": migration_receipt["run_id"],
        "release_run_id": release_receipt["run_id"],
        "target_version": MIG045_GATE12B_TECHNICAL_TARGET_VERSION,
        "source_commit": MIG045_GATE12B_TECHNICAL_SOURCE_COMMIT,
        "transport_sha256": MIG045_GATE12B_TRANSPORT_SHA256,
        "transport_size": MIG045_GATE12B_TRANSPORT_SIZE,
        "migration_sha256": MIG045_GATE12B_MIGRATION_SHA256,
        "rollback_sha256": MIG045_GATE12B_ROLLBACK_SHA256,
        "ready_proof": ready_proof,
    }
# END MIG045_GATE12B_TECHNICAL_MATERIALIZATION_V1
'''
    COMMAND.write_text(text.rstrip() + block.rstrip() + "\n", encoding="utf-8")


def write_manifest() -> str:
    files = {}
    for name in RUNTIME_FILES:
        raw = (ROOT / name).read_bytes()
        files[name] = {
            "path": f".elan-vps-bridge/bootstrap/{name}",
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    payload = {
        "schema_version": "1.0",
        "release_id": RELEASE_ID,
        "files": files,
    }
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    MANIFEST.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    verify_packages()
    patch_command_port()
    patch_issue_inbox()
    manifest_sha = write_manifest()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest["files"]["bridge_worker.py"]["sha256"] != "7d7f7839cf0c5931bf8af29c78adef59a4e1a0bab10dfb064150942975635cd4":
        raise SystemExit("bridge_worker_hash_changed")
    print(f"GATE12B_MIGRATION_SHA256={MIGRATION_SHA256}")
    print(f"GATE12B_ROLLBACK_SHA256={ROLLBACK_SHA256}")
    print(f"RUNTIME_MANIFEST_SHA256={manifest_sha}")
    for name in RUNTIME_FILES:
        print(f"RUNTIME_{name.upper().replace('.', '_')}_SHA256={manifest['files'][name]['sha256']}")


if __name__ == "__main__":
    main()
