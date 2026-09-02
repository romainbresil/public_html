#!/usr/bin/env python3
import hashlib
import json
import os
import pathlib
import secrets
import time
import urllib.request

import bridge_worker

CONTROL_REPO = os.environ.get("ELAN_BRIDGE_CONTROL_REPO", "romainbresil/public_html")
ISSUE_AUTHOR = os.environ.get("ELAN_BRIDGE_ISSUE_AUTHOR", "romainbresil")
ISSUE_TITLE_PREFIX = "EN-INTENT — "
POLL_SECONDS = max(60, int(os.environ.get("ELAN_BRIDGE_POLL_SECONDS", "60")))


def _issues_url() -> str:
    return (
        f"https://api.github.com/repos/{CONTROL_REPO}/issues"
        "?state=open&sort=created&direction=asc&per_page=30"
    )


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
        return response.read()


def _issue_job_id(issue_number: int) -> str:
    return f"gh-issue-{issue_number}"


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
    try:
        return bridge_worker.validate_job(job)
    except ValueError:
        return None


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
    result = bridge_worker.execute_intent(job)
    result["source_sha"] = source_sha
    result["source_issue_number"] = issue["number"]
    result["source_issue_url"] = issue.get("html_url", "")
    bridge_worker.store_result(state_root, result)
    bridge_worker.post_result(result)
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
