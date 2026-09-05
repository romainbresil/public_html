#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
ISSUE_INBOX = ROOT / "issue_inbox.py"
COMMAND_PORT = ROOT / "command_port.py"
BRIDGE_WORKER = ROOT / "bridge_worker.py"
LEGACY_B_TEST = ROOT / "test_mig045_gate12b_committed_proof.py"
MANIFEST = ROOT / "runtime-manifest.json"
RELEASE_ID = "bridge-mig045-gate12b-a-b-final-binding-20260905-v3"

A_TECHNICAL_HEAD = "b8a5672d090fb0ddceb552e5029cf04b736da44d"
A_RUNTIME_VERSION = "1.3.52"
A_CAPABILITY_SHA256 = "b51a4bf09041f42af28b737f868710d5377123eb0747ae4fd6e2fd290a006729"
A_COMMAND_TEMPLATE_SHA256 = "6fff7e691aaa4cbc7d3b789e8b111988bc08d2680e911e6298c4d16fcceb123a"
A_SQL_OWNER_SHA256 = "77c7c90c25f2eefe7827a1c0c469b5a1343ca0646aa9c29d485e3dc1edd2fa25"
CORPUS_SHA256 = "cd0f4bde395351cbdb99b9d6f342cc0718d2be5276ca06000e44162d00bebcef"


def replace_once(path: pathlib.Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected_one_fragment:{path.name}:{count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def insert_before_once(path: pathlib.Path, marker: str, payload: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(marker) != 1:
        raise SystemExit(f"expected_one_marker:{path.name}:{text.count(marker)}")
    path.write_text(text.replace(marker, payload + marker, 1), encoding="utf-8")


def patch_command_port() -> None:
    text = COMMAND_PORT.read_text(encoding="utf-8")
    if "MIG045_GATE12B_A_TECHNICAL_HEAD" in text:
        return

    constants_marker = 'MIG045_GATE12B_CORPUS = tuple(f"CON-{number:03d}" for number in range(20, 28))\n'
    constants = constants_marker + f'''MIG045_GATE12B_A_TECHNICAL_HEAD = "{A_TECHNICAL_HEAD}"\nMIG045_GATE12B_RUNTIME_VERSION = "{A_RUNTIME_VERSION}"\nMIG045_GATE12B_CAPABILITY_SHA256 = "{A_CAPABILITY_SHA256}"\nMIG045_GATE12B_COMMAND_TEMPLATE_SHA256 = "{A_COMMAND_TEMPLATE_SHA256}"\nMIG045_GATE12B_SQL_OWNER_SHA256 = "{A_SQL_OWNER_SHA256}"\nMIG045_GATE12B_RESOLVED_DATABASE = "postgres"\nMIG045_GATE12B_RESOLVED_ROLE = "en_gate12b_executor"\nMIG045_GATE12B_POSTGRES_PROFILE = "business"\nMIG045_GATE12B_SCHEMA = "elan_naturel"\nMIG045_GATE12B_CORPUS_IDENTIFIER = "CON-020..CON-027"\nMIG045_GATE12B_CORPUS_SHA256 = "{CORPUS_SHA256}"\n'''
    replace_once(COMMAND_PORT, constants_marker, constants)

    old_validator = '''    runtime_version = value.get("runtime_version")\n    if not isinstance(runtime_version, str) or _GATE12B_RUNTIME_VERSION_RE.fullmatch(runtime_version) is None:\n        raise CommandPortError("mig045_gate12b_runtime_version_invalid")\n    runtime_source_commit = value.get("runtime_source_commit")\n    if not isinstance(runtime_source_commit, str) or _GATE12B_COMMIT_RE.fullmatch(runtime_source_commit) is None:\n        raise CommandPortError("mig045_gate12b_runtime_source_commit_invalid")\n    for field in (\n        "capability_sha256",\n        "effective_policy_sha256",\n        "command_template_sha256",\n        "sql_owner_sha256",\n        "target_binding_sha256",\n    ):\n        _validate_gate12b_sha256(value.get(field), field)\n'''
    new_validator = '''    static_bindings = {\n        "runtime_version": MIG045_GATE12B_RUNTIME_VERSION,\n        "runtime_source_commit": MIG045_GATE12B_A_TECHNICAL_HEAD,\n        "capability_sha256": MIG045_GATE12B_CAPABILITY_SHA256,\n        "command_template_sha256": MIG045_GATE12B_COMMAND_TEMPLATE_SHA256,\n        "sql_owner_sha256": MIG045_GATE12B_SQL_OWNER_SHA256,\n    }\n    for field, expected in static_bindings.items():\n        if value.get(field) != expected:\n            raise CommandPortError(f"mig045_gate12b_static_binding_mismatch:{field}")\n    for field in ("effective_policy_sha256", "target_binding_sha256"):\n        _validate_gate12b_sha256(value.get(field), field)\n'''
    replace_once(COMMAND_PORT, old_validator, new_validator)

    freeze_block = r'''

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

'''
    insert_before_once(
        COMMAND_PORT,
        "\ndef mig045_gate12b_persisted_result_sha256(wrapper: object) -> str:\n",
        freeze_block,
    )

    old_preflight = '''    if preflight_fn is None:\n        raise CommandPortError("mig045_gate12b_preflight_owner_not_bound")\n    try:\n        observed_preflight = preflight_fn()\n    except CommandPortError:\n        raise\n    except Exception as exc:\n        raise CommandPortError("mig045_gate12b_preflight_failed") from exc\n    _validate_gate12b_preflight(contract, observed_preflight)\n'''
    new_preflight = '''    if preflight_fn is None:\n        frozen = request_mig045_gate12b_production_proof_freeze(request_fn=request_fn)\n        if (\n            frozen.get("proof_contract") != contract\n            or frozen.get("proof_contract_sha256") != expected_contract_sha\n            or frozen.get("proof_id") != proof_id\n        ):\n            raise CommandPortError("mig045_gate12b_production_freeze_mismatch")\n    else:\n        try:\n            observed_preflight = preflight_fn()\n        except CommandPortError:\n            raise\n        except Exception as exc:\n            raise CommandPortError("mig045_gate12b_preflight_failed") from exc\n        _validate_gate12b_preflight(contract, observed_preflight)\n'''
    replace_once(COMMAND_PORT, old_preflight, new_preflight)


def patch_issue_inbox() -> None:
    text = ISSUE_INBOX.read_text(encoding="utf-8")
    if "MIG045_GATE12B_PREFLIGHT_INTENT" in text:
        return

    old_constants = '''MIG045_GATE12B_INTENT = "MIG045_GATE12B_COMMITTED_PROOF_V1"\nMIG045_GATE12B_TARGET = command_port.MIG045_GATE12B_TARGET\nMIG045_GATE12B_EXPECTED_IDENTITY_SET_SHA256 = command_port.MIG045_GATE12B_EXPECTED_IDENTITY_SET_SHA256\n'''
    new_constants = '''MIG045_GATE12B_INTENT = "MIG045_GATE12B_COMMITTED_PROOF_V1"\nMIG045_GATE12B_TARGET = command_port.MIG045_GATE12B_TARGET\nMIG045_GATE12B_EXPECTED_IDENTITY_SET_SHA256 = command_port.MIG045_GATE12B_EXPECTED_IDENTITY_SET_SHA256\nMIG045_GATE12B_PREFLIGHT_INTENT = "MIG045_GATE12B_TECHNICAL_PREFLIGHT_FREEZE_V1"\nMIG045_GATE12B_PREFLIGHT_CONTEXT = {"target": "mig045-gate12b-technical-preflight-freeze"}\n'''
    replace_once(ISSUE_INBOX, old_constants, new_constants)

    parse_marker = '    if job["intent_code"] == MIG045_GATE12B_INTENT:\n'
    parse_block = '''    if job["intent_code"] == MIG045_GATE12B_PREFLIGHT_INTENT:\n        if job["context"] != MIG045_GATE12B_PREFLIGHT_CONTEXT:\n            return None\n        return job\n'''
    # The first Gate12B dispatch belongs to parse_issue_intent.
    text = ISSUE_INBOX.read_text(encoding="utf-8")
    first = text.find(parse_marker)
    if first < 0:
        raise SystemExit("issue_parse_gate12b_marker_missing")
    text = text[:first] + parse_block + text[first:]
    ISSUE_INBOX.write_text(text, encoding="utf-8")

    execute_marker = '    if job["intent_code"] == MIG045_GATE12B_INTENT:\n'
    text = ISSUE_INBOX.read_text(encoding="utf-8")
    execute_search_start = text.find("def _execute_job")
    execute_at = text.find(execute_marker, execute_search_start)
    if execute_at < 0:
        raise SystemExit("issue_execute_gate12b_marker_missing")
    execute_block = '''    if job["intent_code"] == MIG045_GATE12B_PREFLIGHT_INTENT:\n        try:\n            payload = command_port.request_mig045_gate12b_production_proof_freeze()\n            return _completed(job, started, {"status": "PASS", **payload})\n        except command_port.CommandPortError as exc:\n            return _failed(job, started, str(exc))\n'''
    text = text[:execute_at] + execute_block + text[execute_at:]
    ISSUE_INBOX.write_text(text, encoding="utf-8")


def patch_legacy_b_test_fixture() -> None:
    if not LEGACY_B_TEST.is_file():
        raise SystemExit("legacy_b_test_missing")
    text = LEGACY_B_TEST.read_text(encoding="utf-8")
    if A_TECHNICAL_HEAD in text and A_CAPABILITY_SHA256 in text:
        return
    old = '''RUNTIME_VERSION = "1.3.52"\nRUNTIME_SOURCE_COMMIT = "aa" * 20\nCAPABILITY_SHA256 = "bb" * 32\nEFFECTIVE_POLICY_SHA256 = "cc" * 32\nCOMMAND_TEMPLATE_SHA256 = "dd" * 32\nSQL_OWNER_SHA256 = "ee" * 32\nTARGET_BINDING_SHA256 = "ff" * 32\n'''
    new = f'''RUNTIME_VERSION = "{A_RUNTIME_VERSION}"\nRUNTIME_SOURCE_COMMIT = "{A_TECHNICAL_HEAD}"\nCAPABILITY_SHA256 = "{A_CAPABILITY_SHA256}"\nEFFECTIVE_POLICY_SHA256 = "cc" * 32\nCOMMAND_TEMPLATE_SHA256 = "{A_COMMAND_TEMPLATE_SHA256}"\nSQL_OWNER_SHA256 = "{A_SQL_OWNER_SHA256}"\nTARGET_BINDING_SHA256 = "ff" * 32\n'''
    replace_once(LEGACY_B_TEST, old, new)


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
    patch_legacy_b_test_fixture()
    write_manifest()
    print("MIG045_GATE12B_A_B_FINAL_BINDING_MATERIALIZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
