#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
ISSUE = ROOT / "issue_inbox.py"
COMMAND = ROOT / "command_port.py"
MANIFEST = ROOT / "runtime-manifest.json"
RUNTIME_FILES = ("issue_inbox.py", "bridge_worker.py", "command_port.py")
RELEASE_ID = "bridge-mig045-v1351-rollout-fresh-read-20260904-v1"
INTENT = "MIG045_V1351_ROLLOUT_AND_FRESH_READ"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}_anchor_invalid:{count}")
    return text.replace(old, new)


def patch_issue_inbox() -> None:
    text = ISSUE.read_text(encoding="utf-8")
    if INTENT in text:
        raise SystemExit("mig045_v1351_intent_already_present")

    constants_anchor = 'SELF_UPDATE_INTENT = "BRIDGE_SELF_UPDATE"\n'
    constants = '''MIG045_V1351_INTENT = "MIG045_V1351_ROLLOUT_AND_FRESH_READ"\nMIG045_V1351_TARGET = "mig045-v1351-rollout-and-fresh-read"\nSELF_UPDATE_INTENT = "BRIDGE_SELF_UPDATE"\n'''
    text = replace_once(text, constants_anchor, constants, "issue_constants")

    parser_anchor = '''    if job["intent_code"] == SELF_UPDATE_INTENT:\n        if not _valid_self_update_context(job["context"]):\n            return None\n        return job\n'''
    parser = '''    if job["intent_code"] == MIG045_V1351_INTENT:\n        context = job["context"]\n        if not isinstance(context, dict) or set(context) != {"target", "artifact_url"}:\n            return None\n        if context.get("target") != MIG045_V1351_TARGET:\n            return None\n        try:\n            command_port.validate_mig045_v1351_artifact_url(context.get("artifact_url"))\n        except command_port.CommandPortError:\n            return None\n        return job\n    if job["intent_code"] == SELF_UPDATE_INTENT:\n        if not _valid_self_update_context(job["context"]):\n            return None\n        return job\n'''
    text = replace_once(text, parser_anchor, parser, "issue_parser")

    execute_anchor = '''    if job["intent_code"] == SELF_UPDATE_INTENT:\n        try:\n            state_root = pathlib.Path(\n'''
    execute = '''    if job["intent_code"] == MIG045_V1351_INTENT:\n        try:\n            payload = command_port.run_mig045_v1351_rollout_and_fresh_read_v1(\n                job["id"],\n                job["context"]["artifact_url"],\n            )\n            return _completed(job, started, {"status": "PASS", **payload})\n        except command_port.CommandPortError as exc:\n            return _failed(job, started, str(exc))\n    if job["intent_code"] == SELF_UPDATE_INTENT:\n        try:\n            state_root = pathlib.Path(\n'''
    text = replace_once(text, execute_anchor, execute, "issue_execute")
    ISSUE.write_text(text, encoding="utf-8")


def patch_command_port() -> None:
    text = COMMAND.read_text(encoding="utf-8")
    if "MIG045_TARGET_VERSION" in text:
        raise SystemExit("mig045_v1351_command_surface_already_present")

    text = replace_once(
        text,
        "import socket\nimport urllib.parse\n",
        "import socket\nimport time\nimport urllib.parse\n",
        "command_import_time",
    )

    constants_anchor = "_MAX_PACKAGE_BYTES = 180_000\n"
    constants = '''_MAX_PACKAGE_BYTES = 180_000\nMIG045_TARGET_VERSION = "1.3.51"\nMIG045_SOURCE_COMMIT = "275118ca38cd36cdbfc25c9cf9c72d1fca09b89f"\nMIG045_QUALIFIED_TRANSFER_SHA256 = "4825b62c4df34806c98d1379f1df325fbc3f571bceea20e5f05e17bccfd790e0"\nMIG045_QUALIFIED_TRANSFER_SIZE = 63986974\nMIG045_READ_TEMPLATE = "en033_m1_mig045_editorial_readback_v1"\nMIG045_EXPECTED_FIELDS = {\n    "plan_count",\n    "occurrence_count",\n    "publication_state_counts",\n    "observation_state_counts",\n}\nMIG045_PUBLICATION_STATES = {"PLANNED", "PROGRAMMED", "PUBLISHED"}\nMIG045_OBSERVATION_STATES = {\n    "NOT_OBSERVED",\n    "AMBIGUOUS",\n    "CONFIRMED_NOT_FOUND",\n    "CONFIRMED_PUBLISHED",\n}\nMIG045_READYZ_URL = "http://127.0.0.1:8787/readyz"\n'''
    text = replace_once(text, constants_anchor, constants, "command_constants")

    function_anchor = "def build_en2_g4_canary_payload_v1(request_id: str) -> dict:\n"
    functions = r'''def validate_mig045_v1351_artifact_url(value: object) -> str:
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
    if not isinstance(rollout_plan, dict) or rollout_plan.get("risk") != "reversible":
        raise CommandPortError("mig045_rollout_plan_not_reversible")
    rollout_executed = request_fn({
        "operation": "start_run",
        "plan_id": rollout_plan.get("plan_id"),
        "execution_token": rollout_plan.get("execution_token"),
        "procedure_sha256": rollout_plan.get("procedure_sha256"),
        "execution_class": "reversible",
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


''' + function_anchor
    text = replace_once(text, function_anchor, functions, "command_functions")
    COMMAND.write_text(text, encoding="utf-8")


def write_manifest() -> str:
    files = {}
    for name in RUNTIME_FILES:
        path = ROOT / name
        files[name] = {
            "path": f".elan-vps-bridge/bootstrap/{name}",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    value = {"files": files, "release_id": RELEASE_ID, "schema_version": "1.0"}
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    MANIFEST.write_text(raw, encoding="utf-8")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main() -> int:
    patch_issue_inbox()
    patch_command_port()
    digest = write_manifest()
    print(json.dumps({"status": "PATCHED", "release_id": RELEASE_ID, "manifest_sha256": digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
