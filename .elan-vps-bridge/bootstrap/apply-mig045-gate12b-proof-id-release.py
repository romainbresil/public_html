#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
ISSUE_INBOX = ROOT / "issue_inbox.py"
COMMAND_PORT = ROOT / "command_port.py"
BRIDGE_WORKER = ROOT / "bridge_worker.py"
MANIFEST = ROOT / "runtime-manifest.json"


def replace_once(path: pathlib.Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected_one_fragment:{path.name}:{count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def patch_command_port() -> None:
    replace_once(
        COMMAND_PORT,
        "import os\nimport re\nimport socket\n",
        "import os\nimport pathlib\nimport re\nimport socket\n",
    )
    replace_once(
        COMMAND_PORT,
        'MIG045_READYZ_URL = "http://127.0.0.1:8787/readyz"\n_SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]+")\n',
        '''MIG045_READYZ_URL = "http://127.0.0.1:8787/readyz"\nMIG045_GATE12B_TARGET = "mig045-gate12b-committed-proof"\nMIG045_GATE12B_EXPECTED_IDENTITY_SET_SHA256 = "dc731702f983999e083563477216054bfcee5674eff03a5d6ef8cb479b0c2cc1"\nMIG045_GATE12B_TEMPLATE = "en033_m1_mig045_gate12b_committed_proof_v1"\nMIG045_GATE12B_EXECUTION_CLASS = "mutating_technical_change"\n_GATE12B_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")\n_SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]+")\n''',
    )

    marker = "\n\ndef build_en2_g4_canary_payload_v1(request_id: str) -> dict:\n"
    implementation = r'''

def _validate_gate12b_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _GATE12B_SHA256_RE.fullmatch(value) is None:
        raise CommandPortError(f"mig045_gate12b_{label}_invalid")
    return value


def _gate12b_canonical_payload(
    proof_id: str,
    proof_contract_sha256: str,
    expected_identity_set_sha256: str,
) -> tuple[str, str]:
    payload = {
        "target": MIG045_GATE12B_TARGET,
        "proof_id": proof_id,
        "proof_contract_sha256": proof_contract_sha256,
        "expected_identity_set_sha256": expected_identity_set_sha256,
    }
    content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return content, hashlib.sha256(content.encode("utf-8")).hexdigest()


def _gate12b_state_path(state_root: pathlib.Path, proof_id: str) -> pathlib.Path:
    return pathlib.Path(state_root) / "proof-executions" / f"{proof_id}.json"


def _gate12b_write_state(path: pathlib.Path, state: dict, *, create: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wire = (
        json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    if create:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise
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


def _gate12b_validate_binding(
    state: dict,
    proof_id: str,
    proof_contract_sha256: str,
    expected_identity_set_sha256: str,
    payload_sha256: str,
) -> None:
    if state.get("schema_version") != "mig045-gate12b-proof-execution-v1":
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


def _gate12b_result_identity(
    receipt: object,
    proof_id: str,
    proof_contract_sha256: str,
    expected_identity_set_sha256: str,
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
    result = step.get("result")
    if (
        step.get("step_id") != "mig045-gate12b-committed-proof"
        or step.get("status") != "success"
        or not isinstance(result, dict)
        or result.get("template") != MIG045_GATE12B_TEMPLATE
        or result.get("mode") != "commit"
        or result.get("committed") is not True
        or result.get("input_sha256") != payload_sha256
        or not isinstance(result.get("command_result"), dict)
        or not isinstance(result.get("verification"), dict)
    ):
        raise CommandPortError("mig045_gate12b_broker_result_invalid")
    result_wire = json.dumps(
        result,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    logical_key = f"mig045-gate12b-proof-{proof_id}"
    return {
        "proof_id": proof_id,
        "proof_contract_sha256": proof_contract_sha256,
        "expected_identity_set_sha256": expected_identity_set_sha256,
        "payload_sha256": payload_sha256,
        "broker_template": MIG045_GATE12B_TEMPLATE,
        "broker_idempotency_key": logical_key,
        "broker_procedure_id": logical_key,
        "broker_run_id": receipt["run_id"],
        "broker_result_sha256": hashlib.sha256(result_wire).hexdigest(),
        "committed": True,
        "replayed": bool(receipt.get("replayed")),
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
    proof_id: str,
    proof_contract_sha256: str,
    expected_identity_set_sha256: str,
    request_fn: Callable[[dict], dict] = broker_request,
    *,
    state_root: pathlib.Path | None = None,
) -> dict:
    proof_id = _validate_gate12b_sha256(proof_id, "proof_id")
    proof_contract_sha256 = _validate_gate12b_sha256(
        proof_contract_sha256, "proof_contract_sha256"
    )
    expected_identity_set_sha256 = _validate_gate12b_sha256(
        expected_identity_set_sha256, "expected_identity_set_sha256"
    )
    if expected_identity_set_sha256 != MIG045_GATE12B_EXPECTED_IDENTITY_SET_SHA256:
        raise CommandPortError("mig045_gate12b_expected_identity_set_sha256_mismatch")

    content, payload_sha256 = _gate12b_canonical_payload(
        proof_id,
        proof_contract_sha256,
        expected_identity_set_sha256,
    )
    root = pathlib.Path(
        state_root
        if state_root is not None
        else os.environ.get("ELAN_BRIDGE_STATE_ROOT", "/var/lib/elan-web-vps-bridge")
    )
    state_path = _gate12b_state_path(root, proof_id)
    initial = {
        "schema_version": "mig045-gate12b-proof-execution-v1",
        "proof_id": proof_id,
        "proof_contract_sha256": proof_contract_sha256,
        "expected_identity_set_sha256": expected_identity_set_sha256,
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
        _gate12b_validate_binding(
            state,
            proof_id,
            proof_contract_sha256,
            expected_identity_set_sha256,
            payload_sha256,
        )

    if state["phase"] == "COMMITTED":
        result = state.get("result")
        if not isinstance(result, dict):
            raise CommandPortError("mig045_gate12b_state_invalid")
        if state.get("artifact_cleaned") is not True:
            _gate12b_cleanup_artifact(state_path, state, request_fn)
        replay = dict(result)
        replay["replayed"] = True
        return replay

    if state["phase"] == "PREPARED":
        plan_id = state.get("plan_id")
        if not isinstance(plan_id, str) or not plan_id:
            raise CommandPortError("mig045_gate12b_state_invalid")
        try:
            recovered = request_fn({"operation": "get_run", "plan_id": plan_id})
        except CommandPortError as exc:
            if str(exc) != "run_unavailable":
                raise
        else:
            receipt = recovered.get("receipt")
            result = _gate12b_result_identity(
                receipt,
                proof_id,
                proof_contract_sha256,
                expected_identity_set_sha256,
                payload_sha256,
            )
            result["replayed"] = True
            state["phase"] = "COMMITTED"
            state["result"] = result
            _gate12b_write_state(state_path, state)
            _gate12b_cleanup_artifact(state_path, state, request_fn)
            return result

    if state["phase"] == "BOUND":
        staged = request_fn({
            "operation": "stage_text",
            "content": content,
            "expected_sha256": payload_sha256,
            "media_type": "application/json",
            "label": f"mig045-gate12b-proof-{proof_id}",
        })
        artifact_id = _artifact_id(staged)
        state["artifact_id"] = artifact_id
        state["phase"] = "STAGED"
        _gate12b_write_state(state_path, state)

    artifact_id = state.get("artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise CommandPortError("mig045_gate12b_artifact_state_invalid")
    logical_key = f"mig045-gate12b-proof-{proof_id}"
    prepared = request_fn({
        "operation": "prepare_procedure",
        "mission_id": "EN-033/M1",
        "work_id": "MIG045-GATE12B-COMMITTED-PROOF",
        "technical_authority": "JA-023",
        "idempotency_key": logical_key,
        "procedure": {
            "procedure_id": logical_key,
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
        },
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
        proof_id,
        proof_contract_sha256,
        expected_identity_set_sha256,
        payload_sha256,
    )
    if plan.get("replayed") is True:
        result["replayed"] = True
    state["phase"] = "COMMITTED"
    state["result"] = result
    _gate12b_write_state(state_path, state)
    _gate12b_cleanup_artifact(state_path, state, request_fn)
    return result
'''
    replace_once(COMMAND_PORT, marker, implementation + marker)


def patch_issue_inbox() -> None:
    replace_once(
        ISSUE_INBOX,
        'MIG045_V1351_INTENT = "MIG045_V1351_ROLLOUT_AND_FRESH_READ"\nMIG045_V1351_TARGET = "mig045-v1351-rollout-and-fresh-read"\nSELF_UPDATE_INTENT = "BRIDGE_SELF_UPDATE"\n',
        '''MIG045_V1351_INTENT = "MIG045_V1351_ROLLOUT_AND_FRESH_READ"\nMIG045_V1351_TARGET = "mig045-v1351-rollout-and-fresh-read"\nMIG045_GATE12B_INTENT = "MIG045_GATE12B_COMMITTED_PROOF_V1"\nMIG045_GATE12B_TARGET = command_port.MIG045_GATE12B_TARGET\nMIG045_GATE12B_EXPECTED_IDENTITY_SET_SHA256 = command_port.MIG045_GATE12B_EXPECTED_IDENTITY_SET_SHA256\nSELF_UPDATE_INTENT = "BRIDGE_SELF_UPDATE"\n''',
    )

    old_parse = '''    if job["intent_code"] == MIG045_V1351_INTENT:\n        context = job["context"]\n        if not isinstance(context, dict) or set(context) != {"target", "artifact_url"}:\n            return None\n        if context.get("target") != MIG045_V1351_TARGET:\n            return None\n        try:\n            command_port.validate_mig045_v1351_artifact_url(context.get("artifact_url"))\n        except command_port.CommandPortError:\n            return None\n        return job\n    if job["intent_code"] == SELF_UPDATE_INTENT:\n'''
    new_parse = '''    if job["intent_code"] == MIG045_V1351_INTENT:\n        context = job["context"]\n        if not isinstance(context, dict) or set(context) != {"target", "artifact_url"}:\n            return None\n        if context.get("target") != MIG045_V1351_TARGET:\n            return None\n        try:\n            command_port.validate_mig045_v1351_artifact_url(context.get("artifact_url"))\n        except command_port.CommandPortError:\n            return None\n        return job\n    if job["intent_code"] == MIG045_GATE12B_INTENT:\n        context = job["context"]\n        if (\n            not isinstance(context, dict)\n            or set(context)\n            != {\n                "target",\n                "proof_id",\n                "proof_contract_sha256",\n                "expected_identity_set_sha256",\n            }\n            or context.get("target") != MIG045_GATE12B_TARGET\n            or not isinstance(context.get("proof_id"), str)\n            or _SHA256_RE.fullmatch(context["proof_id"]) is None\n            or not isinstance(context.get("proof_contract_sha256"), str)\n            or _SHA256_RE.fullmatch(context["proof_contract_sha256"]) is None\n            or context.get("expected_identity_set_sha256")\n            != MIG045_GATE12B_EXPECTED_IDENTITY_SET_SHA256\n        ):\n            return None\n        return job\n    if job["intent_code"] == SELF_UPDATE_INTENT:\n'''
    replace_once(ISSUE_INBOX, old_parse, new_parse)

    old_execute = '''    if job["intent_code"] == MIG045_V1351_INTENT:\n        try:\n            payload = command_port.run_mig045_v1351_rollout_and_fresh_read_v1(\n                job["id"],\n                job["context"]["artifact_url"],\n            )\n            return _completed(job, started, {"status": "PASS", **payload})\n        except command_port.CommandPortError as exc:\n            return _failed(job, started, str(exc))\n    if job["intent_code"] == SELF_UPDATE_INTENT:\n'''
    new_execute = '''    if job["intent_code"] == MIG045_V1351_INTENT:\n        try:\n            payload = command_port.run_mig045_v1351_rollout_and_fresh_read_v1(\n                job["id"],\n                job["context"]["artifact_url"],\n            )\n            return _completed(job, started, {"status": "PASS", **payload})\n        except command_port.CommandPortError as exc:\n            return _failed(job, started, str(exc))\n    if job["intent_code"] == MIG045_GATE12B_INTENT:\n        try:\n            context = job["context"]\n            payload = command_port.run_mig045_gate12b_committed_proof_v1(\n                context["proof_id"],\n                context["proof_contract_sha256"],\n                context["expected_identity_set_sha256"],\n            )\n            return _completed(job, started, {"status": "PASS", **payload})\n        except command_port.CommandPortError as exc:\n            return _failed(job, started, str(exc))\n    if job["intent_code"] == SELF_UPDATE_INTENT:\n'''
    replace_once(ISSUE_INBOX, old_execute, new_execute)


def write_manifest() -> None:
    release_id = "bridge-mig045-gate12b-proof-id-20260905-v1"
    files = {}
    for path in (ISSUE_INBOX, BRIDGE_WORKER, COMMAND_PORT):
        files[path.name] = {
            "path": f".elan-vps-bridge/bootstrap/{path.name}",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    payload = {
        "files": files,
        "release_id": release_id,
        "schema_version": "1.0",
    }
    MANIFEST.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    patch_command_port()
    patch_issue_inbox()
    write_manifest()
    print("MIG045_GATE12B_PROOF_ID_PATCH_MATERIALIZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
