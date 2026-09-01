# Élan Naturel — ChatGPT Web VPS bridge control channel

This branch is the minimal transport mailbox for the ChatGPT Web ↔ VPS maintenance bridge.

## Security contract

- Never commit plaintext VPS commands here.
- `.elan-vps-bridge/latest.txt` contains only the filename of the newest encrypted job.
- Jobs under `.elan-vps-bridge/jobs/` are CMS-encrypted and base64-encoded.
- The VPS private key never leaves the VPS.
- The corresponding public certificate is published under `.elan-vps-bridge/public.crt` after the one-time bootstrap.
- Results are not written to this repository; they are served ephemerally by the VPS result endpoint and require the per-job read token contained inside the encrypted job.
- Bootstrap source under `.elan-vps-bridge/bootstrap/` is public by design and contains no credentials.

## Job naming

`<job-id>.cms.b64`

The worker polls raw `latest.txt`, not the GitHub API. It claims each job id locally before execution and never blindly replays a claimed job.
