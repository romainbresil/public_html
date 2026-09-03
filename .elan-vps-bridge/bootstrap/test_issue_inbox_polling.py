#!/usr/bin/env python3
import os
import pathlib
import sys
import unittest
import urllib.parse

BOOTSTRAP = pathlib.Path(__file__).resolve().parent
if str(BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(BOOTSTRAP))

# Reproduce the currently deployed systemd value. The runtime must enforce
# enough headroom for GitHub's unauthenticated API quota even before a future
# reinstall updates the unit environment.
os.environ["ELAN_BRIDGE_POLL_SECONDS"] = "60"

import issue_inbox  # noqa: E402


class IssueInboxPollingContractTest(unittest.TestCase):
    def test_issue_query_is_scoped_to_mailbox_label(self):
        parsed = urllib.parse.urlparse(issue_inbox._issues_url())
        query = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(query.get("labels"), ["elan-cms-chatgpt"])

    def test_runtime_enforces_minimum_poll_interval_of_120_seconds(self):
        self.assertGreaterEqual(issue_inbox.POLL_SECONDS, 120)


if __name__ == "__main__":
    unittest.main()
