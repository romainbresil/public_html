# Élan Naturel — ChatGPT Web VPS bridge control channel

This branch contains the public, secret-free bootstrap assets for the ChatGPT Web ↔ VPS bridge.

## Canonical inbound transport

The normal inbox is now **GitHub Issues**, not `latest.txt` + CMS envelopes.

A consumable intent Issue must satisfy all of the following:

- repository: `romainbresil/public_html`;
- state: open;
- author: exactly `romainbresil`;
- title prefix: exactly `EN-INTENT —`;
- body: pure JSON matching the closed business-intent contract.

Example:

```json
{
  "intent_code": "DIAGNOSTIC_REQ",
  "context": {
    "target": "elan-bridge"
  }
}
```

No shell command, SQL, filesystem path, timeout, credential or other executable free-form parameter is accepted.

## Runtime

Public bootstrap payloads live under `.elan-vps-bridge/bootstrap/` and contain no credentials.

The VPS runs:

- `issue_inbox.py` as the public-Issue adapter;
- `bridge_worker.py` as the deterministic intent engine.

The VPS reads public GitHub data only. It stores no GitHub PAT and never writes to GitHub.

## Return channel

Results are posted to the dedicated Netlify form `elan-vps-bridge-return`, which ChatGPT Web reads through its connected Netlify surface.

## Replay rule

Each accepted Issue gets a deterministic local id `gh-issue-<number>` and an exclusive claim under the VPS state directory. A claimed Issue is never blindly replayed.

After successful readback, ChatGPT Web may close the Issue as `completed`.

## Qualified state

`DIAGNOSTIC_REQ + elan-bridge` is E2E-qualified and repeatable.

- probe Issue #3: rejected as designed;
- Issue #4: completed healthy and returned through Netlify;
- Issue #5: created by ChatGPT Web after deployment, completed healthy and returned through Netlify without Codex.

`SYSTEM_REFRESH` and `STATE_TOGGLE` are declared in the backend but are not yet E2E-qualified and must not be treated as acquired capabilities.

## Legacy assets

The following remain only as historical evidence and rollback material:

- `.elan-vps-bridge/latest.txt`;
- `.elan-vps-bridge/jobs/*.cms.b64`;
- `.elan-vps-bridge/public.crt`.

Do not use or replay them as the normal dispatch path.

## Terminal transport state

`ISSUES_INBOX_PASS / DIAGNOSTIC_E2E_REPEATABLE / NETLIFY_RETURN_PASS / CODEX_OUT_OF_NORMAL_PATH`
