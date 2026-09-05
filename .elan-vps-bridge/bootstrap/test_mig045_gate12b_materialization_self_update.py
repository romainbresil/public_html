#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import tempfile
import unittest

BOOTSTRAP = pathlib.Path(__file__).resolve().parent
if str(BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(BOOTSTRAP))

import issue_inbox  # noqa: E402

RELEASE_ID = "bridge-mig045-gate12b-production-materialization-route-20260905-v1"
RUNTIME_FILES = ("issue_inbox.py", "bridge_worker.py", "command_port.py")


class Gate12BMaterializationSelfUpdateTests(unittest.TestCase):
    def test_runtime_manifest_is_owner_backed_and_matches_exact_runtime_bytes(self):
        manifest_path = BOOTSTRAP / "runtime-manifest.json"
        manifest_raw = manifest_path.read_bytes()
        manifest = json.loads(manifest_raw.decode("utf-8"))
        self.assertEqual(manifest["schema_version"], "1.0")
        self.assertEqual(manifest["release_id"], RELEASE_ID)
        self.assertEqual(set(manifest["files"]), set(RUNTIME_FILES))
        self.assertEqual(tuple(issue_inbox.SELF_UPDATE_RUNTIME_FILES), RUNTIME_FILES)
        for name in RUNTIME_FILES:
            entry = manifest["files"][name]
            self.assertEqual(entry["path"], f".elan-vps-bridge/bootstrap/{name}")
            self.assertEqual(
                entry["sha256"],
                hashlib.sha256((BOOTSTRAP / name).read_bytes()).hexdigest(),
                name,
            )
        self.assertEqual(
            manifest["files"]["bridge_worker.py"]["sha256"],
            "7d7f7839cf0c5931bf8af29c78adef59a4e1a0bab10dfb064150942975635cd4",
        )

    def test_bridge_self_update_applies_exact_manifest_then_is_idempotent(self):
        manifest_path = BOOTSTRAP / "runtime-manifest.json"
        manifest_raw = manifest_path.read_bytes()
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        payloads = {
            issue_inbox.SELF_UPDATE_MANIFEST_PATH: manifest_raw,
            **{
                f".elan-vps-bridge/bootstrap/{name}": (BOOTSTRAP / name).read_bytes()
                for name in RUNTIME_FILES
            },
        }

        def fetch_fn(path: str) -> bytes:
            return payloads[path]

        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            app_root = root / "app"
            state_root = root / "state"
            app_root.mkdir()
            for name in RUNTIME_FILES:
                (app_root / name).write_text("# previous runtime\n", encoding="utf-8")

            first = issue_inbox.apply_self_update(
                state_root,
                app_root,
                manifest_sha,
                fetch_fn=fetch_fn,
            )
            self.assertEqual(first["status"], "APPLIED")
            self.assertEqual(first["release_id"], RELEASE_ID)
            self.assertEqual(set(first["updated_files"]), set(RUNTIME_FILES))
            self.assertTrue(first["restart_after_post"])
            for name in RUNTIME_FILES:
                self.assertEqual(
                    hashlib.sha256((app_root / name).read_bytes()).hexdigest(),
                    json.loads(manifest_raw)["files"][name]["sha256"],
                )

            second = issue_inbox.apply_self_update(
                state_root,
                app_root,
                manifest_sha,
                fetch_fn=fetch_fn,
            )
            self.assertEqual(second["status"], "ALREADY_CURRENT")
            self.assertEqual(second["updated_files"], [])
            self.assertFalse(second["restart_after_post"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
