from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMAND_PORT = ROOT / "command_port.py"
ISSUE_INBOX = ROOT / "issue_inbox.py"
BRIDGE_WORKER = ROOT / "bridge_worker.py"
MANIFEST = ROOT / "runtime-manifest.json"
EXPECTED = {
    "issue_inbox.py": "0c20b527f8fb0333becbf7f81df4b564861629c956bf45c8b93443bac3740769",
    "bridge_worker.py": "7d7f7839cf0c5931bf8af29c78adef59a4e1a0bab10dfb064150942975635cd4",
    "command_port.py": "8ffa9d596b008ddda56e827860fbbcec3e2cb07f546eac58f05116418dcce4a7",
}
RELEASE_ID = "en2-g6-schema-read-v2-cc0bd6ab"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch() -> None:
    source = COMMAND_PORT.read_text(encoding="utf-8")
    if 'G6_SCHEMA_COLUMNS_TEMPLATE = "en029_m6_schema_columns_chunks_v2"' in source:
        return
    if "import base64\n" not in source:
        source = source.replace("#!/usr/bin/env python3\n", "#!/usr/bin/env python3\nimport base64\nimport binascii\n", 1)
    source = source.replace(
        'G6_SCHEMA_COLUMNS_TEMPLATE = "en029_m6_schema_columns_v1"',
        'G6_SCHEMA_COLUMNS_TEMPLATE = "en029_m6_schema_columns_chunks_v2"', 1
    ).replace(
        'G6_SCHEMA_FUNCTIONS_TEMPLATE = "en029_m6_schema_functions_v1"',
        'G6_SCHEMA_FUNCTIONS_TEMPLATE = "en029_m6_schema_functions_chunks_v2"', 1
    )
    start = source.index("def _parse_g6_values(")
    end = source.index("def read_en2_g6_decision_schema_v1(", start)
    reconstruct = '''def _reconstruct_g6_capture(result: dict, expected_template: str, expected_capture: str) -> list[dict]:
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


'''
    source = source[:start] + reconstruct + source[end:]
    old = '''    columns_all = _parse_g6_values(
        by_id["schema-columns"].get("result"),
        G6_SCHEMA_COLUMNS_TEMPLATE,
    )
    functions_all = _parse_g6_values(
        by_id["schema-functions"].get("result"),
        G6_SCHEMA_FUNCTIONS_TEMPLATE,
    )
'''
    new = '''    columns_all = _reconstruct_g6_capture(
        by_id["schema-columns"].get("result"),
        G6_SCHEMA_COLUMNS_TEMPLATE,
        "columns",
    )
    functions_all = _reconstruct_g6_capture(
        by_id["schema-functions"].get("result"),
        G6_SCHEMA_FUNCTIONS_TEMPLATE,
        "functions",
    )
'''
    if old not in source:
        raise RuntimeError("g6_parse_call_marker_missing")
    COMMAND_PORT.write_text(source.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    patch()
    actual = {name: sha(ROOT / name) for name in ("issue_inbox.py", "bridge_worker.py", "command_port.py")}
    if actual != EXPECTED:
        raise RuntimeError(f"runtime_hash_mismatch:{actual}")
    manifest = {
        "files": {name: {"path": f".elan-vps-bridge/bootstrap/{name}", "sha256": digest} for name, digest in actual.items()},
        "release_id": RELEASE_ID,
        "schema_version": "1.0",
    }
    MANIFEST.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"status":"PASS","release_id":RELEASE_ID,"files":actual}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
