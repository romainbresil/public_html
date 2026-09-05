#!/usr/bin/env python3
import base64
import binascii
import hashlib
import json
import os
import pathlib
import re
import socket
import time
import urllib.parse
import urllib.request
from typing import Callable

BROKER_SOCKET_PATH_DEFAULT = "/run/elan-vps-v1/control.sock"
READ_STATUS_TEMPLATE = "en029_m6_schema_migrations_v1"
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
G6_SCHEMA_COLUMNS_TEMPLATE = "en029_m6_schema_columns_chunks_v2"
G6_SCHEMA_FUNCTIONS_TEMPLATE = "en029_m6_schema_functions_chunks_v2"
G6_SCHEMA_CONSTRAINTS_TEMPLATE = "en029_m6_schema_constraints_indexes_chunks_v2"
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
MIG045_TARGET_VERSION = "1.3.51"
MIG045_SOURCE_COMMIT = "275118ca38cd36cdbfc25c9cf9c72d1fca09b89f"
MIG045_QUALIFIED_TRANSFER_SHA256 = "4825b62c4df34806c98d1379f1df325fbc3f571bceea20e5f05e17bccfd790e0"
MIG045_QUALIFIED_TRANSFER_SIZE = 63986974
MIG045_READ_TEMPLATE = "en033_m1_mig045_editorial_readback_v1"
MIG045_EXPECTED_FIELDS = {
    "plan_count",
    "occurrence_count",
    "publication_state_counts",
    "observation_state_counts",
}
MIG045_PUBLICATION_STATES = {"PLANNED", "PROGRAMMED", "PUBLISHED"}
MIG045_OBSERVATION_STATES = {
    "NOT_OBSERVED",
    "AMBIGUOUS",
    "CONFIRMED_NOT_FOUND",
    "CONFIRMED_PUBLISHED",
}
MIG045_READYZ_URL = "http://127.0.0.1:8787/readyz"
MIG045_GATE12B_TARGET = "mig045-gate12b-committed-proof"
MIG045_GATE12B_EXPECTED_IDENTITY_SET_SHA256 = "dc731702f983999e083563477216054bfcee5674eff03a5d6ef8cb479b0c2cc1"
MIG045_GATE12B_TEMPLATE = "en033_m1_mig045_gate12b_committed_proof_v1"
MIG045_GATE12B_EXECUTION_CLASS = "mutating_technical_change"
MIG045_GATE12B_OBSERVATION_SEMANTICS = "COMMITTED_PROOF_TRANSACTION_V1"
MIG045_GATE12B_PROOF_ID_DOMAIN = "EN033/M1:MIG045:G12B:COMMITTED_PROOF_TRANSACTION_V1:"
MIG045_GATE12B_CORPUS = tuple(f"CON-{number:03d}" for number in range(20, 28))
MIG045_GATE12B_A_TECHNICAL_HEAD = "b8a5672d090fb0ddceb552e5029cf04b736da44d"
MIG045_GATE12B_RUNTIME_VERSION = "1.3.52"
MIG045_GATE12B_CAPABILITY_SHA256 = "b51a4bf09041f42af28b737f868710d5377123eb0747ae4fd6e2fd290a006729"
MIG045_GATE12B_COMMAND_TEMPLATE_SHA256 = "6fff7e691aaa4cbc7d3b789e8b111988bc08d2680e911e6298c4d16fcceb123a"
MIG045_GATE12B_SQL_OWNER_SHA256 = "77c7c90c25f2eefe7827a1c0c469b5a1343ca0646aa9c29d485e3dc1edd2fa25"
MIG045_GATE12B_RESOLVED_DATABASE = "postgres"
MIG045_GATE12B_RESOLVED_ROLE = "en_gate12b_executor"
MIG045_GATE12B_POSTGRES_PROFILE = "business"
MIG045_GATE12B_SCHEMA = "elan_naturel"
MIG045_GATE12B_CORPUS_IDENTIFIER = "CON-020..CON-027"
MIG045_GATE12B_CORPUS_SHA256 = "cd0f4bde395351cbdb99b9d6f342cc0718d2be5276ca06000e44162d00bebcef"
_GATE12B_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_GATE12B_COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")
_GATE12B_RUNTIME_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_GATE12B_PROOF_CONTRACT_FIELDS = frozenset({
    "observation_semantics",
    "expected_identity_set_sha256",
    "corpus",
    "runtime_version",
    "runtime_source_commit",
    "capability_sha256",
    "effective_policy_sha256",
    "command_template_sha256",
    "sql_owner_sha256",
    "target_binding_sha256",
})
_GATE12B_PREFLIGHT_FIELDS = (
    "runtime_version",
    "runtime_source_commit",
    "capability_sha256",
    "effective_policy_sha256",
    "command_template_sha256",
    "sql_owner_sha256",
    "target_binding_sha256",
)
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


def _project_schema_migration_membership_v1(values: object, requested_ids: object) -> dict:
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


def validate_mig045_v1351_artifact_url(value: object) -> str:
    if not isinstance(value, str) or len(value) < 16 or len(value) > 4096:
        raise CommandPortError("mig045_artifact_url_invalid")
    try:
        parsed = urllib.parse.urlparse(value)
    except ValueError as exc:
        raise CommandPortError("mig045_artifact_url_invalid") from exc
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not host.endswith(".oaiusercontent.com")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or not parsed.path.startswith("/files/")
        or parsed.fragment
    ):
        raise CommandPortError("mig045_artifact_url_invalid")
    return value


def _mig045_wait_ready_v1351(timeout_seconds: int = 600) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(
                MIG045_READYZ_URL,
                headers={"User-Agent": "elan-web-vps-bridge-mig045/1", "Cache-Control": "no-cache"},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                proof = json.load(response)
            if (
                isinstance(proof, dict)
                and proof.get("version") == MIG045_TARGET_VERSION
                and proof.get("status") in {"ok", "ready"}
            ):
                return proof
        except Exception:
            pass
        time.sleep(2)
    raise CommandPortError("mig045_v1351_readiness_timeout")


def _validate_mig045_ready_proof(proof: object) -> dict:
    if (
        not isinstance(proof, dict)
        or proof.get("version") != MIG045_TARGET_VERSION
        or proof.get("status") not in {"ok", "ready"}
    ):
        raise CommandPortError("mig045_v1351_ready_proof_invalid")
    return proof


def _validate_mig045_aggregate(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != MIG045_EXPECTED_FIELDS:
        raise CommandPortError("mig045_fresh_read_contract_invalid")
    for name in ("plan_count", "occurrence_count"):
        count = value.get(name)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise CommandPortError("mig045_fresh_read_count_invalid")
    publication = value.get("publication_state_counts")
    observation = value.get("observation_state_counts")
    if not isinstance(publication, dict) or set(publication) != MIG045_PUBLICATION_STATES:
        raise CommandPortError("mig045_publication_state_contract_invalid")
    if not isinstance(observation, dict) or set(observation) != MIG045_OBSERVATION_STATES:
        raise CommandPortError("mig045_observation_state_contract_invalid")
    for counts in (publication, observation):
        for count in counts.values():
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise CommandPortError("mig045_fresh_read_count_invalid")
    occurrence_count = value["occurrence_count"]
    if sum(publication.values()) != occurrence_count or sum(observation.values()) != occurrence_count:
        raise CommandPortError("mig045_fresh_read_distribution_total_mismatch")
    return value


def run_mig045_v1351_rollout_and_fresh_read_v1(
    request_id: str,
    artifact_url: str,
    request_fn: Callable[[dict], dict] = broker_request,
    ready_fn: Callable[[], dict] = _mig045_wait_ready_v1351,
) -> dict:
    key = _safe_key(request_id).lower()
    url = validate_mig045_v1351_artifact_url(artifact_url)
    staged = request_fn({
        "operation": "stage_https",
        "url": url,
        "expected_sha256": MIG045_QUALIFIED_TRANSFER_SHA256,
        "expected_size_bytes": MIG045_QUALIFIED_TRANSFER_SIZE,
        "media_type": "application/zip",
        "label": f"qualified-connector-transfer:elan-vps-{MIG045_TARGET_VERSION}",
    })
    artifact_id = _artifact_id(staged)

    rollout_prepared = request_fn({
        "operation": "prepare_procedure",
        "mission_id": "EN-041/M1",
        "work_id": "W7",
        "technical_authority": "JA-023",
        "idempotency_key": f"mig045-v1351-rollout-{key}",
        "procedure": {
            "procedure_id": f"mig045-v1351-rollout-{key}",
            "title": "MIG045 closed rollout VPS 1.3.51",
            "run_budget_seconds": 3600,
            "steps": [{
                "step_id": "qualified-release-install",
                "primitive": "qualified_release_install",
                "args": {
                    "artifact_id": artifact_id,
                    "expected_version": MIG045_TARGET_VERSION,
                    "expected_source_commit": MIG045_SOURCE_COMMIT,
                },
                "timeout_seconds": 3600,
                "resource_lock": "qualified-release",
            }],
        },
    })
    rollout_plan = rollout_prepared.get("plan")
    if not isinstance(rollout_plan, dict) or rollout_plan.get("risk") not in {"reversible", "reversible_technical_change"}:
        raise CommandPortError("mig045_rollout_plan_not_reversible")
    rollout_executed = request_fn({
        "operation": "start_run",
        "plan_id": rollout_plan.get("plan_id"),
        "execution_token": rollout_plan.get("execution_token"),
        "procedure_sha256": rollout_plan.get("procedure_sha256"),
        "execution_class": "reversible_technical_change",
        "mode": "sync",
    })
    rollout_receipt = rollout_executed.get("receipt")
    if not isinstance(rollout_receipt, dict) or rollout_receipt.get("status") != "succeeded":
        raise CommandPortError("mig045_qualified_release_install_failed")
    rollout_steps = rollout_receipt.get("steps")
    if not isinstance(rollout_steps, list) or len(rollout_steps) != 1 or not isinstance(rollout_steps[0], dict):
        raise CommandPortError("mig045_rollout_receipt_invalid")
    rollout_step = rollout_steps[0]
    if rollout_step.get("step_id") != "qualified-release-install" or rollout_step.get("status") != "success":
        raise CommandPortError("mig045_rollout_step_failed")

    ready_proof = _validate_mig045_ready_proof(ready_fn())

    cleanup_response = request_fn({"operation": "cleanup_artifact", "artifact_id": artifact_id})
    cleanup = cleanup_response.get("result")
    if not isinstance(cleanup, dict):
        raise CommandPortError("mig045_transport_cleanup_invalid")

    read_prepared = request_fn({
        "operation": "prepare_procedure",
        "mission_id": "EN-033/M1",
        "work_id": "MIG045-CLOSED-EDITORIAL-FRESH-READ",
        "technical_authority": "JA-023",
        "idempotency_key": f"mig045-editorial-fresh-read-{key}",
        "procedure": {
            "procedure_id": f"mig045-editorial-fresh-read-{key}",
            "title": "MIG045 one closed editorial aggregate fresh read",
            "run_budget_seconds": 60,
            "steps": [{
                "step_id": "mig045-editorial-fresh-read",
                "primitive": "postgres_query_template",
                "args": {"profile": "business", "template": MIG045_READ_TEMPLATE, "parameters": []},
                "timeout_seconds": 30,
            }],
        },
    })
    read_plan = read_prepared.get("plan")
    if not isinstance(read_plan, dict) or read_plan.get("risk") != "read_only":
        raise CommandPortError("mig045_fresh_read_plan_not_read_only")
    read_executed = request_fn({
        "operation": "start_run",
        "plan_id": read_plan.get("plan_id"),
        "execution_token": read_plan.get("execution_token"),
        "procedure_sha256": read_plan.get("procedure_sha256"),
        "execution_class": "read_only",
        "mode": "sync",
    })
    read_receipt = read_executed.get("receipt")
    if (
        not isinstance(read_receipt, dict)
        or read_receipt.get("status") != "succeeded"
        or read_receipt.get("execution_class") != "read_only"
    ):
        raise CommandPortError("mig045_fresh_read_failed")
    read_steps = read_receipt.get("steps")
    if not isinstance(read_steps, list) or len(read_steps) != 1 or not isinstance(read_steps[0], dict):
        raise CommandPortError("mig045_fresh_read_receipt_invalid")
    read_step = read_steps[0]
    result = read_step.get("result")
    if (
        read_step.get("step_id") != "mig045-editorial-fresh-read"
        or read_step.get("status") != "success"
        or not isinstance(result, dict)
        or result.get("template") != MIG045_READ_TEMPLATE
        or result.get("rows") != 1
    ):
        raise CommandPortError("mig045_fresh_read_result_invalid")
    values = result.get("values")
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], str):
        raise CommandPortError("mig045_fresh_read_cardinality_invalid")
    try:
        aggregate = _validate_mig045_aggregate(json.loads(values[0]))
    except json.JSONDecodeError as exc:
        raise CommandPortError("mig045_fresh_read_json_invalid") from exc

    return {
        "status": "succeeded",
        "target_version": MIG045_TARGET_VERSION,
        "source_commit": MIG045_SOURCE_COMMIT,
        "qualified_transfer_sha256": MIG045_QUALIFIED_TRANSFER_SHA256,
        "qualified_transfer_size_bytes": MIG045_QUALIFIED_TRANSFER_SIZE,
        "rollout_run_id": rollout_receipt.get("run_id"),
        "ready_proof": ready_proof,
        "transport_cleanup": cleanup,
        "fresh_read": {
            "database_profile": "business",
            "template": MIG045_READ_TEMPLATE,
            "execution_class": "read_only",
            "rows": 1,
            "sha256": result.get("sha256"),
            "run_id": read_receipt.get("run_id"),
            "replayed": bool(read_receipt.get("replayed")),
            "aggregate": aggregate,
        },
        "free_sql": False,
        "external_action_allowed": False,
    }



def _validate_gate12b_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _GATE12B_SHA256_RE.fullmatch(value) is None:
        raise CommandPortError(f"mig045_gate12b_{label}_invalid")
    return value


def _gate12b_canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CommandPortError("mig045_gate12b_canonical_json_invalid") from exc


def _validate_mig045_gate12b_proof_contract(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != _GATE12B_PROOF_CONTRACT_FIELDS:
        raise CommandPortError("mig045_gate12b_proof_contract_shape_invalid")
    if value.get("observation_semantics") != MIG045_GATE12B_OBSERVATION_SEMANTICS:
        raise CommandPortError("mig045_gate12b_observation_semantics_invalid")
    if value.get("expected_identity_set_sha256") != MIG045_GATE12B_EXPECTED_IDENTITY_SET_SHA256:
        raise CommandPortError("mig045_gate12b_expected_identity_set_sha256_mismatch")
    corpus = value.get("corpus")
    if not isinstance(corpus, list) or corpus != list(MIG045_GATE12B_CORPUS):
        raise CommandPortError("mig045_gate12b_corpus_invalid")
    static_bindings = {
        "runtime_version": MIG045_GATE12B_RUNTIME_VERSION,
        "runtime_source_commit": MIG045_GATE12B_A_TECHNICAL_HEAD,
        "capability_sha256": MIG045_GATE12B_CAPABILITY_SHA256,
        "command_template_sha256": MIG045_GATE12B_COMMAND_TEMPLATE_SHA256,
        "sql_owner_sha256": MIG045_GATE12B_SQL_OWNER_SHA256,
    }
    for field, expected in static_bindings.items():
        if value.get(field) != expected:
            raise CommandPortError(f"mig045_gate12b_static_binding_mismatch:{field}")
    for field in ("effective_policy_sha256", "target_binding_sha256"):
        _validate_gate12b_sha256(value.get(field), field)
    return dict(value)


def mig045_gate12b_proof_contract_sha256(value: object) -> str:
    contract = _validate_mig045_gate12b_proof_contract(value)
    return hashlib.sha256(_gate12b_canonical_bytes(contract)).hexdigest()


def derive_mig045_gate12b_proof_id(proof_contract_sha256: str) -> str:
    contract_sha = _validate_gate12b_sha256(
        proof_contract_sha256,
        "proof_contract_sha256",
    )
    raw = (MIG045_GATE12B_PROOF_ID_DOMAIN + contract_sha).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_mig045_gate12b_context(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {
        "target",
        "proof_contract",
        "proof_contract_sha256",
        "proof_id",
    }:
        raise CommandPortError("mig045_gate12b_context_shape_invalid")
    if value.get("target") != MIG045_GATE12B_TARGET:
        raise CommandPortError("mig045_gate12b_target_invalid")
    contract = _validate_mig045_gate12b_proof_contract(value.get("proof_contract"))
    supplied_contract_sha = value.get("proof_contract_sha256")
    if not isinstance(supplied_contract_sha, str):
        raise CommandPortError("mig045_gate12b_proof_contract_sha256_invalid")
    expected_contract_sha = hashlib.sha256(_gate12b_canonical_bytes(contract)).hexdigest()
    if supplied_contract_sha != expected_contract_sha:
        raise CommandPortError("mig045_gate12b_proof_contract_sha256_mismatch")
    supplied_proof_id = value.get("proof_id")
    if not isinstance(supplied_proof_id, str):
        raise CommandPortError("mig045_gate12b_proof_id_invalid")
    expected_proof_id = derive_mig045_gate12b_proof_id(expected_contract_sha)
    if supplied_proof_id != expected_proof_id:
        raise CommandPortError("mig045_gate12b_proof_id_mismatch")
    return {
        "target": MIG045_GATE12B_TARGET,
        "proof_contract": contract,
        "proof_contract_sha256": expected_contract_sha,
        "proof_id": expected_proof_id,
    }


def _validate_gate12b_preflight(proof_contract: dict, value: object) -> dict:
    if not isinstance(value, dict) or set(value) != set(_GATE12B_PREFLIGHT_FIELDS):
        raise CommandPortError("mig045_gate12b_preflight_contract_invalid")
    for field in _GATE12B_PREFLIGHT_FIELDS:
        if value.get(field) != proof_contract[field]:
            raise CommandPortError(f"mig045_gate12b_preflight_binding_mismatch:{field}")
    return dict(value)



def freeze_mig045_gate12b_production_proof(preflight: object) -> dict:
    required = {
        "business_reads",
        "proof_executed",
        "runtime_version",
        "runtime_source_commit",
        "capability_sha256",
        "effective_policy_sha256",
        "command_template_sha256",
        "sql_owner_sha256",
        "target_binding_sha256",
        "resolved_database",
        "resolved_role",
        "postgres_profile",
        "schema",
        "expected_identity_set_sha256",
        "corpus",
    }
    if not isinstance(preflight, dict) or not required.issubset(preflight):
        raise CommandPortError("mig045_gate12b_production_preflight_contract_invalid")
    if type(preflight.get("business_reads")) is not int or preflight["business_reads"] != 0:
        raise CommandPortError("mig045_gate12b_production_preflight_business_reads_invalid")
    if preflight.get("proof_executed") is not False:
        raise CommandPortError("mig045_gate12b_production_preflight_proof_executed_invalid")

    static_bindings = {
        "runtime_version": MIG045_GATE12B_RUNTIME_VERSION,
        "runtime_source_commit": MIG045_GATE12B_A_TECHNICAL_HEAD,
        "capability_sha256": MIG045_GATE12B_CAPABILITY_SHA256,
        "command_template_sha256": MIG045_GATE12B_COMMAND_TEMPLATE_SHA256,
        "sql_owner_sha256": MIG045_GATE12B_SQL_OWNER_SHA256,
        "expected_identity_set_sha256": MIG045_GATE12B_EXPECTED_IDENTITY_SET_SHA256,
        "corpus": list(MIG045_GATE12B_CORPUS),
    }
    for field, expected in static_bindings.items():
        if preflight.get(field) != expected:
            raise CommandPortError(f"mig045_gate12b_production_preflight_static_binding_mismatch:{field}")

    target_semantics = {
        "resolved_database": MIG045_GATE12B_RESOLVED_DATABASE,
        "resolved_role": MIG045_GATE12B_RESOLVED_ROLE,
        "postgres_profile": MIG045_GATE12B_POSTGRES_PROFILE,
        "schema": MIG045_GATE12B_SCHEMA,
    }
    for field, expected in target_semantics.items():
        if preflight.get(field) != expected:
            raise CommandPortError(f"mig045_gate12b_production_target_mismatch:{field}")

    effective_policy_sha256 = _validate_gate12b_sha256(
        preflight.get("effective_policy_sha256"), "effective_policy_sha256"
    )
    target_binding_sha256 = _validate_gate12b_sha256(
        preflight.get("target_binding_sha256"), "target_binding_sha256"
    )
    proof_contract = {
        "observation_semantics": MIG045_GATE12B_OBSERVATION_SEMANTICS,
        "expected_identity_set_sha256": MIG045_GATE12B_EXPECTED_IDENTITY_SET_SHA256,
        "corpus": list(MIG045_GATE12B_CORPUS),
        "runtime_version": MIG045_GATE12B_RUNTIME_VERSION,
        "runtime_source_commit": MIG045_GATE12B_A_TECHNICAL_HEAD,
        "capability_sha256": MIG045_GATE12B_CAPABILITY_SHA256,
        "effective_policy_sha256": effective_policy_sha256,
        "command_template_sha256": MIG045_GATE12B_COMMAND_TEMPLATE_SHA256,
        "sql_owner_sha256": MIG045_GATE12B_SQL_OWNER_SHA256,
        "target_binding_sha256": target_binding_sha256,
    }
    proof_contract = _validate_mig045_gate12b_proof_contract(proof_contract)
    proof_contract_sha256 = mig045_gate12b_proof_contract_sha256(proof_contract)
    proof_id = derive_mig045_gate12b_proof_id(proof_contract_sha256)
    technical_preflight = {field: preflight[field] for field in sorted(required)}
    return {
        "proof_contract": proof_contract,
        "proof_contract_sha256": proof_contract_sha256,
        "proof_id": proof_id,
        "technical_preflight": technical_preflight,
        "business_reads": 0,
        "proof_executed": False,
        "external_action_allowed": False,
    }


def _normalize_mig045_gate12b_runtime_preflight_response(response: object) -> dict:
    if (
        not isinstance(response, dict)
        or response.get("status") != "ok"
        or response.get("operation") != "gate12b_technical_preflight"
    ):
        raise CommandPortError("mig045_gate12b_runtime_preflight_response_invalid")
    binding = response.get("preflight")
    provenance = response.get("provenance")
    if not isinstance(binding, dict) or set(binding) != set(_GATE12B_PREFLIGHT_FIELDS):
        raise CommandPortError("mig045_gate12b_runtime_preflight_binding_invalid")
    if not isinstance(provenance, dict):
        raise CommandPortError("mig045_gate12b_runtime_preflight_provenance_invalid")
    if type(provenance.get("business_reads")) is not int or provenance["business_reads"] != 0:
        raise CommandPortError("mig045_gate12b_runtime_preflight_business_reads_invalid")
    if provenance.get("free_sql") is not False or provenance.get("generic_business_mutation") is not False:
        raise CommandPortError("mig045_gate12b_runtime_preflight_boundary_invalid")
    if provenance.get("corpus") != MIG045_GATE12B_CORPUS_IDENTIFIER:
        raise CommandPortError("mig045_gate12b_runtime_preflight_corpus_mismatch")
    if provenance.get("corpus_sha256") != MIG045_GATE12B_CORPUS_SHA256:
        raise CommandPortError("mig045_gate12b_runtime_preflight_corpus_sha256_mismatch")

    return {
        "business_reads": provenance["business_reads"],
        "proof_executed": False,
        "runtime_version": binding.get("runtime_version"),
        "runtime_source_commit": binding.get("runtime_source_commit"),
        "capability_sha256": binding.get("capability_sha256"),
        "effective_policy_sha256": binding.get("effective_policy_sha256"),
        "command_template_sha256": binding.get("command_template_sha256"),
        "sql_owner_sha256": binding.get("sql_owner_sha256"),
        "target_binding_sha256": binding.get("target_binding_sha256"),
        "resolved_database": provenance.get("resolved_database"),
        "resolved_role": provenance.get("resolved_role"),
        "postgres_profile": provenance.get("postgres_profile"),
        "schema": provenance.get("schema"),
        "expected_identity_set_sha256": provenance.get("expected_identity_set_sha256"),
        "corpus": list(MIG045_GATE12B_CORPUS),
    }


def request_mig045_gate12b_production_proof_freeze(
    request_fn: Callable[[dict], dict] = broker_request,
) -> dict:
    try:
        response = request_fn({"operation": "gate12b_technical_preflight"})
    except CommandPortError:
        raise
    except Exception as exc:
        raise CommandPortError("mig045_gate12b_runtime_preflight_failed") from exc
    normalized = _normalize_mig045_gate12b_runtime_preflight_response(response)
    return freeze_mig045_gate12b_production_proof(normalized)


def mig045_gate12b_persisted_result_sha256(wrapper: object) -> str:
    if not isinstance(wrapper, dict) or "result" not in wrapper:
        raise CommandPortError("mig045_gate12b_persisted_wrapper_invalid")
    persisted = wrapper.get("result")
    if not isinstance(persisted, dict):
        raise CommandPortError("mig045_gate12b_persisted_result_invalid")
    return hashlib.sha256(_gate12b_canonical_bytes(persisted)).hexdigest()


def _gate12b_input_payload(proof_id: str, proof_contract_sha256: str) -> tuple[str, str]:
    payload = {
        "proof_id": proof_id,
        "proof_contract_sha256": proof_contract_sha256,
    }
    raw = _gate12b_canonical_bytes(payload)
    return raw.decode("utf-8"), hashlib.sha256(raw).hexdigest()


def _gate12b_state_path(state_root: pathlib.Path, proof_id: str) -> pathlib.Path:
    return pathlib.Path(state_root) / "proof-executions" / f"{proof_id}.json"


def _gate12b_write_state(path: pathlib.Path, state: dict, *, create: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wire = _gate12b_canonical_bytes(state) + b"\n"
    if create:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(wire)
            handle.flush()
            os.fsync(handle.fileno())
        return
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(wire)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _gate12b_load_state(path: pathlib.Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CommandPortError("mig045_gate12b_state_invalid") from exc
    if not isinstance(value, dict):
        raise CommandPortError("mig045_gate12b_state_invalid")
    return value


def _gate12b_validate_state_binding(
    state: dict,
    proof_id: str,
    proof_contract_sha256: str,
    expected_identity_set_sha256: str,
    payload_sha256: str,
) -> None:
    if state.get("schema_version") != "mig045-gate12b-proof-execution-v2":
        raise CommandPortError("mig045_gate12b_state_invalid")
    if state.get("proof_id") != proof_id:
        raise CommandPortError("mig045_gate12b_state_invalid")
    if (
        state.get("proof_contract_sha256") != proof_contract_sha256
        or state.get("expected_identity_set_sha256") != expected_identity_set_sha256
        or state.get("payload_sha256") != payload_sha256
    ):
        raise CommandPortError("mig045_gate12b_proof_binding_conflict")
    if state.get("phase") not in {"BOUND", "STAGED", "PREPARED", "COMMITTED"}:
        raise CommandPortError("mig045_gate12b_state_invalid")


def _gate12b_procedure(proof_id: str, artifact_id: str) -> dict:
    return {
        "procedure_id": proof_id,
        "title": "MIG045 Gate12B committed proof transaction",
        "run_budget_seconds": 60,
        "steps": [{
            "step_id": "mig045-gate12b-committed-proof",
            "primitive": "postgres_command_template",
            "args": {
                "profile": "business",
                "template": MIG045_GATE12B_TEMPLATE,
                "input_artifact_id": artifact_id,
                "mode": "commit",
            },
            "timeout_seconds": 30,
        }],
    }


def _gate12b_result_identity(
    receipt: object,
    proof_contract: dict,
    proof_id: str,
    proof_contract_sha256: str,
    payload_sha256: str,
) -> dict:
    if (
        not isinstance(receipt, dict)
        or receipt.get("status") != "succeeded"
        or receipt.get("execution_class") != MIG045_GATE12B_EXECUTION_CLASS
        or not isinstance(receipt.get("run_id"), str)
        or not receipt.get("run_id")
    ):
        raise CommandPortError("mig045_gate12b_broker_receipt_invalid")
    steps = receipt.get("steps")
    if not isinstance(steps, list) or len(steps) != 1 or not isinstance(steps[0], dict):
        raise CommandPortError("mig045_gate12b_broker_receipt_invalid")
    step = steps[0]
    broker_result = step.get("result")
    if (
        step.get("step_id") != "mig045-gate12b-committed-proof"
        or step.get("status") != "success"
        or not isinstance(broker_result, dict)
        or broker_result.get("template") != MIG045_GATE12B_TEMPLATE
        or broker_result.get("mode") != "commit"
        or broker_result.get("committed") is not True
        or broker_result.get("input_sha256") != payload_sha256
        or not isinstance(broker_result.get("command_result"), dict)
        or not isinstance(broker_result.get("verification"), dict)
    ):
        raise CommandPortError("mig045_gate12b_broker_result_invalid")
    wrapper = broker_result["command_result"]
    if (
        wrapper.get("proof_id") != proof_id
        or wrapper.get("proof_contract_sha256") != proof_contract_sha256
        or not isinstance(wrapper.get("replayed"), bool)
        or not isinstance(wrapper.get("committed_at"), str)
        or not wrapper.get("committed_at")
    ):
        raise CommandPortError("mig045_gate12b_persisted_wrapper_binding_invalid")
    result_sha256 = mig045_gate12b_persisted_result_sha256(wrapper)
    expected_result_sha256 = proof_contract["expected_identity_set_sha256"]
    if result_sha256 != expected_result_sha256:
        raise CommandPortError("mig045_gate12b_persisted_result_sha256_mismatch")
    wrapper_sha256 = hashlib.sha256(_gate12b_canonical_bytes(wrapper)).hexdigest()
    return {
        "proof_id": proof_id,
        "postgres_proof_id": wrapper["proof_id"],
        "proof_contract_sha256": proof_contract_sha256,
        "expected_identity_set_sha256": expected_result_sha256,
        "result_sha256": result_sha256,
        "persisted_result": wrapper["result"],
        "committed_at": wrapper["committed_at"],
        "payload_sha256": payload_sha256,
        "broker_template": MIG045_GATE12B_TEMPLATE,
        "broker_idempotency_key": proof_id,
        "broker_procedure_id": proof_id,
        "broker_run_id": receipt["run_id"],
        "broker_result_sha256": wrapper_sha256,
        "ledger_replayed": wrapper["replayed"],
        "committed": True,
        "replayed": bool(receipt.get("replayed")) or wrapper["replayed"],
        "external_action_allowed": False,
    }


def _gate12b_cleanup_artifact(
    state_path: pathlib.Path,
    state: dict,
    request_fn: Callable[[dict], dict],
) -> None:
    if state.get("artifact_cleaned") is True:
        return
    artifact_id = state.get("artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise CommandPortError("mig045_gate12b_artifact_state_invalid")
    cleanup_response = request_fn({"operation": "cleanup_artifact", "artifact_id": artifact_id})
    if not isinstance(cleanup_response.get("result"), dict):
        raise CommandPortError("mig045_gate12b_transport_cleanup_invalid")
    state["artifact_cleaned"] = True
    _gate12b_write_state(state_path, state)


def run_mig045_gate12b_committed_proof_v1(
    proof_contract: dict,
    proof_contract_sha256: str,
    proof_id: str,
    request_fn: Callable[[dict], dict] = broker_request,
    *,
    preflight_fn: Callable[[], dict] | None = None,
    state_root: pathlib.Path | None = None,
) -> dict:
    contract = _validate_mig045_gate12b_proof_contract(proof_contract)
    expected_contract_sha = mig045_gate12b_proof_contract_sha256(contract)
    if proof_contract_sha256 != expected_contract_sha:
        raise CommandPortError("mig045_gate12b_proof_contract_sha256_mismatch")
    expected_proof_id = derive_mig045_gate12b_proof_id(expected_contract_sha)
    if proof_id != expected_proof_id:
        raise CommandPortError("mig045_gate12b_proof_id_mismatch")

    if preflight_fn is None:
        frozen = request_mig045_gate12b_production_proof_freeze(request_fn=request_fn)
        if (
            frozen.get("proof_contract") != contract
            or frozen.get("proof_contract_sha256") != expected_contract_sha
            or frozen.get("proof_id") != proof_id
        ):
            raise CommandPortError("mig045_gate12b_production_freeze_mismatch")
    else:
        try:
            observed_preflight = preflight_fn()
        except CommandPortError:
            raise
        except Exception as exc:
            raise CommandPortError("mig045_gate12b_preflight_failed") from exc
        _validate_gate12b_preflight(contract, observed_preflight)

    content, payload_sha256 = _gate12b_input_payload(proof_id, expected_contract_sha)
    root = pathlib.Path(
        state_root
        if state_root is not None
        else os.environ.get("ELAN_BRIDGE_STATE_ROOT", "/var/lib/elan-web-vps-bridge")
    )
    state_path = _gate12b_state_path(root, proof_id)
    initial = {
        "schema_version": "mig045-gate12b-proof-execution-v2",
        "proof_id": proof_id,
        "proof_contract_sha256": expected_contract_sha,
        "expected_identity_set_sha256": contract["expected_identity_set_sha256"],
        "payload_sha256": payload_sha256,
        "phase": "BOUND",
        "artifact_id": None,
        "plan_id": None,
        "procedure_sha256": None,
        "result": None,
        "artifact_cleaned": False,
    }
    try:
        _gate12b_write_state(state_path, initial, create=True)
        state = initial
    except FileExistsError:
        state = _gate12b_load_state(state_path)
        _gate12b_validate_state_binding(
            state,
            proof_id,
            expected_contract_sha,
            contract["expected_identity_set_sha256"],
            payload_sha256,
        )

    if state["phase"] == "COMMITTED":
        saved = state.get("result")
        if not isinstance(saved, dict):
            raise CommandPortError("mig045_gate12b_state_invalid")
        if saved.get("proof_id") != proof_id or saved.get("proof_contract_sha256") != expected_contract_sha:
            raise CommandPortError("mig045_gate12b_state_invalid")
        if state.get("artifact_cleaned") is not True:
            _gate12b_cleanup_artifact(state_path, state, request_fn)
        replay = dict(saved)
        replay["replayed"] = True
        return replay

    if state["phase"] == "BOUND":
        staged = request_fn({
            "operation": "stage_text",
            "content": content,
            "expected_sha256": payload_sha256,
            "media_type": "application/json",
            "label": f"mig045-gate12b-proof-{proof_id}",
        })
        state["artifact_id"] = _artifact_id(staged)
        state["phase"] = "STAGED"
        _gate12b_write_state(state_path, state)

    artifact_id = state.get("artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise CommandPortError("mig045_gate12b_artifact_state_invalid")
    procedure = _gate12b_procedure(proof_id, artifact_id)
    prepared = request_fn({
        "operation": "prepare_procedure",
        "mission_id": "EN-033/M1",
        "work_id": "MIG045-GATE12B-COMMITTED-PROOF",
        "technical_authority": "JA-023",
        "idempotency_key": proof_id,
        "procedure": procedure,
    })
    plan = prepared.get("plan")
    if (
        not isinstance(plan, dict)
        or plan.get("risk") not in {"mutating", MIG045_GATE12B_EXECUTION_CLASS}
        or not isinstance(plan.get("plan_id"), str)
        or not plan.get("plan_id")
        or not isinstance(plan.get("procedure_sha256"), str)
        or _GATE12B_SHA256_RE.fullmatch(plan["procedure_sha256"]) is None
    ):
        raise CommandPortError("mig045_gate12b_broker_plan_invalid")
    state["plan_id"] = plan["plan_id"]
    state["procedure_sha256"] = plan["procedure_sha256"]
    state["phase"] = "PREPARED"
    _gate12b_write_state(state_path, state)

    if plan.get("may_execute_same_turn") is False:
        recovered = request_fn({"operation": "get_run", "plan_id": plan["plan_id"]})
        receipt = recovered.get("receipt")
    else:
        execution_token = plan.get("execution_token")
        if not isinstance(execution_token, str) or not execution_token:
            raise CommandPortError("mig045_gate12b_execution_token_missing")
        executed = request_fn({
            "operation": "start_run",
            "plan_id": plan["plan_id"],
            "execution_token": execution_token,
            "procedure_sha256": plan["procedure_sha256"],
            "execution_class": MIG045_GATE12B_EXECUTION_CLASS,
            "mode": "sync",
        })
        receipt = executed.get("receipt")

    result = _gate12b_result_identity(
        receipt,
        contract,
        proof_id,
        expected_contract_sha,
        payload_sha256,
    )
    if plan.get("replayed") is True:
        result["replayed"] = True
    state["phase"] = "COMMITTED"
    state["result"] = result
    _gate12b_write_state(state_path, state)
    _gate12b_cleanup_artifact(state_path, state, request_fn)
    return result


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
    if not isinstance(steps, list) or len(steps) != 3:
        raise CommandPortError("broker_g6_schema_receipt_invalid")
    by_id = {
        step.get("step_id"): step
        for step in steps
        if isinstance(step, dict) and isinstance(step.get("step_id"), str)
    }
    if set(by_id) != {"schema-columns", "schema-functions", "schema-constraints"}:
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
    constraints_all = _reconstruct_g6_capture(
        by_id["schema-constraints"].get("result"),
        G6_SCHEMA_CONSTRAINTS_TEMPLATE,
        "constraints_indexes",
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
    constraints_indexes = [
        item
        for item in constraints_all
        if item.get("kind") in {"constraint", "index"}
        and item.get("table") in allowed_tables
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
        "constraints_indexes": constraints_indexes,
        "business_rows_emitted": False,
        "external_action_allowed": False,
    }
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
# EN2-P1 bounded canonical migration-registry read.
# The canonical read-all call remains a transport/provenance control, but a
# sanitizer-damaged aggregate must never prevent bounded technical registry
# entries from being read. The authoritative P1 diagnostic window is queried
# entry-by-entry through the already deployed MIG-037 template. No caller SQL,
# business row, or external action is permitted.
P1_MIGRATION_REGISTRY_TEMPLATE = "en033_m1_mig037_registry_read_all_v1"
P1_MIGRATION_REGISTRY_ENTRY_TEMPLATE = "en033_m1_mig037_registry_read_v1"
P1_MIGRATION_REGISTRY_IDS = (
    "MIG-042", "MIG-043", "MIG-044", "MIG-045", "MIG-046",
    "MIG-047", "MIG-048", "MIG-049", "MIG-050",
)


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
            "title": "EN2-P1 canonical registry read with bounded transport-safe recovery",
            "run_budget_seconds": 360,
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
    expected_count = 1 + len(P1_MIGRATION_REGISTRY_IDS)
    if not isinstance(receipt_steps, list) or len(receipt_steps) != expected_count:
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
        except json.JSONDecodeError:
            read_all_transport = "UNPARSEABLE_BOUNDED_FALLBACK"
        else:
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

    migration_presence = {
        migration_id: bounded_by_id[migration_id] is not None
        for migration_id in P1_MIGRATION_REGISTRY_IDS
    }
    present_ids = [
        migration_id
        for migration_id in P1_MIGRATION_REGISTRY_IDS
        if migration_presence[migration_id]
    ]
    latest_migration = max(present_ids) if present_ids else None

    return {
        "status": "succeeded",
        "execution_class": "read_only",
        "database_profile": "business",
        "template": P1_MIGRATION_REGISTRY_TEMPLATE,
        "entry_template": P1_MIGRATION_REGISTRY_ENTRY_TEMPLATE,
        "canonical_read_all_invoked": True,
        "read_all_transport": read_all_transport,
        "bounded_window": list(P1_MIGRATION_REGISTRY_IDS),
        "entries": entries,
        "migration_presence": migration_presence,
        "missing_migration_ids": missing_migration_ids,
        "latest_migration": latest_migration,
        "run_id": receipt.get("run_id"),
        "replayed": bool(receipt.get("replayed")),
        "business_rows_emitted": False,
        "free_sql": False,
        "external_action_allowed": False,
    }

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
MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS = "reversible_technical_change"
MIG045_GATE12B_TECHNICAL_RESOURCE_LOCK = "postgres-business-en033-mig045-gate12b"


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
        or plan.get("risk") not in {"reversible", MIG045_GATE12B_TECHNICAL_EXECUTION_CLASS}
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
