#!/bin/sh
set -eu
STATE=/var/lib/elan-vps-v1
ROLLBACK=$STATE/rollback-v1.3.2
LEGACY=$ROLLBACK/legacy-helpers
TARGETS=$ROLLBACK/legacy-helper-targets.tsv
POLICY=/etc/elan-vps-v1/policy.json
ORIGINAL=/usr/local/lib/elan-vps-v1/.en034-finalize-v1.3.1
FINALIZER=/usr/local/lib/elan-vps-v1/finalize-v1.3
RECEIPT=$STATE/en034-bootstrap-policy.json
EXPECTED_ORIGINAL=91aeddf1c1bebb151f53d604ddc40a4cc98e99623e4e025d8dec9237f426270e

test -s "$POLICY" || { echo active_policy_missing >&2; exit 20; }
test -s "$ORIGINAL" || { echo original_finalizer_missing >&2; exit 21; }
test "$(sha256sum "$ORIGINAL" | awk '{print $1}')" = "$EXPECTED_ORIGINAL" || { echo original_finalizer_hash_mismatch >&2; exit 22; }

install -d -m 700 "$ROLLBACK" "$LEGACY"
if [ ! -f "$ROLLBACK/policy.json" ]; then
  install -m 600 "$POLICY" "$ROLLBACK/policy.json"
fi
if [ ! -f "$TARGETS" ]; then
  tmp_targets=$(mktemp "$ROLLBACK/.legacy-helper-targets.XXXXXX")
  : > "$tmp_targets"
  for spec in \
    "/usr/local/lib/elan-vps-v1/build-v1.3-once:build-v1.3-once" \
    "/usr/local/lib/elan-vps-v1/inspect-image-archive.py:inspect-image-archive.py" \
    "/usr/local/lib/elan-vps-v1/derive-policy-v1.3.py:derive-policy-v1.3.py" \
    "$ORIGINAL:finalize-v1.3" \
    "/usr/local/lib/elan-vps-v1/activate-v1.3:activate-v1.3"
  do
    source=${spec%%:*}
    name=${spec#*:}
    test -f "$source" && test ! -L "$source" || { rm -f "$tmp_targets"; echo legacy_helper_invalid >&2; exit 23; }
    mode=$(stat -c %a "$source")
    install -m "$mode" "$source" "$LEGACY/$name"
    target="/usr/local/lib/elan-vps-v1/$name"
    printf '%s\t%s\t%s\n' "$target" "$mode" "$name" >> "$tmp_targets"
  done
  chmod 600 "$tmp_targets"
  mv -f "$tmp_targets" "$TARGETS"
fi

python3 - "$POLICY" "$RECEIPT" <<'PY'
import datetime,hashlib,json,os,pathlib,sys,tempfile
policy_path,receipt_path=map(pathlib.Path,sys.argv[1:])
raw=policy_path.read_bytes()
value=json.loads(raw)
if not isinstance(value,dict):
    raise SystemExit("active_policy_invalid")
paths=set(value.get("allowed_write_paths") or [])
units=set(value.get("allowed_systemd_units") or [])
paths.update({
    "/etc/elan-vps-v1/release-manifest.json",
    "/etc/systemd/system/elan-vps-v1-release-rollback.service",
    "/etc/systemd/system/elan-vps-v1-en034-restore-policy.service",
})
units.update({
    "elan-vps-v1-release-rollback.service",
    "elan-vps-v1-en034-restore-policy.service",
})
value["allowed_write_paths"]=sorted(paths)
value["allowed_systemd_units"]=sorted(units)
encoded=(json.dumps(value,indent=2,sort_keys=True,ensure_ascii=False)+"\n").encode()
fd,tmp=tempfile.mkstemp(prefix=".policy.en034.",dir=policy_path.parent)
try:
    os.write(fd,encoded);os.fsync(fd);os.close(fd);os.chmod(tmp,0o600);os.replace(tmp,policy_path)
finally:
    try: os.close(fd)
    except OSError: pass
    pathlib.Path(tmp).unlink(missing_ok=True)
receipt={
    "schema":"en-034-bootstrap-policy-v1",
    "original_sha256":hashlib.sha256(raw).hexdigest(),
    "augmented_sha256":hashlib.sha256(encoded).hexdigest(),
    "added_write_paths":[
        "/etc/elan-vps-v1/release-manifest.json",
        "/etc/systemd/system/elan-vps-v1-release-rollback.service",
        "/etc/systemd/system/elan-vps-v1-en034-restore-policy.service",
    ],
    "added_units":[
        "elan-vps-v1-release-rollback.service",
        "elan-vps-v1-en034-restore-policy.service",
    ],
    "created_at":datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z"),
}
receipt_path.write_text(json.dumps(receipt,sort_keys=True,separators=(",",":"))+"\n")
os.chmod(receipt_path,0o600)
PY

install -m 755 "$ORIGINAL" "$FINALIZER"
rm -f "$ORIGINAL"
exit 0
