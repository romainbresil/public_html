#!/usr/bin/env python3
import hashlib
import json
import os
import pathlib
import re
import secrets
import shutil
import sys
import time
import urllib.parse
import urllib.request

import bridge_worker
import command_port

CONTROL_REPO = os.environ.get("ELAN_BRIDGE_CONTROL_REPO", "romainbresil/public_html")
CONTROL_REF = os.environ.get("ELAN_BRIDGE_CONTROL_REF", "elan-vps-bridge-control-v1")
ISSUE_AUTHOR = os.environ.get("ELAN_BRIDGE_ISSUE_AUTHOR", "romainbresil")
ISSUE_TITLE_PREFIX = "EN-INTENT — "
POLL_SECONDS = max(120, int(os.environ.get("ELAN_BRIDGE_POLL_SECONDS", "120")))
SPRINT_PRO_READ_INTENT = "EN_CORE_STATUS_READ"
SPRINT_PRO_SCHEMA_MIGRATION_EVIDENCE_CONTEXT = {
    "target": "en-core",
    "evidence_contract": command_port.SCHEMA_MIGRATION_EVIDENCE_CONTRACT,
    "requested_ids": list(command_port.SCHEMA_MIGRATION_EVIDENCE_IDS),
}
G4_COMMERCIAL_INTENT = "EN2_G4_COMMERCIAL_CANARY_WRITE"
G4_COMMERCIAL_CONTEXT = {"target": "en2-g4-commercial-canary"}
G5_KNOWLEDGE_INTENT = "EN2_G5_KNOWLEDGE_CAPTURE_APPLY"
G5_KNOWLEDGE_CONTEXT = {"target": "en2-g5-knowledge-capture"}
G6_SCHEMA_READ_INTENT = "EN2_G6_DECISION_SCHEMA_READ"
G6_SCHEMA_READ_CONTEXT = {"target": "en2-g6-decision-schema"}
P1_MIGRATION_REGISTRY_INTENT = "EN2_P1_MIGRATION_REGISTRY_READ"
P1_MIGRATION_REGISTRY_CONTEXT = {"target": "en2-p1-migration-registry"}
G6_DECISION_ABSORPTION_INTENT = "EN2_G6_DECISION_ABSORPTION_CANARY"
G6_DECISION_ABSORPTION_CONTEXT = {
    "target": "en2-g6-decision-absorption",
    "synthetic": True,
    "idempotency_key": "en2-g6-decision-resolved-20260903-v1",
}
SELF_UPDATE_INTENT = "BRIDGE_SELF_UPDATE"
SELF_UPDATE_MANIFEST_PATH = ".elan-vps-bridge/bootstrap/runtime-manifest.json"
SELF_UPDATE_RUNTIME_FILES = ("issue_inbox.py", "bridge_worker.py", "command_port.py")
SELF_UPDATE_BASE_PATH = ".elan-vps-bridge/bootstrap"
SELF_UPDATE_MAX_BYTES = 1_048_576
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_RELEASE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def _issues_url() -> str:
    return (
        f"https://api.github.com/repos/{CONTROL_REPO}/issues"
        "?state=open&sort=created&direction=asc&per_page=30&labels=elan-cms-chatgpt"
    )


def _control_raw_url(relative_path: str) -> str:
    quoted = "/".join(urllib.parse.quote(part, safe="") for part in relative_path.split("/"))
    return f"https://raw.githubusercontent.com/{CONTROL_REPO}/{CONTROL_REF}/{quoted}"


def _urlopen_bytes(url: str, timeout: int = 15) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "elan-web-vps-bridge-issues/1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        value = response.read(SELF_UPDATE_MAX_BYTES + 1)
    if len(value) > SELF_UPDATE_MAX_BYTES:
        raise ValueError("response_too_large")
    return value


def _fetch_control_path(relative_path: str) -> bytes:
    return _urlopen_bytes(_control_raw_url(relative_path), timeout=15)


def _issue_job_id(issue_number: int) -> str:
    return f"gh-issue-{issue_number}"


def _valid_self_update_context(context: object) -> bool:
    if not isinstance(context, dict) or set(context) != {"target", "manifest_sha256"}:
        return False
    return (
        context.get("target") == "elan-bridge"
        and isinstance(context.get("manifest_sha256"), str)
        and _SHA256_RE.fullmatch(context["manifest_sha256"]) is not None
    )


def parse_issue_intent(issue: dict) -> dict | None:
    if not isinstance(issue, dict) or "pull_request" in issue:
        return None
    user = issue.get("user")
    if not isinstance(user, dict) or user.get("login") != ISSUE_AUTHOR:
        return None
    title = issue.get("title")
    number = issue.get("number")
    body = issue.get("body")
    if (
        not isinstance(title, str)
        or not title.startswith(ISSUE_TITLE_PREFIX)
        or not isinstance(number, int)
        or number < 1
        or not isinstance(body, str)
    ):
        return None
    try:
        intent = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(intent, dict) or set(intent) != {"intent_code", "context"}:
        return None
    job = {
        "id": _issue_job_id(number),
        "intent_code": intent["intent_code"],
        "context": intent["context"],
        "read_token": secrets.token_urlsafe(32),
    }
    if job["intent_code"] == SPRINT_PRO_READ_INTENT:
        if job["context"] == {"target": "en-core"}:
            return job
        if job["context"] == SPRINT_PRO_SCHEMA_MIGRATION_EVIDENCE_CONTEXT:
            return job
        return None
    if job["intent_code"] == G4_COMMERCIAL_INTENT:
        if job["context"] != G4_COMMERCIAL_CONTEXT:
            return None
        return job
    if job["intent_code"] == G5_KNOWLEDGE_INTENT:
        if job["context"] != G5_KNOWLEDGE_CONTEXT:
            return None
        return job
    if job["intent_code"] == G6_SCHEMA_READ_INTENT:
        if job["context"] != G6_SCHEMA_READ_CONTEXT:
            return None
        return job
    if job["intent_code"] == P1_MIGRATION_REGISTRY_INTENT:
        if job["context"] != P1_MIGRATION_REGISTRY_CONTEXT:
            return None
        return job
    if job["intent_code"] == G6_DECISION_ABSORPTION_INTENT:
        if job["context"] != G6_DECISION_ABSORPTION_CONTEXT:
            return None
        return job
    if job["intent_code"] == SELF_UPDATE_INTENT:
        if not _valid_self_update_context(job["context"]):
            return None
        return job
    try:
        return bridge_worker.validate_job(job)
    except ValueError:
        return None


def _completed(job: dict, started: str, result: dict) -> dict:
    return {
        "id": job["id"],
        "read_token": job["read_token"],
        "intent_code": job["intent_code"],
        "context": job["context"],
        "state": "COMPLETED",
        "result": result,
        "started_at": started,
        "finished_at": bridge_worker.now_iso(),
    }


def _failed(job: dict, started: str, error: str) -> dict:
    return {
        "id": job["id"],
        "read_token": job["read_token"],
        "intent_code": job["intent_code"],
        "context": job["context"],
        "state": "FAILED",
        "result": {"status": "UNAVAILABLE", "stderr": error},
        "started_at": started,
        "finished_at": bridge_worker.now_iso(),
    }


def _validate_self_update_manifest(payload: object) -> dict:
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "release_id", "files"}:
        raise ValueError("invalid_self_update_manifest")
    if payload.get("schema_version") != "1.0":
        raise ValueError("invalid_self_update_schema_version")
    release_id = payload.get("release_id")
    if not isinstance(release_id, str) or _RELEASE_RE.fullmatch(release_id) is None:
        raise ValueError("invalid_self_update_release_id")
    files = payload.get("files")
    if not isinstance(files, dict) or set(files) != set(SELF_UPDATE_RUNTIME_FILES):
        raise ValueError("invalid_self_update_file_set")
    normalized = {}
    for name in SELF_UPDATE_RUNTIME_FILES:
        entry = files.get(name)
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise ValueError("invalid_self_update_file_entry")
        expected_path = f"{SELF_UPDATE_BASE_PATH}/{name}"
        if entry.get("path") != expected_path:
            raise ValueError("invalid_self_update_file_path")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise ValueError("invalid_self_update_file_sha256")
        normalized[name] = {"path": expected_path, "sha256": digest}
    return {"schema_version": "1.0", "release_id": release_id, "files": normalized}


def _atomic_write(path: pathlib.Path, payload: bytes, mode: int) -> None:
    temporary = path.with_name(path.name + ".tmp-en-bridge-update")
    temporary.write_bytes(payload)
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def apply_self_update(
    state_root: pathlib.Path,
    app_root: pathlib.Path,
    expected_manifest_sha256: str,
    *,
    fetch_fn=_fetch_control_path,
) -> dict:
    if _SHA256_RE.fullmatch(expected_manifest_sha256) is None:
        raise ValueError("invalid_manifest_sha256")
    manifest_raw = fetch_fn(SELF_UPDATE_MANIFEST_PATH)
    if hashlib.sha256(manifest_raw).hexdigest() != expected_manifest_sha256:
        raise ValueError("self_update_manifest_sha256_mismatch")
    try:
        manifest = _validate_self_update_manifest(json.loads(manifest_raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_self_update_manifest") from exc

    candidates: dict[str, bytes] = {}
    for name in SELF_UPDATE_RUNTIME_FILES:
        entry = manifest["files"][name]
        payload = fetch_fn(entry["path"])
        if len(payload) > SELF_UPDATE_MAX_BYTES:
            raise ValueError("self_update_file_too_large")
        if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise ValueError("self_update_file_sha256_mismatch")
        text = payload.decode("utf-8")
        compile(text, name, "exec")
        candidates[name] = payload

    app_root = pathlib.Path(app_root)
    state_root = pathlib.Path(state_root)
    current_hashes = {}
    for name in SELF_UPDATE_RUNTIME_FILES:
        target = app_root / name
        if not target.is_file():
            raise ValueError("self_update_runtime_file_missing")
        current_hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    if all(current_hashes[name] == manifest["files"][name]["sha256"] for name in SELF_UPDATE_RUNTIME_FILES):
        return {
            "status": "ALREADY_CURRENT",
            "release_id": manifest["release_id"],
            "manifest_sha256": expected_manifest_sha256,
            "updated_files": [],
            "restart_after_post": False,
            "external_action_allowed": False,
        }

    update_root = state_root / "runtime-updates" / manifest["release_id"]
    backup_root = update_root / "previous"
    backup_root.mkdir(parents=True, exist_ok=True)
    for name in SELF_UPDATE_RUNTIME_FILES:
        shutil.copy2(app_root / name, backup_root / name)

    replaced = []
    try:
        for name in SELF_UPDATE_RUNTIME_FILES:
            target = app_root / name
            mode = target.stat().st_mode & 0o777
            _atomic_write(target, candidates[name], mode)
            replaced.append(name)
    except Exception:
        for name in replaced:
            backup = backup_root / name
            target = app_root / name
            _atomic_write(target, backup.read_bytes(), backup.stat().st_mode & 0o777)
        raise

    for name in SELF_UPDATE_RUNTIME_FILES:
        observed = hashlib.sha256((app_root / name).read_bytes()).hexdigest()
        if observed != manifest["files"][name]["sha256"]:
            for rollback_name in SELF_UPDATE_RUNTIME_FILES:
                backup = backup_root / rollback_name
                target = app_root / rollback_name
                _atomic_write(target, backup.read_bytes(), backup.stat().st_mode & 0o777)
            raise ValueError("self_update_post_write_readback_mismatch")

    receipt = {
        "schema_version": "1.0",
        "release_id": manifest["release_id"],
        "manifest_sha256": expected_manifest_sha256,
        "files": {name: manifest["files"][name]["sha256"] for name in SELF_UPDATE_RUNTIME_FILES},
        "applied_at": bridge_worker.now_iso(),
    }
    receipt_path = update_root / "applied-receipt.json"
    receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(receipt_path, 0o600)
    return {
        "status": "APPLIED",
        "release_id": manifest["release_id"],
        "manifest_sha256": expected_manifest_sha256,
        "updated_files": list(SELF_UPDATE_RUNTIME_FILES),
        "restart_after_post": True,
        "external_action_allowed": False,
    }


def exec_updated_runtime(app_root: pathlib.Path | None = None) -> None:
    root = pathlib.Path(
        app_root
        if app_root is not None
        else os.environ.get("ELAN_BRIDGE_APP_ROOT", "/opt/elan-web-vps-bridge")
    )
    target = root / "issue_inbox.py"
    os.execv(sys.executable, [sys.executable, str(target)])


def _execute_job(job: dict) -> dict:
    started = bridge_worker.now_iso()
    if job["intent_code"] == SPRINT_PRO_READ_INTENT:
        try:
            if job["context"] == SPRINT_PRO_SCHEMA_MIGRATION_EVIDENCE_CONTEXT:
                payload = command_port.read_en_core_status_v1(
                    job["id"],
                    evidence_contract=job["context"]["evidence_contract"],
                    requested_ids=job["context"]["requested_ids"],
                )
            else:
                payload = command_port.read_en_core_status_v1(job["id"])
            return _completed(job, started, {"status": "HEALTHY", **payload})
        except command_port.CommandPortError as exc:
            return _failed(job, started, str(exc))
    if job["intent_code"] == G4_COMMERCIAL_INTENT:
        try:
            payload = command_port.run_en2_g4_commercial_canary_v1(job["id"])
            return _completed(job, started, {"status": "PASS", **payload})
        except command_port.CommandPortError as exc:
            return _failed(job, started, str(exc))
    if job["intent_code"] == G5_KNOWLEDGE_INTENT:
        try:
            payload = command_port.run_en2_g5_knowledge_capture_v1(job["id"])
            return _completed(job, started, {"status": "PASS", **payload})
        except command_port.CommandPortError as exc:
            return _failed(job, started, str(exc))
    if job["intent_code"] == G6_SCHEMA_READ_INTENT:
        try:
            payload = command_port.read_en2_g6_decision_schema_v1(job["id"])
            return _completed(job, started, {"status": "PASS", **payload})
        except command_port.CommandPortError as exc:
            return _failed(job, started, str(exc))
    if job["intent_code"] == G6_DECISION_ABSORPTION_INTENT:
        try:
            payload = command_port.execute_en2_g6_decision_absorption_canary_v1(job["id"])
            return _completed(job, started, {"status": "PASS", **payload})
        except command_port.CommandPortError as exc:
            return _failed(job, started, str(exc))
    if job["intent_code"] == P1_MIGRATION_REGISTRY_INTENT:
        try:
            payload = command_port.read_en2_p1_migration_registry_v1(job["id"])
            return _completed(job, started, {"status": "PASS", **payload})
        except command_port.CommandPortError as exc:
            return _failed(job, started, str(exc))
    if job["intent_code"] == SELF_UPDATE_INTENT:
        try:
            state_root = pathlib.Path(
                os.environ.get("ELAN_BRIDGE_STATE_ROOT", "/var/lib/elan-web-vps-bridge")
            )
            app_root = pathlib.Path(
                os.environ.get("ELAN_BRIDGE_APP_ROOT", "/opt/elan-web-vps-bridge")
            )
            payload = apply_self_update(
                state_root,
                app_root,
                job["context"]["manifest_sha256"],
            )
            return _completed(job, started, payload)
        except (OSError, UnicodeDecodeError, ValueError, SyntaxError) as exc:
            return _failed(job, started, str(exc))
    return bridge_worker.execute_intent(job)


def process_issue(state_root: pathlib.Path, issue: dict) -> str:
    job = parse_issue_intent(issue)
    if job is None:
        return "IGNORED"
    source = json.dumps(
        {
            "number": issue["number"],
            "title": issue["title"],
            "body": issue["body"],
            "author": issue["user"]["login"],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    source_sha = hashlib.sha256(source).hexdigest()
    try:
        bridge_worker.create_claim(state_root, job["id"], source_sha)
    except bridge_worker.AlreadyClaimed:
        return "ALREADY_CLAIMED"
    result = _execute_job(job)
    result["source_sha"] = source_sha
    result["source_issue_number"] = issue["number"]
    result["source_issue_url"] = issue.get("html_url", "")
    bridge_worker.store_result(state_root, result)
    bridge_worker.post_result(result)
    if result.get("state") == "COMPLETED" and result.get("result", {}).get("restart_after_post") is True:
        exec_updated_runtime()
    return result["state"]


def poll_issue_once(state_root: pathlib.Path) -> list[tuple[str, str]]:
    raw = _urlopen_bytes(_issues_url(), timeout=15)
    issues = json.loads(raw.decode("utf-8"))
    if not isinstance(issues, list):
        raise ValueError("invalid_issues_response")
    for issue in issues:
        job = parse_issue_intent(issue)
        if job is None:
            continue
        job_id = job["id"]
        if bridge_worker._claim_path(state_root, job_id).exists():
            continue
        status = process_issue(state_root, issue)
        return [(job_id, status)]
    return []


def main() -> int:
    state_root = pathlib.Path(
        os.environ.get("ELAN_BRIDGE_STATE_ROOT", "/var/lib/elan-web-vps-bridge")
    )
    host = os.environ.get("ELAN_BRIDGE_RESULT_HOST", "127.0.0.1")
    port = int(os.environ.get("ELAN_BRIDGE_RESULT_PORT", "8789"))
    state_root.mkdir(parents=True, exist_ok=True)
    server = bridge_worker.serve_results(state_root, host, port)
    try:
        while True:
            try:
                outcomes = poll_issue_once(state_root)
                for job_id, status in outcomes:
                    print(
                        json.dumps({"event": "issue_job", "id": job_id, "status": status}),
                        flush=True,
                    )
            except Exception as exc:
                print(
                    json.dumps(
                        {"event": "issue_poll_error", "error": type(exc).__name__}
                    ),
                    flush=True,
                )
            time.sleep(POLL_SECONDS)
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
