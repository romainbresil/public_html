# Élan Naturel — ChatGPT Web VPS bridge control channel

This branch is the minimal transport mailbox for the ChatGPT Web ↔ VPS maintenance bridge.

## Security contract

- Never commit plaintext VPS commands here.
- ChatGPT Web publishes only encrypted **intent events**.
- `.elan-vps-bridge/latest.txt` contains only the filename of the newest encrypted intent envelope.
- Envelopes under `.elan-vps-bridge/jobs/` are CMS-encrypted and base64-encoded.
- The VPS private key never leaves the VPS.
- The corresponding public certificate is published under `.elan-vps-bridge/public.crt`.
- Bootstrap source under `.elan-vps-bridge/bootstrap/` is public by design and contains no credentials.
- Results are posted by the VPS to the dedicated Netlify form `elan-vps-bridge-return`, which ChatGPT Web can read through its connected Netlify surface.

## Accepted intent contract

The decrypted payload is restricted to:

- `intent_code`: `DIAGNOSTIC_REQ`, `SYSTEM_REFRESH`, or `STATE_TOGGLE`;
- `context.target`: currently `elan-bridge` only;
- `context.state`: `active` or `inactive` only for `STATE_TOGGLE`;
- correlation fields `id` and `read_token`.

No `command`, SQL, filesystem path, working directory, timeout or other executable free-form field is accepted.

## Event naming

`<event-id>.cms.b64`

The worker polls raw `latest.txt`, not the GitHub API. It claims each event id locally before backend resolution and never blindly replays a claimed event.

## Current transition

`intentdiag-20260902-001` is the first ChatGPT Web `DIAGNOSTIC_REQ` intent. Publication and pointer dispatch were both accepted by the ChatGPT Web GitHub connector. It remains pending until the already-running VPS worker is upgraded once from the legacy command contract to the intent-only runtime.
