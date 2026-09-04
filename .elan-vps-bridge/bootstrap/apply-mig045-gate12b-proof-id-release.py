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
RELEASE_ID = "bridge-mig045-gate12b-canonical-proof-20260905-v2"


def replace_once(path: pathlib.Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected_one_fragment:{path.name}:{count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def replace_between(path: pathlib.Path, start: str, end: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    start_index = text.find(start)
    end_index = text.find(end, start_index + len(start))
    if start_index < 0 or end_index < 0:
        raise SystemExit(f"expected_markers:{path.name}")
    path.write_text(text[:start_index] + replacement + text[end_index:], encoding="utf-8")


COMMAND_PORT_CONSTANTS_V1 = '''MIG045_GATE12B_TARGET = "mig045-gate12b-committed-proof"\nMIG045_GATE12B_EXPECTED_IDENTITY_SET_SHA256 = "dc731702f983999e083563477216054bfcee5674eff03a5d6ef8cb479b0c2cc1"\nMIG045_GATE12B_TEMPLATE = "en033_m1_mig045_gate12b_committed_proof_v1"\nMIG045_GATE12B_EXECUTION_CLASS = "mutating_technical_change"\n_GATE12B_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")\n'''

COMMAND_PORT_CONSTANTS_V2 = '''MIG045_GATE12B_TARGET = "mig045-gate12b-committed-proof"\nMIG045_GATE12B_EXPECTED_IDENTITY_SET_SHA256 = "dc731702f983999e083563477216054bfcee5674eff03a5d6ef8cb479b0c2cc1"\nMIG045_GATE12B_TEMPLATE = "en033_m1_mig045_gate12b_committed_proof_v1"\nMIG045_GATE12B_EXECUTION_CLASS = "mutating_technical_change"\nMIG045_GATE12B_OBSERVATION_SEMANTICS = "COMMITTED_PROOF_TRANSACTION_V1"\nMIG045_GATE12B_PROOF_ID_DOMAIN = "EN033/M1:MIG045:G12B:COMMITTED_PROOF_TRANSACTION_V1:"\nMIG045_GATE12B_CORPUS = tuple(f"CON-{number:03d}" for number in range(20, 28))\n_GATE12B_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")\n_GATE12B_COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")\n_GATE12B_RUNTIME_VERSION_RE = re.compile(r"^[0-9]+\\.[0-9]+\\.[0-9]+$")\n_GATE12B_PROOF_CONTRACT_FIELDS = frozenset({\n    "observation_semantics",\n    "expected_identity_set_sha256",\n    "corpus",\n    "runtime_version",\n    "runtime_source_commit",\n    "capability_sha256",\n    "effective_policy_sha256",\n    "command_template_sha256",\n    "sql_owner_sha256",\n    "target_binding_sha256",\n})\n_GATE12B_PREFLIGHT_FIELDS = (\n    "runtime_version",\n    "runtime_source_commit",\n    "capability_sha256",\n    "effective_policy_sha256",\n    "command_template_sha256",\n    "sql_owner_sha256",\n    "target_binding_sha256",\n)\n'''

NEW_GATE12B_BLOCK = r'''
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
    runtime_version = value.get("runtime_version")
    if not isinstance(runtime_version, str) or _GATE12B_RUNTIME_VERSION_RE.fullmatch(runtime_version) is None:
        raise CommandPortError("mig045_gate12b_runtime_version_invalid")
    runtime_source_commit = value.get("runtime_source_commit")
    if not isinstance(runtime_source_commit, str) or _GATE12B_COMMIT_RE.fullmatch(runtime_source_commit) is None:
        raise CommandPortError("mig045_gate12b_runtime_source_commit_invalid")
    for field in (
        "capability_sha256",
        "effective_policy_sha256",
        "command_template_sha256",
        "sql_owner_sha256",
        "target_binding_sha256",
    ):
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
        raise CommandPortError("mig045_gate12b_preflight_owner_not_bound")
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

'''


ISSUE_PARSE_V2 = '''    if job["intent_code"] == MIG045_GATE12B_INTENT:\n        try:\n            job["context"] = command_port.validate_mig045_gate12b_context(job["context"])\n        except command_port.CommandPortError:\n            return None\n        return job\n'''

ISSUE_EXECUTE_V2 = '''    if job["intent_code"] == MIG045_GATE12B_INTENT:\n        try:\n            context = command_port.validate_mig045_gate12b_context(job["context"])\n            payload = command_port.run_mig045_gate12b_committed_proof_v1(\n                context["proof_contract"],\n                context["proof_contract_sha256"],\n                context["proof_id"],\n            )\n            return _completed(job, started, {"status": "PASS", **payload})\n        except command_port.CommandPortError as exc:\n            return _failed(job, started, str(exc))\n'''

CLAIM_HELPER = r'''
def _gate12b_claim_blocks_retry(state_root: pathlib.Path, job: dict) -> bool:
    if job.get("intent_code") != MIG045_GATE12B_INTENT:
        return True
    result_path = pathlib.Path(state_root) / "results" / f"{job['id']}.json"
    if not result_path.is_file():
        return False
    try:
        stored = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return (
        isinstance(stored, dict)
        and stored.get("id") == job.get("id")
        and stored.get("intent_code") == MIG045_GATE12B_INTENT
        and stored.get("state") == "COMPLETED"
        and isinstance(stored.get("result"), dict)
        and stored["result"].get("status") == "PASS"
        and isinstance(stored.get("context"), dict)
        and stored["context"].get("proof_id") == job["context"].get("proof_id")
    )

'''


def patch_command_port() -> None:
    text = COMMAND_PORT.read_text(encoding="utf-8")
    if "MIG045_GATE12B_PROOF_ID_DOMAIN =" in text:
        return
    replace_once(COMMAND_PORT, COMMAND_PORT_CONSTANTS_V1, COMMAND_PORT_CONSTANTS_V2)
    replace_between(
        COMMAND_PORT,
        "\ndef _validate_gate12b_sha256",
        "\ndef build_en2_g4_canary_payload_v1",
        "\n" + NEW_GATE12B_BLOCK,
    )


def patch_issue_inbox() -> None:
    text = ISSUE_INBOX.read_text(encoding="utf-8")
    if "_gate12b_claim_blocks_retry" in text:
        return
    parse_start = '    if job["intent_code"] == MIG045_GATE12B_INTENT:\n'
    parse_end = '    if job["intent_code"] == SELF_UPDATE_INTENT:\n'
    first = text.find(parse_start)
    first_end = text.find(parse_end, first)
    if first < 0 or first_end < 0:
        raise SystemExit("issue_parse_gate12b_markers_missing")
    text = text[:first] + ISSUE_PARSE_V2 + text[first_end:]

    execute_start = '    if job["intent_code"] == MIG045_GATE12B_INTENT:\n'
    execute_end = '    if job["intent_code"] == SELF_UPDATE_INTENT:\n'
    second = text.find(execute_start, text.find("def _execute_job"))
    second_end = text.find(execute_end, second)
    if second < 0 or second_end < 0:
        raise SystemExit("issue_execute_gate12b_markers_missing")
    text = text[:second] + ISSUE_EXECUTE_V2 + text[second_end:]

    process_marker = "\n\ndef process_issue(state_root: pathlib.Path, issue: dict) -> str:\n"
    if process_marker not in text:
        raise SystemExit("issue_process_marker_missing")
    text = text.replace(process_marker, "\n" + CLAIM_HELPER + "\ndef process_issue(state_root: pathlib.Path, issue: dict) -> str:\n", 1)

    old_claim = '''    try:\n        bridge_worker.create_claim(state_root, job["id"], source_sha)\n    except bridge_worker.AlreadyClaimed:\n        return "ALREADY_CLAIMED"\n'''
    new_claim = '''    try:\n        bridge_worker.create_claim(state_root, job["id"], source_sha)\n    except bridge_worker.AlreadyClaimed:\n        if _gate12b_claim_blocks_retry(state_root, job):\n            return "ALREADY_CLAIMED"\n'''
    if old_claim not in text:
        raise SystemExit("issue_claim_fragment_missing")
    text = text.replace(old_claim, new_claim, 1)

    old_poll = '''        job_id = job["id"]\n        if bridge_worker._claim_path(state_root, job_id).exists():\n            continue\n        status = process_issue(state_root, issue)\n'''
    new_poll = '''        job_id = job["id"]\n        if (\n            bridge_worker._claim_path(state_root, job_id).exists()\n            and _gate12b_claim_blocks_retry(state_root, job)\n        ):\n            continue\n        status = process_issue(state_root, issue)\n'''
    if old_poll not in text:
        raise SystemExit("issue_poll_claim_fragment_missing")
    text = text.replace(old_poll, new_poll, 1)
    ISSUE_INBOX.write_text(text, encoding="utf-8")


def write_manifest() -> None:
    files = {}
    for path in (ISSUE_INBOX, BRIDGE_WORKER, COMMAND_PORT):
        files[path.name] = {
            "path": f".elan-vps-bridge/bootstrap/{path.name}",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    payload = {
        "files": files,
        "release_id": RELEASE_ID,
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
    print("MIG045_GATE12B_CANONICAL_PROOF_PATCH_MATERIALIZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
