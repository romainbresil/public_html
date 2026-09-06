#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
COMMAND = ROOT / "command_port.py"
ISSUE = ROOT / "issue_inbox.py"
WORKER = ROOT / "bridge_worker.py"
MANIFEST = ROOT / "runtime-manifest.json"

RELEASE_ID = "bridge-mig045-gate12b-broker-marker-runtime-repair-20260906-v1"
EXPECTED_ISSUE_SHA256 = "da64818986b268ac961dcac2a07669853aef0ad99619a4ae34b17e5c9bf64453"
EXPECTED_WORKER_SHA256 = "7d7f7839cf0c5931bf8af29c78adef59a4e1a0bab10dfb064150942975635cd4"


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Gate12BBrokerMarkerRuntimeRepairTest(unittest.TestCase):
    def test_only_command_port_runtime_surface_needs_change(self) -> None:
        self.assertEqual(sha(ISSUE), EXPECTED_ISSUE_SHA256)
        self.assertEqual(sha(WORKER), EXPECTED_WORKER_SHA256)

    def test_runtime_manifest_matches_exact_new_runtime_bytes(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["release_id"], RELEASE_ID)
        self.assertEqual(manifest["schema_version"], "1.0")
        for name in ("issue_inbox.py", "bridge_worker.py", "command_port.py"):
            self.assertEqual(manifest["files"][name]["sha256"], sha(ROOT / name), name)

    def test_command_port_layers_on_qualified_previous_runtime(self) -> None:
        text = COMMAND.read_text(encoding="utf-8")
        self.assertIn("gate12b_previous_command_port_missing", text)
        self.assertIn("runtime-updates", text)
        self.assertIn("previous", text)
        self.assertIn("command_port.py", text)

    def test_transient_hotfix_is_bounded_to_exact_membership_contract(self) -> None:
        text = COMMAND.read_text(encoding="utf-8")
        self.assertIn("schema_migration_exact_membership_v1", text)
        self.assertIn("SELECT migration_id FROM elan_naturel.schema_migrations ORDER BY migration_id", text)
        self.assertIn("f05ad6de45a6029b82d51f75e3f97eda7ff48412fdece71b1f183b6c9c18e224", text)
        self.assertIn("/var/lib/elan-vps-v1/work/v1.3-build/", text)
        self.assertNotIn("commit_mig045_gate12b_proof_v1", text)

    def test_hotfix_and_target_process_are_both_restarted_and_read_back(self) -> None:
        text = COMMAND.read_text(encoding="utf-8")
        self.assertIn('_submit_restart(request_key, "hotfix"', text)
        self.assertIn('_submit_restart(request_key, "target"', text)
        self.assertIn('version="1.3.51"', text)
        self.assertIn('version="1.3.52"', text)
        self.assertIn('"proof_executed": False', text)
        self.assertIn('"database_observations_added": 0', text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
