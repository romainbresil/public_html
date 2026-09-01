#!/usr/bin/env python3
import base64
import hashlib
import hmac
import json
import os
import pathlib
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
MAX_TIMEOUT = 120
DEFAULT_OUTPUT_LIMIT = 65536


class AlreadyClaimed(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_job(job: dict) -> dict:
    if not isinstance(job, dict):
        raise ValueError("job_not_object")
    job_id = job.get("id")
    command = job.get("command")
    timeout = job.get("timeout_seconds", 60)
    read_token = job.get("read_token")
    cwd = job.get("cwd")
    if not isinstance(job_id, str) or not _ID_RE.fullmatch(job_id):
        raise ValueError("invalid_id")
    if not isinstance(command, str) or not command.strip() or len(command) > 20000:
        raise ValueError("invalid_command")
    if not isinstance(timeout, int) or timeout < 1 or timeout > MAX_TIMEOUT:
        raise ValueError("invalid_timeout")
    if not isinstance(read_token, str) or len(read_token) < 32 or len(read_token) > 256:
        raise ValueError("invalid_read_token")
    if cwd is not None and (not isinstance(cwd, str) or not cwd.startswith("/")):
        raise ValueError("invalid_cwd")
    return {
        "id": job_id,
        "command": command,
        "timeout_seconds": timeout,
        "read_token": read_token,
        "cwd": cwd,
    }


def _bounded_text(data: bytes, limit: int) -> tuple[str, bool]:
    truncated = len(data) > limit
    return data[:limit].decode("utf-8", errors="replace"), truncated


def execute_job(job: dict, output_limit: int = DEFAULT_OUTPUT_LIMIT) -> dict:
    job = validate_job(job)
    started = now_iso()
    try:
        proc = subprocess.run(
            ["/bin/bash", "-lc", job["command"]],
            cwd=job["cwd"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=job["timeout_seconds"],
            check=False,
            env=os.environ.copy(),
        )
        stdout, stdout_truncated = _bounded_text(proc.stdout, output_limit)
        stderr, stderr_truncated = _bounded_text(proc.stderr, output_limit)
        return {
            "id": job["id"],
            "read_token": job["read_token"],
            "state": "COMPLETED",
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "started_at": started,
            "finished_at": now_iso(),
        }
    except subprocess.TimeoutExpired as exc:
        stdout, stdout_truncated = _bounded_text(exc.stdout or b"", output_limit)
        stderr, stderr_truncated = _bounded_text(exc.stderr or b"", output_limit)
        return {
            "id": job["id"],
            "read_token": job["read_token"],
            "state": "TIMEOUT",
            "exit_code": None,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "started_at": started,
            "finished_at": now_iso(),
        }


def _claim_path(state_root: pathlib.Path, job_id: str) -> pathlib.Path:
    return state_root / "claims" / f"{job_id}.json"


def create_claim(state_root: pathlib.Path, job_id: str, source_sha: str) -> pathlib.Path:
    claims = state_root / "claims"
    claims.mkdir(parents=True, exist_ok=True)
    path = _claim_path(state_root, job_id)
    payload = json.dumps({"id": job_id, "source_sha": source_sha, "claimed_at": now_iso()}, sort_keys=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise AlreadyClaimed(job_id) from exc
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(payload + "\n")
        f.flush()
        os.fsync(f.fileno())
    return path


def store_result(state_root: pathlib.Path, result: dict) -> pathlib.Path:
    results = state_root / "results"
    results.mkdir(parents=True, exist_ok=True)
    path = results / f"{result['id']}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return path


def load_result_for_token(state_root: pathlib.Path, job_id: str, supplied_token: str):
    if not _ID_RE.fullmatch(job_id):
        return None
    path = state_root / "results" / f"{job_id}.json"
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    expected = value.get("read_token", "")
    if not isinstance(expected, str) or not hmac.compare_digest(expected, supplied_token):
        return None
    return value


def decrypt_envelope(envelope_path: pathlib.Path, cert_path: pathlib.Path, key_path: pathlib.Path) -> dict:
    raw = base64.b64decode(envelope_path.read_bytes(), validate=True)
    with tempfile.NamedTemporaryFile(prefix="elan-bridge-", suffix=".der") as der:
        der.write(raw)
        der.flush()
        proc = subprocess.run(
            [
                "openssl", "cms", "-decrypt", "-binary", "-inform", "DER",
                "-in", der.name, "-recip", str(cert_path), "-inkey", str(key_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    if proc.returncode != 0:
        raise ValueError("decrypt_failed")
    return validate_job(json.loads(proc.stdout.decode("utf-8")))


def process_envelope(state_root: pathlib.Path, envelope_path: pathlib.Path, source_sha: str, cert_path: pathlib.Path, key_path: pathlib.Path) -> str:
    job = decrypt_envelope(envelope_path, cert_path, key_path)
    try:
        create_claim(state_root, job["id"], source_sha)
    except AlreadyClaimed:
        return "ALREADY_CLAIMED"
    result = execute_job(job)
    result["source_sha"] = source_sha
    store_result(state_root, result)
    return result["state"]


def resolve_result_request(state_root: pathlib.Path, raw_path: str) -> tuple[int, str]:
    parsed = urllib.parse.urlparse(raw_path)
    if not parsed.path.startswith("/results/"):
        return 404, '{"error":"not_found"}'
    job_id = parsed.path[len("/results/"):]
    token = urllib.parse.parse_qs(parsed.query).get("token", [""])[0]
    value = load_result_for_token(state_root, job_id, token)
    if value is None:
        return 404, '{"error":"not_found"}'
    public = {k: v for k, v in value.items() if k != "read_token"}
    return 200, json.dumps(public, ensure_ascii=False, sort_keys=True)


CONTROL_REPO = os.environ.get("ELAN_BRIDGE_CONTROL_REPO", "romainbresil/public_html")
CONTROL_REF = os.environ.get("ELAN_BRIDGE_CONTROL_REF", "elan-vps-bridge-control-v1")
CONTROL_BASE_PATH = os.environ.get("ELAN_BRIDGE_CONTROL_BASE_PATH", ".elan-vps-bridge")
POLL_SECONDS = max(2, int(os.environ.get("ELAN_BRIDGE_POLL_SECONDS", "3")))


def _raw_url(relative_path: str) -> str:
    quoted = "/".join(urllib.parse.quote(part, safe="") for part in relative_path.split("/"))
    return f"https://raw.githubusercontent.com/{CONTROL_REPO}/{CONTROL_REF}/{quoted}"


def _urlopen_bytes(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "elan-web-vps-bridge/1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def parse_latest_pointer(raw: bytes) -> str | None:
    value = raw.decode("utf-8", errors="strict").strip()
    if not value:
        return None
    if "/" in value or "\\" in value or not value.endswith(".cms.b64"):
        raise ValueError("invalid_latest_pointer")
    job_id = value[:-8]
    if not _ID_RE.fullmatch(job_id):
        raise ValueError("invalid_latest_pointer")
    return value


def poll_once(state_root: pathlib.Path, cert_path: pathlib.Path, key_path: pathlib.Path) -> list[tuple[str, str]]:
    latest_url = _raw_url(f"{CONTROL_BASE_PATH}/latest.txt")
    name = parse_latest_pointer(_urlopen_bytes(latest_url))
    if name is None:
        return []
    job_id = name[:-8]
    if _claim_path(state_root, job_id).exists():
        return []
    incoming = state_root / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    raw = _urlopen_bytes(_raw_url(f"{CONTROL_BASE_PATH}/jobs/{name}"))
    source_sha = hashlib.sha256(raw).hexdigest()
    path = incoming / name
    path.write_bytes(raw)
    os.chmod(path, 0o600)
    try:
        status = process_envelope(state_root, path, source_sha, cert_path, key_path)
    except Exception as exc:
        status = f"ERROR:{type(exc).__name__}"
    return [(job_id, status)]


class ResultHandler(BaseHTTPRequestHandler):
    state_root = pathlib.Path("/var/lib/elan-web-vps-bridge")

    def do_GET(self):
        if self.path == "/healthz":
            payload = b'{"status":"ok"}'
            self.send_response(200)
        else:
            status, text = resolve_result_request(self.state_root, self.path)
            payload = text.encode("utf-8")
            self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


def serve_results(state_root: pathlib.Path, host: str, port: int) -> ThreadingHTTPServer:
    handler = type("ConfiguredResultHandler", (ResultHandler,), {"state_root": state_root})
    server = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, name="result-http", daemon=True)
    thread.start()
    return server


def main() -> int:
    state_root = pathlib.Path(os.environ.get("ELAN_BRIDGE_STATE_ROOT", "/var/lib/elan-web-vps-bridge"))
    cert_path = pathlib.Path(os.environ.get("ELAN_BRIDGE_CERT", str(state_root / "public.crt")))
    key_path = pathlib.Path(os.environ.get("ELAN_BRIDGE_KEY", str(state_root / "private.key")))
    host = os.environ.get("ELAN_BRIDGE_RESULT_HOST", "127.0.0.1")
    port = int(os.environ.get("ELAN_BRIDGE_RESULT_PORT", "8789"))
    state_root.mkdir(parents=True, exist_ok=True)
    server = serve_results(state_root, host, port)
    try:
        while True:
            try:
                outcomes = poll_once(state_root, cert_path, key_path)
                for job_id, status in outcomes:
                    print(json.dumps({"event": "job", "id": job_id, "status": status}), flush=True)
            except Exception as exc:
                print(json.dumps({"event": "poll_error", "error": type(exc).__name__}), flush=True)
            time.sleep(POLL_SECONDS)
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
