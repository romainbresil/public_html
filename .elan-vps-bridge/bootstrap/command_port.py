#!/usr/bin/env python3
import base64
import binascii
import hashlib
import json
import os
import re
import socket
import urllib.parse
import urllib.request
from typing import Callable

BROKER_SOCKET_PATH_DEFAULT = "/run/elan-vps-v1/control.sock"
READ_STATUS_TEMPLATE = "en029_m6_schema_migrations_v1"
G6_SCHEMA_COLUMNS_TEMPLATE = "en029_m6_schema_columns_chunks_v2"
G6_SCHEMA_FUNCTIONS_TEMPLATE = "en029_m6_schema_functions_chunks_v2"
G4_COMMAND_TEMPLATE = "en029_m6_chatgpt_voice_register_v1"
G4_EXECUTION_CLASS = "mutating_technical_change"
G5_EXECUTION_CLASS = "reversible_technical_change"
CONTROL_REPO = os.environ.get("ELAN_BRIDGE_CONTROL_REPO", "romainbresil/public_html")
CONTROL_REF = os.environ.get("ELAN_BRIDGE_CONTROL_REF", "elan-vps-bridge-control-v1")
G5_MIGRATION_PATH = ".elan-vps-bridge/packages/en2-g5/20260903_en2_g5_001_knowledge_observation_capture.sql"
G5_ROLLBACK_PATH = ".elan-vps-bridge/packages/en2-g5/20260903_en2_g5_001_knowledge_observation_capture.rollback.sql"
G5_MIGRATION_SHA256 = "9ba6de679ef3dd5382b7a0b2b5b3d6dada0dac0d5f6cabe3ad50e2739d4ec236"
G5_ROLLBACK_SHA256 = "4a5823e4dd95d61f3b92b47cbcefaa72184a751d00fcd724ca3f572f62eaecb8"
G5_EXPECTED_MIGRATION = "EN2_G5_001"
_MAX_RESPONSE_BYTES = 4_194_304
_MAX_PACKAGE_BYTES = 180_000
_SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]+")


class CommandPortError(RuntimeError):
    pass


def broker_request(payload: dict) -> dict:
    path = os.environ.get("ELAN_BRIDGE_BROKER_SOCKET", BROKER_SOCKET_PATH_DEFAULT)
    wire = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    chunks: list[bytes] = []
    total = 0
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(45)
            client.connect(path)
            client.sendall(wire)
            client.shutdown(socket.SHUT_WR)
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_RESPONSE_BYTES:
                    raise CommandPortError("broker_response_too_large")
                chunks.append(chunk)
    except (OSError, TimeoutError) as exc:
        raise CommandPortError("broker_unavailable") from exc
    try:
        response = json.loads(b"".join(chunks).decode("utf-8").strip())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CommandPortError("invalid_broker_response") from exc
    if not isinstance(response, dict):
        raise CommandPortError("invalid_broker_response")
    if response.get("status") == "error":
        raise CommandPortError(str(response.get("error") or "broker_error"))
    return response


def _safe_key(value: str) -> str:
    cleaned = _SAFE_ID.sub("-", value).strip("-.")[:96]
    if not cleaned:
        raise CommandPortError("invalid_request_id")
    return cleaned


def _artifact_id(response: dict) -> str:
    direct = response.get("artifact_id")
    if isinstance(direct, str) and direct:
        return direct
    nested = response.get("artifact")
    if isinstance(nested, dict):
        value = nested.get("artifact_id")
        if isinstance(value, str) and value:
            return value
    raise CommandPortError("broker_stage_result_invalid")


def _control_raw_url(relative_path: str) -> str:
    quoted = "/".join(urllib.parse.quote(part, safe="") for part in relative_path.split("/"))
    return f"https://raw.githubusercontent.com/{CONTROL_REPO}/{CONTROL_REF}/{quoted}"


def _fetch_control_path(relative_path: str) -> bytes:
    request = urllib.request.Request(
        _control_raw_url(relative_path),
        headers={
            "User-Agent": "elan-web-vps-bridge-command-port/1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = response.read(_MAX_PACKAGE_BYTES + 1)
    except OSError as exc:
        raise CommandPortError("g5_package_fetch_failed") from exc
    if len(payload) > _MAX_PACKAGE_BYTES:
        raise CommandPortError("g5_package_too_large")
    return payload


def read_en_core_status_v1(request_id: str, request_fn: Callable[[dict], dict] = broker_request) -> dict:
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
    return {
        "status": "succeeded",
        "execution_class": "read_only",
        "template": READ_STATUS_TEMPLATE,
        "rows": result.get("rows"),
        "sha256": result.get("sha256"),
        "latest_migration": latest,
        "run_id": receipt.get("run_id"),
        "replayed": bool(receipt.get("replayed")),
    }


def build_en2_g4_canary_payload_v1(request_id: str) -> dict:
    key = _safe_key(request_id).lower()
    external_id = f"en2-g4-canary-{key}"
    return {
        "schema_version": "en029-m6.multichannel-entry.v1",
        "channel": "CHATGPT_VOICE",
        "source_system": "inbound:voice",
        "external_id": external_id,
        "occurred_at": "2026-09-03T00:00:00Z",
        "idempotency_key": f"inbound:voice:{external_id}",
        "evidence": {
            "kind": "CHATGPT_TRANSCRIPT",
            "external_id": external_id,
            "note": "EN2-G4 synthetic production canary; no external action is authorized.",
        },
        "subject": "EN2-G4 SYNTHETIC CANARY — DO NOT CONTACT",
        "content_text": "Synthetic production canary for idempotency and readback verification. Do not contact or execute externally.",
        "people": [{
            "display_name": f"EN2 G4 Synthetic Canary {key}",
            "role": "SYNTHETIC_CANARY",
            "is_referrer": False,
        }],
        "organizations": [],
        "classification": "COMMERCIAL",
        "proposed_stage": "QUALIFICATION",
        "proposed_next_action": {
            "title": "SYNTHETIC CANARY — DO NOT CONTACT",
            "due_at": "2099-01-01T00:00:00Z",
            "wait_condition": "MANUAL_NEVER_EXECUTE",
        },
        "matching_confidence": 1.0,
        "metadata": {
            "account_ref": "EN2_G4_CANARY",
            "confidentiality_code": "INTERNAL_ROMAIN",
        },
    }


def _run_g4_command_once(
    request_key: str,
    attempt: int,
    artifact_id: str,
    request_fn: Callable[[dict], dict],
) -> dict:
    prepared = request_fn({
        "operation": "prepare_procedure",
        "mission_id": "EN2-G4",
        "work_id": "COMMERCIAL-VERTICAL-PROD",
        "technical_authority": "JA-023",
        "idempotency_key": f"en2-g4-commercial-{request_key}-attempt-{attempt}",
        "procedure": {
            "procedure_id": f"en2-g4-commercial-{request_key}-attempt-{attempt}",
            "title": "EN2-G4 bounded commercial synthetic canary",
            "run_budget_seconds": 60,
            "steps": [{
                "step_id": "register-commercial-canary",
                "primitive": "postgres_command_template",
                "args": {
                    "profile": "business",
                    "template": G4_COMMAND_TEMPLATE,
                    "input_artifact_id": artifact_id,
                    "mode": "commit",
                },
                "timeout_seconds": 30,
            }],
        },
    })
    plan = prepared.get("plan")
    if not isinstance(plan, dict) or plan.get("risk") not in {"mutating", G4_EXECUTION_CLASS}:
        raise CommandPortError("broker_plan_not_mutating")
    executed = request_fn({
        "operation": "start_run",
        "plan_id": plan.get("plan_id"),
        "execution_token": plan.get("execution_token"),
        "procedure_sha256": plan.get("procedure_sha256"),
        "execution_class": G4_EXECUTION_CLASS,
        "mode": "sync",
    })
    receipt = executed.get("receipt")
    if (
        not isinstance(receipt, dict)
        or receipt.get("status") != "succeeded"
        or receipt.get("execution_class") != G4_EXECUTION_CLASS
    ):
        raise CommandPortError("broker_g4_run_failed")
    steps = receipt.get("steps")
    if not isinstance(steps, list) or len(steps) != 1 or not isinstance(steps[0], dict):
        raise CommandPortError("broker_g4_receipt_invalid")
    result = steps[0].get("result")
    if (
        not isinstance(result, dict)
        or result.get("template") != G4_COMMAND_TEMPLATE
        or result.get("mode") != "commit"
        or result.get("committed") is not True
    ):
        raise CommandPortError("broker_g4_result_invalid")
    command_result = result.get("command_result")
    verification = result.get("verification")
    if not isinstance(command_result, dict) or command_result.get("ok") is not True:
        raise CommandPortError("broker_g4_command_failed")
    if not isinstance(verification, dict) or verification.get("status_code") != "COMMITTED":
        raise CommandPortError("broker_g4_readback_invalid")
    return {
        "run_id": receipt.get("run_id"),
        "duplicate": bool(command_result.get("duplicate")),
        "outcome": command_result.get("outcome"),
        "idempotency_key": verification.get("idempotency_key"),
        "dossier_id": verification.get("dossier_id"),
        "information_id": verification.get("information_id"),
        "action_id": verification.get("action_id"),
        "status_code": verification.get("status_code"),
    }


def run_en2_g4_commercial_canary_v1(
    request_id: str,
    request_fn: Callable[[dict], dict] = broker_request,
) -> dict:
    request_key = _safe_key(request_id).lower()
    payload = build_en2_g4_canary_payload_v1(request_id)
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    staged = request_fn({
        "operation": "stage_text",
        "content": content,
        "expected_sha256": checksum,
        "media_type": "application/json",
        "label": f"en2-g4-commercial-{request_key}",
    })
    artifact_id = _artifact_id(staged)

    first = _run_g4_command_once(request_key, 1, artifact_id, request_fn)
    replay = _run_g4_command_once(request_key, 2, artifact_id, request_fn)

    if first["duplicate"] is not False or replay["duplicate"] is not True:
        raise CommandPortError("g4_application_idempotency_not_proven")
    expected_key = payload["idempotency_key"]
    if first["idempotency_key"] != expected_key or replay["idempotency_key"] != expected_key:
        raise CommandPortError("g4_idempotency_readback_mismatch")
    identity_fields = ("dossier_id", "information_id", "action_id")
    for field in identity_fields:
        if not first.get(field) or first.get(field) != replay.get(field):
            raise CommandPortError("g4_readback_identity_mismatch")

    return {
        "status": "succeeded",
        "execution_class": G4_EXECUTION_CLASS,
        "template": G4_COMMAND_TEMPLATE,
        "idempotency_key": expected_key,
        "artifact_sha256": checksum,
        "first": first,
        "replay": replay,
        "reconciled": True,
        "external_action_allowed": False,
    }


def _verified_g5_package(fetch_fn: Callable[[str], bytes]) -> tuple[str, str]:
    try:
        migration_raw = fetch_fn(G5_MIGRATION_PATH)
        rollback_raw = fetch_fn(G5_ROLLBACK_PATH)
    except CommandPortError:
        raise
    except Exception as exc:
        raise CommandPortError("g5_package_fetch_failed") from exc
    if not isinstance(migration_raw, bytes) or not isinstance(rollback_raw, bytes):
        raise CommandPortError("g5_package_fetch_invalid")
    if len(migration_raw) > _MAX_PACKAGE_BYTES or len(rollback_raw) > _MAX_PACKAGE_BYTES:
        raise CommandPortError("g5_package_too_large")
    if hashlib.sha256(migration_raw).hexdigest() != G5_MIGRATION_SHA256:
        raise CommandPortError("g5_migration_sha256_mismatch")
    if hashlib.sha256(rollback_raw).hexdigest() != G5_ROLLBACK_SHA256:
        raise CommandPortError("g5_rollback_sha256_mismatch")
    try:
        return migration_raw.decode("utf-8"), rollback_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CommandPortError("g5_package_not_utf8") from exc


def run_en2_g5_knowledge_capture_v1(
    request_id: str,
    request_fn: Callable[[dict], dict] = broker_request,
    fetch_fn: Callable[[str], bytes] = _fetch_control_path,
) -> dict:
    request_key = _safe_key(request_id).lower()
    migration_text, rollback_text = _verified_g5_package(fetch_fn)

    staged_migration = request_fn({
        "operation": "stage_text",
        "content": migration_text,
        "expected_sha256": G5_MIGRATION_SHA256,
        "media_type": "text/plain",
        "label": f"en2-g5-migration-{request_key}",
    })
    staged_rollback = request_fn({
        "operation": "stage_text",
        "content": rollback_text,
        "expected_sha256": G5_ROLLBACK_SHA256,
        "media_type": "text/plain",
        "label": f"en2-g5-rollback-{request_key}",
    })
    migration_artifact_id = _artifact_id(staged_migration)
    rollback_artifact_id = _artifact_id(staged_rollback)

    prepared = request_fn({
        "operation": "prepare_procedure",
        "mission_id": "EN2-G5",
        "work_id": "KNOWLEDGE-CAPTURE-PROD",
        "technical_authority": "JA-023",
        "idempotency_key": f"en2-g5-knowledge-{request_key}",
        "procedure": {
            "procedure_id": f"en2-g5-knowledge-{request_key}",
            "title": "EN2-G5 bounded knowledge capture production migration",
            "run_budget_seconds": 900,
            "steps": [
                {
                    "step_id": "backup",
                    "primitive": "postgres_backup",
                    "args": {"profile": "business", "label": f"en2-g5-pre-{request_key}"},
                    "timeout_seconds": 300,
                    "retry": 0,
                    "resource_lock": "postgres-business-en2-g5",
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
                    "resource_lock": "postgres-business-en2-g5",
                },
                {
                    "step_id": "apply",
                    "primitive": "postgres_migration_apply",
                    "args": {
                        "profile": "business",
                        "artifact_id": migration_artifact_id,
                        "rollback_artifact_id": rollback_artifact_id,
                        "expected_migration": G5_EXPECTED_MIGRATION,
                    },
                    "timeout_seconds": 300,
                    "retry": 0,
                    "resource_lock": "postgres-business-en2-g5",
                },
                {
                    "step_id": "inventory",
                    "primitive": "postgres_inventory",
                    "args": {"profile": "business"},
                    "timeout_seconds": 120,
                    "retry": 0,
                    "resource_lock": "postgres-business-en2-g5",
                },
            ],
        },
    })
    plan = prepared.get("plan")
    if not isinstance(plan, dict) or plan.get("risk") not in {"reversible", G5_EXECUTION_CLASS}:
        raise CommandPortError("broker_g5_plan_not_reversible")

    executed = request_fn({
        "operation": "start_run",
        "plan_id": plan.get("plan_id"),
        "execution_token": plan.get("execution_token"),
        "procedure_sha256": plan.get("procedure_sha256"),
        "execution_class": G5_EXECUTION_CLASS,
        "mode": "sync",
    })
    receipt = executed.get("receipt")
    if (
        not isinstance(receipt, dict)
        or receipt.get("status") != "succeeded"
        or receipt.get("execution_class") != G5_EXECUTION_CLASS
    ):
        raise CommandPortError("broker_g5_run_failed")
    steps = receipt.get("steps")
    if not isinstance(steps, list) or len(steps) != 4:
        raise CommandPortError("broker_g5_receipt_invalid")
    by_id = {
        step.get("step_id"): step
        for step in steps
        if isinstance(step, dict) and isinstance(step.get("step_id"), str)
    }
    if set(by_id) != {"backup", "preflight", "apply", "inventory"}:
        raise CommandPortError("broker_g5_receipt_step_mismatch")
    if any(by_id[name].get("status") != "success" for name in by_id):
        raise CommandPortError("broker_g5_step_failed")

    preflight = by_id["preflight"].get("result")
    apply_result = by_id["apply"].get("result")
    inventory = by_id["inventory"].get("result")
    backup = by_id["backup"].get("result")
    if not isinstance(preflight, dict) or preflight.get("free_sql") is not False or preflight.get("rollback_present") is not True:
        raise CommandPortError("broker_g5_preflight_readback_invalid")
    if not isinstance(apply_result, dict) or apply_result.get("artifact_sha256") != G5_MIGRATION_SHA256:
        raise CommandPortError("broker_g5_apply_readback_invalid")
    if not isinstance(inventory, dict):
        raise CommandPortError("broker_g5_inventory_readback_invalid")
    if not isinstance(backup, dict):
        raise CommandPortError("broker_g5_backup_readback_invalid")

    return {
        "status": "succeeded",
        "execution_class": G5_EXECUTION_CLASS,
        "expected_migration": G5_EXPECTED_MIGRATION,
        "migration_sha256": G5_MIGRATION_SHA256,
        "rollback_sha256": G5_ROLLBACK_SHA256,
        "run_id": receipt.get("run_id"),
        "backup": backup,
        "preflight": preflight,
        "apply": apply_result,
        "inventory": inventory,
        "transaction_assertions_embedded": True,
        "external_action_allowed": False,
    }



def _reconstruct_g6_capture(result: dict, expected_template: str, expected_capture: str) -> list[dict]:
    if not isinstance(result, dict) or result.get("template") != expected_template:
        raise CommandPortError("broker_g6_schema_result_invalid")
    values = result.get("values")
    if not isinstance(values, list) or not values:
        raise CommandPortError("broker_g6_schema_values_invalid")
    grouped: dict[int, dict[int, str]] = {}
    counts: dict[int, int] = {}
    expected_keys = {"kind", "capture", "record_ordinal", "chunk_ordinal", "chunk_count", "payload_base64_chunk"}
    for value in values:
        if not isinstance(value, str) or len(value) > 4096:
            raise CommandPortError("broker_g6_schema_value_invalid")
        try:
            item = json.loads(value)
        except json.JSONDecodeError as exc:
            raise CommandPortError("broker_g6_schema_chunk_json_invalid") from exc
        if not isinstance(item, dict) or set(item) != expected_keys:
            raise CommandPortError("broker_g6_schema_chunk_contract_invalid")
        if item.get("kind") != "capture_chunk" or item.get("capture") != expected_capture:
            raise CommandPortError("broker_g6_schema_chunk_contract_invalid")
        record_ordinal = item.get("record_ordinal")
        chunk_ordinal = item.get("chunk_ordinal")
        chunk_count = item.get("chunk_count")
        chunk = item.get("payload_base64_chunk")
        if (
            not isinstance(record_ordinal, int) or record_ordinal < 1
            or not isinstance(chunk_ordinal, int) or chunk_ordinal < 1
            or not isinstance(chunk_count, int) or chunk_count < 1
            or chunk_ordinal > chunk_count
            or not isinstance(chunk, str) or len(chunk) > 3000
        ):
            raise CommandPortError("broker_g6_schema_chunk_contract_invalid")
        if record_ordinal in counts and counts[record_ordinal] != chunk_count:
            raise CommandPortError("broker_g6_schema_chunk_count_mismatch")
        counts[record_ordinal] = chunk_count
        record = grouped.setdefault(record_ordinal, {})
        if chunk_ordinal in record:
            raise CommandPortError("broker_g6_schema_duplicate_chunk")
        record[chunk_ordinal] = chunk

    if sorted(grouped) != list(range(1, len(grouped) + 1)):
        raise CommandPortError("broker_g6_schema_record_sequence_incomplete")

    records: list[dict] = []
    for record_ordinal in range(1, len(grouped) + 1):
        chunks = grouped[record_ordinal]
        chunk_count = counts[record_ordinal]
        if sorted(chunks) != list(range(1, chunk_count + 1)):
            raise CommandPortError("broker_g6_schema_chunk_sequence_incomplete")
        encoded = "".join(chunks[index] for index in range(1, chunk_count + 1))
        try:
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
            record = json.loads(decoded)
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CommandPortError("broker_g6_schema_record_invalid") from exc
        if not isinstance(record, dict):
            raise CommandPortError("broker_g6_schema_record_invalid")
        records.append(record)
    return records


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
                    "args": {
                        "profile": "business",
                        "template": G6_SCHEMA_COLUMNS_TEMPLATE,
                        "parameters": [],
                    },
                    "timeout_seconds": 30,
                },
                {
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
    if (
        not isinstance(receipt, dict)
        or receipt.get("status") != "succeeded"
        or receipt.get("execution_class") != "read_only"
    ):
        raise CommandPortError("broker_g6_schema_read_failed")
    steps = receipt.get("steps")
    if not isinstance(steps, list) or len(steps) != 2:
        raise CommandPortError("broker_g6_schema_receipt_invalid")
    by_id = {
        step.get("step_id"): step
        for step in steps
        if isinstance(step, dict) and isinstance(step.get("step_id"), str)
    }
    if set(by_id) != {"schema-columns", "schema-functions"}:
        raise CommandPortError("broker_g6_schema_step_mismatch")
    if any(by_id[name].get("status") != "success" for name in by_id):
        raise CommandPortError("broker_g6_schema_step_failed")

    columns_all = _reconstruct_g6_capture(
        by_id["schema-columns"].get("result"),
        G6_SCHEMA_COLUMNS_TEMPLATE,
        "columns",
    )
    functions_all = _reconstruct_g6_capture(
        by_id["schema-functions"].get("result"),
        G6_SCHEMA_FUNCTIONS_TEMPLATE,
        "functions",
    )
    allowed_tables = {"dossiers", "dossier_decisions", "dossier_events", "parties"}
    columns = [
        item
        for item in columns_all
        if item.get("kind") == "column" and item.get("table") in allowed_tables
    ]
    functions = [
        item
        for item in functions_all
        if item.get("kind") == "function"
        and item.get("name") == "record_human_decision_v1"
    ]
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
