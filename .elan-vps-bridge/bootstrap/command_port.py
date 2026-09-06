#!/usr/bin/env python3
"""Transient D-owner Gate12B materialization repair layered on the qualified Bridge command port."""
from __future__ import annotations

import hashlib
import importlib.util
import os
import pathlib
import time
from typing import Callable

_RELEASE_ID = "bridge-mig045-gate12b-broker-marker-runtime-repair-20260906-v1"
_DEFAULT_PREVIOUS = pathlib.Path(
    "/var/lib/elan-web-vps-bridge/runtime-updates"
) / _RELEASE_ID / "previous" / "command_port.py"
_PREVIOUS_PATH = pathlib.Path(os.environ.get("ELAN_BRIDGE_PREVIOUS_COMMAND_PORT", str(_DEFAULT_PREVIOUS)))
if not _PREVIOUS_PATH.is_file():
    raise ImportError("gate12b_previous_command_port_missing")

_spec = importlib.util.spec_from_file_location("_elan_gate12b_previous_command_port", _PREVIOUS_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError("gate12b_previous_command_port_unloadable")
_previous = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_previous)
for _name in dir(_previous):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_previous, _name)

_ORIGINAL_MATERIALIZE = _previous.run_mig045_gate12b_technical_materialization_v1
_BROKER_UNIT = "elan-vps-v1-broker.service"
_BROKER_DESTINATION = "/usr/local/sbin/elan-vps-v1-broker"
_STABLE_V1351_BROKER = (
    "/var/lib/elan-vps-v1/work/v1.3-build/"
    "observer/v1.3.0/actions/elan-vps-v1-broker"
)
_EXPECTED_V1351_BROKER_SHA256 = "f05ad6de45a6029b82d51f75e3f97eda7ff48412fdece71b1f183b6c9c18e224"
_HOTFIX_CONTRACT = "schema_migration_exact_membership_v1"
_BAD_MARKER_SQL = "SELECT COALESCE(max(migration_id),'') FROM elan_naturel.schema_migrations"
_GOOD_MARKER_SQL = "SELECT migration_id FROM elan_naturel.schema_migrations ORDER BY migration_id"
_MEMBERSHIP_ANCHOR = (
    'if primitive=="postgres_migration_apply" and args["expected_migration"] '
    'not in after.stdout.decode(errors="replace"):'
)
_MEMBERSHIP_REPLACEMENT = (
    'if primitive=="postgres_migration_apply" and args["expected_migration"] '
    'not in after.stdout.decode(errors="replace").splitlines():'
)


def _transient_broker_wrapper_text() -> str:
    template = """#!/usr/bin/env python3
import hashlib
import pathlib

SOURCE = pathlib.Path(__SOURCE__)
EXPECTED_SHA256 = __EXPECTED_SHA__
BAD_MARKER_SQL = __BAD_SQL__
GOOD_MARKER_SQL = __GOOD_SQL__
HOTFIX_CONTRACT = __CONTRACT__
ANCHOR = __ANCHOR__
REPLACEMENT = __REPLACEMENT__

raw = SOURCE.read_bytes()
if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
    raise SystemExit("gate12b_stable_v1351_broker_sha256_mismatch")
source = raw.decode("utf-8")
if source.count(ANCHOR) != 1:
    raise SystemExit("gate12b_membership_anchor_invalid")
source = source.replace(ANCHOR, REPLACEMENT)
overlay = '''
_MIG045_MARKER_BASE_POSTGRES_PROFILE = Broker._postgres_profile
_MIG045_MARKER_BASE_STATUS = Broker.status
_MIG045_MARKER_BAD_SQL = __BAD_SQL__
_MIG045_MARKER_GOOD_SQL = __GOOD_SQL__
_MIG045_MARKER_CONTRACT = __CONTRACT__

def _mig045_marker_postgres_profile(self, name):
    profile = _MIG045_MARKER_BASE_POSTGRES_PROFILE(self, name)
    if profile.get("migration_marker_sql") == _MIG045_MARKER_BAD_SQL:
        profile = dict(profile)
        profile["migration_marker_sql"] = _MIG045_MARKER_GOOD_SQL
    return profile

def _mig045_marker_status(self):
    value = _MIG045_MARKER_BASE_STATUS(self)
    value["postgres_migration_marker_contract"] = _MIG045_MARKER_CONTRACT
    return value

Broker._postgres_profile = _mig045_marker_postgres_profile
Broker.status = _mig045_marker_status
'''
source += "\\n" + overlay
namespace = {"__name__": "__main__", "__file__": str(SOURCE)}
exec(compile(source, str(SOURCE), "exec"), namespace, namespace)
"""
    replacements = {
        "__SOURCE__": repr(_STABLE_V1351_BROKER),
        "__EXPECTED_SHA__": repr(_EXPECTED_V1351_BROKER_SHA256),
        "__BAD_SQL__": repr(_BAD_MARKER_SQL),
        "__GOOD_SQL__": repr(_GOOD_MARKER_SQL),
        "__CONTRACT__": repr(_HOTFIX_CONTRACT),
        "__ANCHOR__": repr(_MEMBERSHIP_ANCHOR),
        "__REPLACEMENT__": repr(_MEMBERSHIP_REPLACEMENT),
    }
    for token, value in replacements.items():
        template = template.replace(token, value)
    return template


def _plan_fields(plan: object, expected_risk: str) -> dict:
    if not isinstance(plan, dict) or plan.get("risk") != expected_risk:
        raise CommandPortError("gate12b_hotfix_plan_risk_invalid")
    required = ("plan_id", "execution_token", "procedure_sha256")
    if any(not isinstance(plan.get(field), str) or not plan.get(field) for field in required):
        raise CommandPortError("gate12b_hotfix_plan_invalid")
    return plan


def _start(plan: dict, execution_class: str, mode: str, request_fn: Callable[[dict], dict]) -> dict:
    return request_fn({
        "operation": "start_run",
        "plan_id": plan["plan_id"],
        "execution_token": plan["execution_token"],
        "procedure_sha256": plan["procedure_sha256"],
        "execution_class": execution_class,
        "mode": mode,
    })


def _prepare(procedure: dict, key: str, request_fn: Callable[[dict], dict], expected_risk: str) -> dict:
    prepared = request_fn({
        "operation": "prepare_procedure",
        "mission_id": "EN-033/M1",
        "work_id": "MIG045-GATE12B-BROKER-MARKER-RUNTIME-REPAIR",
        "technical_authority": "JA-023",
        "idempotency_key": key,
        "procedure": procedure,
    })
    return _plan_fields(prepared.get("plan"), expected_risk)


def _verify_stable_v1351_source(request_key: str, request_fn: Callable[[dict], dict]) -> None:
    procedure = {
        "procedure_id": f"gate12b-marker-source-{request_key}",
        "title": "Gate12B stable 1.3.51 broker source readback",
        "run_budget_seconds": 60,
        "steps": [{
            "step_id": "stable-v1351-broker",
            "primitive": "file_preflight",
            "args": {"items": [{
                "path": _STABLE_V1351_BROKER,
                "expected_sha256": _EXPECTED_V1351_BROKER_SHA256,
            }]},
            "timeout_seconds": 30,
        }],
    }
    plan = _prepare(procedure, f"gate12b-marker-source-{request_key}", request_fn, "read_only")
    executed = _start(plan, "read_only", "sync", request_fn)
    receipt = executed.get("receipt")
    if not isinstance(receipt, dict) or receipt.get("status") != "succeeded":
        raise CommandPortError("gate12b_stable_v1351_broker_preflight_failed")


def _install_transient_wrapper(request_key: str, request_fn: Callable[[dict], dict]) -> str:
    status = request_fn({"operation": "status"})
    if status.get("server_version") != "1.3.51":
        raise CommandPortError("gate12b_hotfix_requires_v1351")
    _verify_stable_v1351_source(request_key, request_fn)

    content = _transient_broker_wrapper_text()
    raw = content.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    staged = request_fn({
        "operation": "stage_text",
        "content": content,
        "expected_sha256": digest,
        "media_type": "text/x-python",
        "label": "mig045-gate12b-transient-broker-wrapper",
    })
    artifact = staged.get("artifact")
    if not isinstance(artifact, dict) or artifact.get("sha256") != digest:
        raise CommandPortError("gate12b_hotfix_stage_failed")
    artifact_id = artifact.get("artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise CommandPortError("gate12b_hotfix_stage_invalid")

    procedure = {
        "procedure_id": f"gate12b-marker-install-{request_key}",
        "title": "Gate12B transient broker marker repair install",
        "run_budget_seconds": 90,
        "steps": [{
            "step_id": "install-broker-marker-hotfix",
            "primitive": "install_file_atomic",
            "args": {
                "artifact_id": artifact_id,
                "destination": _BROKER_DESTINATION,
                "mode": "0755",
            },
            "timeout_seconds": 60,
        }],
    }
    plan = _prepare(
        procedure,
        f"gate12b-marker-install-{request_key}",
        request_fn,
        "reversible_technical_change",
    )
    executed = _start(plan, "reversible_technical_change", "sync", request_fn)
    receipt = executed.get("receipt")
    if not isinstance(receipt, dict) or receipt.get("status") != "succeeded":
        raise CommandPortError("gate12b_hotfix_install_failed")
    return artifact_id


def _submit_restart(request_key: str, phase: str, request_fn: Callable[[dict], dict]) -> None:
    procedure = {
        "procedure_id": f"gate12b-broker-restart-{phase}-{request_key}",
        "title": f"Gate12B broker restart {phase}",
        "run_budget_seconds": 90,
        "steps": [{
            "step_id": "restart-broker",
            "primitive": "systemd_unit",
            "args": {"unit": _BROKER_UNIT, "action": "restart"},
            "timeout_seconds": 60,
        }],
    }
    plan = _prepare(
        procedure,
        f"gate12b-broker-restart-{phase}-{request_key}",
        request_fn,
        "reversible_technical_change",
    )
    queued = _start(plan, "reversible_technical_change", "async", request_fn)
    receipt = queued.get("receipt")
    if not isinstance(receipt, dict) or receipt.get("status") not in {"queued", "running"}:
        raise CommandPortError("gate12b_broker_restart_not_queued")


def _wait_broker(
    *,
    version: str,
    marker_contract: str | None,
    request_fn: Callable[[dict], dict],
    timeout_seconds: int = 120,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            status = request_fn({"operation": "status"})
            if status.get("server_version") != version:
                time.sleep(2)
                continue
            observed = status.get("postgres_migration_marker_contract")
            if marker_contract is None:
                if observed is not None:
                    time.sleep(2)
                    continue
            elif observed != marker_contract:
                time.sleep(2)
                continue
            return status
        except Exception as exc:
            last_error = exc
            time.sleep(2)
    if last_error:
        raise CommandPortError("gate12b_broker_restart_readback_timeout") from last_error
    raise CommandPortError("gate12b_broker_restart_readback_timeout")


def _cleanup_artifact_safely(artifact_id: str | None, request_fn: Callable[[dict], dict]) -> None:
    if not artifact_id:
        return
    try:
        request_fn({"operation": "cleanup_artifact", "artifact_id": artifact_id})
    except Exception:
        pass


def run_mig045_gate12b_technical_materialization_v1(
    request_id: str,
    artifact_url: str,
    request_fn: Callable[[dict], dict] = broker_request,
    fetch_fn: Callable[[str], bytes] = _fetch_control_path,
    ready_fn: Callable[[], dict] = _mig045_gate12b_wait_ready_v1352,
) -> dict:
    request_key = _safe_key(request_id).lower()
    hotfix_artifact_id: str | None = None
    try:
        hotfix_artifact_id = _install_transient_wrapper(request_key, request_fn)
        _submit_restart(request_key, "hotfix", request_fn)
        hotfix_status = _wait_broker(
            version="1.3.51",
            marker_contract=_HOTFIX_CONTRACT,
            request_fn=request_fn,
        )

        release_install_seen = False

        def proxy(payload: dict) -> dict:
            nonlocal release_install_seen
            response = request_fn(payload)
            if payload.get("operation") == "start_run":
                receipt = response.get("receipt")
                steps = receipt.get("steps") if isinstance(receipt, dict) else None
                if isinstance(steps, list):
                    for step in steps:
                        if (
                            isinstance(step, dict)
                            and step.get("step_id") == "qualified-release-install"
                            and step.get("status") == "success"
                        ):
                            release_install_seen = True
                            _submit_restart(request_key, "target", request_fn)
                            _wait_broker(version="1.3.52", marker_contract=None, request_fn=request_fn)
                            break
            return response

        result = _ORIGINAL_MATERIALIZE(
            request_id,
            artifact_url,
            request_fn=proxy,
            fetch_fn=fetch_fn,
            ready_fn=ready_fn,
        )
        if not release_install_seen:
            raise CommandPortError("gate12b_target_release_install_not_observed")
        target_status = _wait_broker(version="1.3.52", marker_contract=None, request_fn=request_fn)
        return {
            **result,
            "broker_marker_repair": {
                "status": "PASS",
                "transient": True,
                "contract": _HOTFIX_CONTRACT,
                "hotfix_process_version": hotfix_status.get("server_version"),
                "target_process_version": target_status.get("server_version"),
                "business_reads": 0,
                "proof_executed": False,
                "database_observations_added": 0,
            },
        }
    finally:
        _cleanup_artifact_safely(hotfix_artifact_id, request_fn)
