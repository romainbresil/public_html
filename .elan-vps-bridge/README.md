# Élan Naturel — ChatGPT Web VPS bridge control channel

This branch is a transport mailbox for the ChatGPT Web ↔ VPS maintenance bridge.

## Security contract

- Never commit plaintext VPS commands here.
- Jobs under `.elan-vps-bridge/jobs/` are CMS-encrypted and base64-encoded.
- The VPS private key never leaves the VPS.
- The corresponding public certificate will be published under `.elan-vps-bridge/public.crt` after the one-time bootstrap.
- Results are not written to this repository; they are served ephemerally by the VPS result endpoint and require the per-job read token contained inside the encrypted job.

## Job naming

`<job-id>.cms.b64`

The worker claims each job id locally before execution and never blindly replays a claimed job.
