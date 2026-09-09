#!/usr/bin/env python3
"""Transient D-owner Gate12B materialization repair layered on the qualified Bridge command port."""
from __future__ import annotations

import hashlib
import importlib.util
import os
import pathlib
import time
from typing import Callable

_RELEASE_ID = "bridge-mig045-gate12b-broker-marker-runtime-repair-20260906-v1"
_DEFAULT_PREVIOUS = pathlib.Path(
    "/var/lib/elan-web-vps-bridge/runtime-updates"
) / _RELEASE_ID / "previous" / "command_port.py"
_PREVIOUS_PATH = pathlib.Path(os.environ.get("ELAN_BRIDGE_PREVIOUS_COMMAND_PORT", str(_DEFAULT_PREVIOUS)))
if not _PREVIOUS_PATH.is_file():
    raise ImportError("gate12b_previous_command_port_missing")

_spec = importlib.util.spec_from_file_location("_elan_gate12b_previous_command_port", _PREVIOUS_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError("gate12b_previous_command_port_unloadable")
_previous = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_previous)
for _name in dir(_previous):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_previous, _name)

_ORIGINAL_MATERIALIZE = _previous.run_mig045_gate12b_technical_materialization_v1
_BROKER_UNIT = "elan-vps-v1-broker.service"
_BROKER_DESTINATION = "/usr/local/sbin/elan-vps-v1-broker"
_STABLE_V1351_BROKER = (
    "/var/lib/elan-vps-v1/work/v1.3-build/"
    "observer/v1.3.0/actions/elan-vps-v1-broker"
)
_EXPECTED_V1351_BROKER_SHA256 = "f05ad6de45a6029b82d51f75e3f97eda7ff48412fdece71b1f183b6c9c18e224"
_HOTFIX_CONTRACT = "schema_migration_exact_membership_v1"
_BAD_MARKER_SQL = "SELECT COALESCE(max(migration_id),'') FROM elan_naturel.schema_migrations"
_GOOD_MARKER_SQL = "SELECT migration_id FROM elan_naturel.schema_migrations ORDER BY migration_id"
_MEMBERSHIP_ANCHOR = (
    'if primitive=="postgres_migration_apply" and args["expected_migration"] '
    'not in after.stdout.decode(errors="replace"):'
)
_MEMBERSHIP_REPLACEMENT = (
    'if primitive=="postgres_migration_apply" and args["expected_migration"] '
    'not in after.stdout.decode(errors="replace").splitlines():'
)


def _transient_broker_wrapper_text() -> str:
    template = """#!/usr/bin/env python3
import hashlib
import pathlib

SOURCE = pathlib.Path(__SOURCE__)
EXPECTED_SHA256 = __EXPECTED_SHA__
BAD_MARKER_SQL = __BAD_SQL__
GOOD_MARKER_SQL = __GOOD_SQL__
HOTFIX_CONTRACT = __CONTRACT__
ANCHOR = __ANCHOR__
REPLACEMENT = __REPLACEMENT__

raw = SOURCE.read_bytes()
if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
    raise SystemExit("gate12b_stable_v1351_broker_sha256_mismatch")
source = raw.decode("utf-8")
if source.count(ANCHOR) != 1:
    raise SystemExit("gate12b_membership_anchor_invalid")
source = source.replace(ANCHOR, REPLACEMENT)
overlay = '''
_MIG045_MARKER_BASE_POSTGRES_PROFILE = Broker._postgres_profile
_MIG045_MARKER_BASE_STATUS = Broker.status
_MIG045_MARKER_BAD_SQL = __BAD_SQL__
_MIG045_MARKER_GOOD_SQL = __GOOD_SQL__
_MIG045_MARKER_CONTRACT = __CONTRACT__

def _mig045_marker_postgres_profile(self, name):
    profile = _MIG045_MARKER_BASE_POSTGRES_PROFILE(self, name)
    if profile.get("migration_marker_sql") == _MIG045_MARKER_BAD_SQL:
        profile = dict(profile)
        profile["migration_marker_sql"] = _MIG045_MARKER_GOOD_SQL
    return profile

def _mig045_marker_status(self):
    value = _MIG045_MARKER_BASE_STATUS(self)
    value["postgres_migration_marker_contract"] = _MIG045_MARKER_CONTRACT
    return value

Broker._postgres_profile = _mig045_marker_postgres_profile
Broker.status = _mig045_marker_status
'''
source += "\\n" + overlay
namespace = {"__name__": "__main__", "__file__": str(SOURCE)}
exec(compile(source, str(SOURCE), "exec"), namespace, namespace)
"""
    replacements = {
        "__SOURCE__": repr(_STABLE_V1351_BROKER),
        "__EXPECTED_SHA__": repr(_EXPECTED_V1351_BROKER_SHA256),
        "__BAD_SQL__": repr(_BAD_MARKER_SQL),
        "__GOOD_SQL__": repr(_GOOD_MARKER_SQL),
        "__CONTRACT__": repr(_HOTFIX_CONTRACT),
        "__ANCHOR__": repr(_MEMBERSHIP_ANCHOR),
        "__REPLACEMENT__": repr(_MEMBERSHIP_REPLACEMENT),
    }
    for token, value in replacements.items():
        template = template.replace(token, value)
    return template


def _plan_fields(plan: object, expected_risk: str) -> dict:
    if not isinstance(plan, dict) or plan.get("risk") != expected_risk:
        raise CommandPortError("gate12b_hotfix_plan_risk_invalid")
    required = ("plan_id", "execution_token", "procedure_sha256")
    if any(not isinstance(plan.get(field), str) or not plan.get(field) for field in required):
        raise CommandPortError("gate12b_hotfix_plan_invalid")
    return plan


def _start(plan: dict, execution_class: str, mode: str, request_fn: Callable[[dict], dict]) -> dict:
    return request_fn({
        "operation": "start_run",
        "plan_id": plan["plan_id"],
        "execution_token": plan["execution_token"],
        "procedure_sha256": plan["procedure_sha256"],
        "execution_class": execution_class,
        "mode": mode,
    })


def _prepare(procedure: dict, key: str, request_fn: Callable[[dict], dict], expected_risk: str) -> dict:
    prepared = request_fn({
        "operation": "prepare_procedure",
        "mission_id": "EN-033/M1",
        "work_id": "MIG045-GATE12B-BROKER-MARKER-RUNTIME-REPAIR",
        "technical_authority": "JA-023",
        "idempotency_key": key,
        "procedure": procedure,
    })
    return _plan_fields(prepared.get("plan"), expected_risk)


def _verify_stable_v1351_source(request_key: str, request_fn: Callable[[dict], dict]) -> None:
    procedure = {
        "procedure_id": f"gate12b-marker-source-{request_key}",
        "title": "Gate12B stable 1.3.51 broker source readback",
        "run_budget_seconds": 60,
        "steps": [{
            "step_id": "stable-v1351-broker",
            "primitive": "file_preflight",
            "args": {"items": [{
                "path": _STABLE_V1351_BROKER,
                "expected_sha256": _EXPECTED_V1351_BROKER_SHA256,
            }]},
            "timeout_seconds": 30,
        }],
    }
    plan = _prepare(procedure, f"gate12b-marker-source-{request_key}", request_fn, "read_only")
    executed = _start(plan, "read_only", "sync", request_fn)
    receipt = executed.get("receipt")
    if not isinstance(receipt, dict) or receipt.get("status") != "succeeded":
        raise CommandPortError("gate12b_stable_v1351_broker_preflight_failed")


def _install_transient_wrapper(request_key: str, request_fn: Callable[[dict], dict]) -> str:
    status = request_fn({"operation": "status"})
    if status.get("server_version") != "1.3.51":
        raise CommandPortError("gate12b_hotfix_requires_v1351")
    _verify_stable_v1351_source(request_key, request_fn)

    content = _transient_broker_wrapper_text()
    raw = content.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    staged = request_fn({
        "operation": "stage_text",
        "content": content,
        "expected_sha256": digest,
        "media_type": "text/x-python",
        "label": "mig045-gate12b-transient-broker-wrapper",
    })
    artifact = staged.get("artifact")
    if not isinstance(artifact, dict) or artifact.get("sha256") != digest:
        raise CommandPortError("gate12b_hotfix_stage_failed")
    artifact_id = artifact.get("artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise CommandPortError("gate12b_hotfix_stage_invalid")

    procedure = {
        "procedure_id": f"gate12b-marker-install-{request_key}",
        "title": "Gate12B transient broker marker repair install",
        "run_budget_seconds": 90,
        "steps": [{
            "step_id": "install-broker-marker-hotfix",
            "primitive": "install_file_atomic",
            "args": {
                "artifact_id": artifact_id,
                "destination": _BROKER_DESTINATION,
                "mode": "0755",
            },
            "timeout_seconds": 60,
        }],
    }
    plan = _prepare(
        procedure,
        f"gate12b-marker-install-{request_key}",
        request_fn,
        "reversible_technical_change",
    )
    executed = _start(plan, "reversible_technical_change", "sync", request_fn)
    receipt = executed.get("receipt")
    if not isinstance(receipt, dict) or receipt.get("status") != "succeeded":
        raise CommandPortError("gate12b_hotfix_install_failed")
    return artifact_id


def _submit_restart(request_key: str, phase: str, request_fn: Callable[[dict], dict]) -> None:
    procedure = {
        "procedure_id": f"gate12b-broker-restart-{phase}-{request_key}",
        "title": f"Gate12B broker restart {phase}",
        "run_budget_seconds": 90,
        "steps": [{
            "step_id": "restart-broker",
            "primitive": "systemd_unit",
            "args": {"unit": _BROKER_UNIT, "action": "restart"},
            "timeout_seconds": 60,
        }],
    }
    plan = _prepare(
        procedure,
        f"gate12b-broker-restart-{phase}-{request_key}",
        request_fn,
        "reversible_technical_change",
    )
    queued = _start(plan, "reversible_technical_change", "async", request_fn)
    receipt = queued.get("receipt")
    if not isinstance(receipt, dict) or receipt.get("status") not in {"queued", "running"}:
        raise CommandPortError("gate12b_broker_restart_not_queued")


def _wait_broker(
    *,
    version: str,
    marker_contract: str | None,
    request_fn: Callable[[dict], dict],
    timeout_seconds: int = 120,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            status = request_fn({"operation": "status"})
            if status.get("server_version") != version:
                time.sleep(2)
                continue
            observed = status.get("postgres_migration_marker_contract")
            if marker_contract is None:
                if observed is not None:
                    time.sleep(2)
                    continue
            elif observed != marker_contract:
                time.sleep(2)
                continue
            return status
        except Exception as exc:
            last_error = exc
            time.sleep(2)
    if last_error:
        raise CommandPortError("gate12b_broker_restart_readback_timeout") from last_error
    raise CommandPortError("gate12b_broker_restart_readback_timeout")


def _cleanup_artifact_safely(artifact_id: str | None, request_fn: Callable[[dict], dict]) -> None:
    if not artifact_id:
        return
    try:
        request_fn({"operation": "cleanup_artifact", "artifact_id": artifact_id})
    except Exception:
        pass


def run_mig045_gate12b_technical_materialization_v1(
    request_id: str,
    artifact_url: str,
    request_fn: Callable[[dict], dict] = broker_request,
    fetch_fn: Callable[[str], bytes] = _fetch_control_path,
    ready_fn: Callable[[], dict] = _mig045_gate12b_wait_ready_v1352,
) -> dict:
    request_key = _safe_key(request_id).lower()
    hotfix_artifact_id: str | None = None
    try:
        hotfix_artifact_id = _install_transient_wrapper(request_key, request_fn)
        _submit_restart(request_key, "hotfix", request_fn)
        hotfix_status = _wait_broker(
            version="1.3.51",
            marker_contract=_HOTFIX_CONTRACT,
            request_fn=request_fn,
        )

        release_install_seen = False

        def proxy(payload: dict) -> dict:
            nonlocal release_install_seen
            response = request_fn(payload)
            if payload.get("operation") == "start_run":
                receipt = response.get("receipt")
                steps = receipt.get("steps") if isinstance(receipt, dict) else None
                if isinstance(steps, list):
                    for step in steps:
                        if (
                            isinstance(step, dict)
                            and step.get("step_id") == "qualified-release-install"
                            and step.get("status") == "success"
                        ):
                            release_install_seen = True
                            _submit_restart(request_key, "target", request_fn)
                            _wait_broker(version="1.3.52", marker_contract=None, request_fn=request_fn)
                            break
            return response

        result = _ORIGINAL_MATERIALIZE(
            request_id,
            artifact_url,
            request_fn=proxy,
            fetch_fn=fetch_fn,
            ready_fn=ready_fn,
        )
        if not release_install_seen:
            raise CommandPortError("gate12b_target_release_install_not_observed")
        target_status = _wait_broker(version="1.3.52", marker_contract=None, request_fn=request_fn)
        return {
            **result,
            "broker_marker_repair": {
                "status": "PASS",
                "transient": True,
                "contract": _HOTFIX_CONTRACT,
                "hotfix_process_version": hotfix_status.get("server_version"),
                "target_process_version": target_status.get("server_version"),
                "business_reads": 0,
                "proof_executed": False,
                "database_observations_added": 0,
            },
        }
    finally:
        _cleanup_artifact_safely(hotfix_artifact_id, request_fn)


"""Transversal mailbox transport; native policy retains execution authority."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import uuid

_MB_FIELDS = {'project_id','mission_id','work_id','request_id','operation','payload'}
_MB_OPS = {'capabilities','procedure','run_status','release_install','release_observe','host_runtime_update'}
_MB_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_./:-]{0,119}$')
_MB_SHA = re.compile(r'^[a-f0-9]{64}$')
_MB_HOST_SOCKET = '/run/elan-mailbox-host/control.sock'


def mailbox_validate_context(context):
    if not isinstance(context,dict) or set(context)!=_MB_FIELDS:
        raise ValueError('mailbox_context_fields_invalid')
    for field in ('project_id','mission_id','work_id'):
        if not isinstance(context[field],str) or not _MB_ID.fullmatch(context[field]):
            raise ValueError('mailbox_identity_invalid')
    try:
        if str(uuid.UUID(context['request_id']))!=context['request_id']:raise ValueError()
    except (ValueError,TypeError,AttributeError):raise ValueError('mailbox_request_id_invalid')
    op=context['operation']; p=context['payload']
    if not isinstance(op,str) or op not in _MB_OPS or not isinstance(p,dict):raise ValueError('mailbox_operation_invalid')
    if len(json.dumps(context,ensure_ascii=False).encode())>131072:raise ValueError('mailbox_context_too_large')
    fields={'capabilities':set(),'run_status':{'plan_id'},'release_install':{'release_id'},'host_runtime_update':{'update_id','source_commit','manifest_sha256','artifact_id','artifact_sha256','artifact_size_bytes','ci_run_id'},'release_observe':{'issue_number'},'procedure':{'expected_policy_hash','expected_capability_hash','execution_class','procedure'}}[op]
    if set(p)!=fields:raise ValueError('mailbox_payload_fields_invalid')
    if op=='procedure':
        if any(not isinstance(p[k],str) or not _MB_SHA.fullmatch(p[k]) for k in ['expected_policy_hash','expected_capability_hash']):raise ValueError('mailbox_native_binding_invalid')
        if not isinstance(p['execution_class'],str) or p['execution_class'] not in {'read_only','reversible_technical_change','mutating_technical_change'} or not isinstance(p['procedure'],dict):raise ValueError('mailbox_procedure_invalid')
        # Installation through the generic route would omit the host guards.
        steps=p['procedure'].get('steps')
        if not isinstance(steps,list) or not steps:raise ValueError('mailbox_procedure_invalid')
        if any(not isinstance(s,dict) or s.get('primitive')=='qualified_release_install' for s in steps):raise ValueError('mailbox_use_guarded_release_route')
    if op=='host_runtime_update':
        if not isinstance(p['update_id'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}',p['update_id']):raise ValueError('mailbox_update_id_invalid')
        if not isinstance(p['source_commit'],str) or not re.fullmatch(r'[a-f0-9]{40}',p['source_commit']):raise ValueError('mailbox_update_commit_invalid')
        if any(not isinstance(p[k],str) or not _MB_SHA.fullmatch(p[k]) for k in ('manifest_sha256','artifact_sha256')):raise ValueError('mailbox_update_hash_invalid')
        if type(p['artifact_size_bytes']) is not int or not 1<=p['artifact_size_bytes']<=1073741824:raise ValueError('mailbox_update_size_invalid')
        if not isinstance(p['ci_run_id'],str) or not re.fullmatch(r'[1-9][0-9]{0,19}',p['ci_run_id']):raise ValueError('mailbox_update_ci_invalid')
        try:uuid.UUID(p['artifact_id'])
        except (ValueError,TypeError,AttributeError):raise ValueError('mailbox_update_artifact_invalid')
    if op=='run_status':
        try:uuid.UUID(p['plan_id'])
        except (ValueError,TypeError,AttributeError):raise ValueError('mailbox_plan_id_invalid')
    if op=='release_install' and (not isinstance(p['release_id'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}',p['release_id'])):raise ValueError('mailbox_release_id_invalid')
    if op=='release_observe' and (type(p['issue_number']) is not int or p['issue_number']<1):raise ValueError('mailbox_issue_invalid')
    return context


def _mb_write(path,value):
    raw=json.dumps(value,sort_keys=True,separators=(',',':')).encode()+b'\n'
    temp=path.with_name(path.name+'.tmp')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
    os.replace(temp,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def _mb_receipt(response,context,plan_id):
    r=response.get('receipt',response)
    if not isinstance(r,dict) or r.get('plan_id',r.get('run_id'))!=plan_id or r.get('mission_id')!=context['mission_id'] or r.get('work_id')!=context['work_id']:raise ValueError('mailbox_receipt_binding_invalid')
    return _mb_public_fields(r, {'status','plan_id','run_id','procedure_sha256','started_at','finished_at','policy_hash','capability_hash'})


def mailbox_host_request(operation,issue_number):
    wire=json.dumps({'schema':'mailbox-host-request-v1','operation':operation,'issue_number':issue_number}).encode()+b'\n'
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(45);client.connect(_MB_HOST_SOCKET);client.sendall(wire);client.shutdown(socket.SHUT_WR)
        chunks=[];size=0
        while True:
            block=client.recv(8192)
            if not block:break
            size+=len(block)
            if size>65536:raise ValueError('mailbox_host_response_too_large')
            chunks.append(block)
    response=json.loads(b''.join(chunks))
    return mailbox_public_host_response(response, issue_number)


def mailbox_public_host_response(response, issue_number):
    if not isinstance(response,dict) or response.get('schema')!='mailbox-host-response-v1' or type(response.get('issue_number')) is not int or response['issue_number']!=issue_number:raise ValueError('mailbox_host_response_invalid')
    allowed={'schema','status','issue_number','run_id','source_commit','artifact_sha256','error','request_id','release_id','install_run_id','activation_status','ready_sha256','manifest_sha256','update_id'}
    return _mb_public_fields(response, allowed)


def mailbox_execute(context,*,issue_number,state_root,request_fn,host_fn=mailbox_host_request):
    c=mailbox_validate_context(context);op=c['operation'];p=c['payload']
    if op=='capabilities':
        s=request_fn({'operation':'status'})
        _mb_public_fields(s, {'policy_hash','capability_hash'})
        if not isinstance(s.get('server_version'),str) or not re.fullmatch(r'[0-9]+[.][0-9]+[.][0-9]+',s['server_version']):raise ValueError('mailbox_status_invalid')
        if not isinstance(s.get('primitives'),list) or any(not isinstance(x,str) or not re.fullmatch(r'[a-z][a-z0-9_.]{0,79}',x) for x in s['primitives']):raise ValueError('mailbox_primitives_invalid')
        return {'status':'OBSERVED','contract':'elan-technical-mailbox-v1','project_id':c['project_id'],'broker_version':s.get('server_version'),'policy_hash':s.get('policy_hash'),'capability_hash':s.get('capability_hash'),'native_primitives':s.get('primitives',[]),'host_installation':'REQUIRES_SEPARATE_HOST_CAPABILITY_PROOF'}
    if op in {'release_install','host_runtime_update'}:return host_fn('execute',issue_number)
    if op=='release_observe':return host_fn('observe',p['issue_number'])
    if op=='run_status':
        known=False
        for entry in (Path(state_root)/'technical-mailbox').glob('*.json'):
            if entry.is_symlink():continue
            value=json.loads(entry.read_text())
            identity=value.get('identity',{})
            if value.get('plan_id')==p['plan_id'] and all(identity.get(k)==c[k] for k in ('project_id','mission_id','work_id')):known=True;break
        if not known:raise ValueError('mailbox_project_binding_invalid')
        return _mb_receipt(request_fn({'operation':'get_run','plan_id':p['plan_id']}),c,p['plan_id'])
    identity={k:c[k] for k in ('project_id','mission_id','work_id','request_id')}
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    digest=hashlib.sha256(json.dumps(c,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    root=Path(state_root)/'technical-mailbox';root.mkdir(mode=0o700,parents=True,exist_ok=True)
    if root.is_symlink():raise ValueError('mailbox_state_unsafe')
    path=root/(key+'.json')
    fd=os.open(root/(key+'.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if path.exists():
            if path.is_symlink():raise ValueError('mailbox_state_unsafe')
            saved=json.loads(path.read_text())
            if saved.get('request_sha256')!=digest:raise ValueError('mailbox_idempotency_conflict')
            if not saved.get('plan_id'):return {'status':'prepare_outcome_unknown','request_id':c['request_id'],'native_idempotency_key':'mailbox-'+key}
            try:return _mb_receipt(request_fn({'operation':'get_run','plan_id':saved['plan_id']}),c,saved['plan_id'])
            except Exception:return {'status':'observation_required','plan_id':saved['plan_id']}
        saved={'request_sha256':digest,'identity':identity,'source_issue':issue_number,'state':'preparing','native_idempotency_key':'mailbox-'+key}
        _mb_write(path,saved)
        response=request_fn({'operation':'prepare_procedure','technical_authority':'JA-023','mission_id':c['mission_id'],'work_id':c['work_id'],'idempotency_key':'mailbox-'+key,'procedure':p['procedure']})
        plan=response.get('plan',response)
        if not isinstance(plan,dict):raise ValueError('mailbox_prepared_binding_invalid')
        try:uuid.UUID(plan['plan_id'])
        except (KeyError,TypeError,ValueError,AttributeError):raise ValueError('mailbox_prepared_binding_invalid')
        saved.update(plan_id=plan['plan_id'],state='prepared');_mb_write(path,saved)
        if (plan.get('risk'),plan.get('policy_hash'),plan.get('capability_hash'))!=(p['execution_class'],p['expected_policy_hash'],p['expected_capability_hash']):raise ValueError('mailbox_prepared_binding_invalid')
        if not isinstance(plan.get('execution_token'),str) or not isinstance(plan.get('procedure_sha256'),str):raise ValueError('mailbox_prepared_binding_invalid')
        saved['state']='start_requested';_mb_write(path,saved)
        try:
            response=request_fn({'operation':'start_run','plan_id':plan['plan_id'],'execution_token':plan['execution_token'],'procedure_sha256':plan['procedure_sha256'],'execution_class':plan['risk'],'mode':'async'})
            receipt=_mb_receipt(response,c,plan['plan_id'])
        except Exception:
            try:receipt=_mb_receipt(request_fn({'operation':'get_run','plan_id':plan['plan_id']}),c,plan['plan_id'])
            except Exception:receipt={'status':'observation_required','plan_id':plan['plan_id']}
        saved['state']='observed';saved['public_receipt']=receipt;_mb_write(path,saved)
        return receipt


_MB_STATES = {'accepted','OBSERVED','UNAVAILABLE','queued','running','cancelling','succeeded','success','failed_rolled_back','failed_critical','cancelled','interrupted','interrupted_not_executed','interrupted_ambiguous','activation_launched','activation_succeeded','activation_failed','observation_required','prepare_outcome_unknown','FAIL_CLOSED','UNKNOWN','INSTALL_PREPARED','INSTALL_START_REQUESTED','ACTIVATION_REQUESTED','host_update_pending','host_update_succeeded','host_update_failed_rolled_back','host_update_failed_critical'}


def _mb_public_fields(value, allowed):
    output={}
    for k in allowed:
        if k not in value:continue
        v=value[k]
        if v is None and k in {'started_at','finished_at','run_id','install_run_id','activation_status','ready_sha256','manifest_sha256','update_id'}:output[k]=None;continue
        if k in {'status','activation_status','ready_sha256','manifest_sha256','update_id'}:
            if not isinstance(v,str) or v not in _MB_STATES:raise ValueError('mailbox_public_status_invalid')
        elif k=='issue_number':
            if type(v) is not int or v<1:raise ValueError('mailbox_public_issue_invalid')
        elif k in {'plan_id','run_id','install_run_id','request_id'}:
            try:uuid.UUID(v)
            except (ValueError,TypeError,AttributeError):raise ValueError('mailbox_public_uuid_invalid')
        elif k.endswith('_sha256') or k in {'policy_hash','capability_hash'}:
            if not isinstance(v,str) or not _MB_SHA.fullmatch(v):raise ValueError('mailbox_public_hash_invalid')
        elif k=='source_commit':
            if not isinstance(v,str) or not re.fullmatch(r'[a-f0-9]{40}',v):raise ValueError('mailbox_public_commit_invalid')
        elif k in {'started_at','finished_at'}:
            if not isinstance(v,str) or not re.fullmatch(r'[0-9TZ: .+\-]{10,40}',v):raise ValueError('mailbox_public_timestamp_invalid')
        elif k=='error':
            if not isinstance(v,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,99}',v):raise ValueError('mailbox_public_error_invalid')
            v='host_refused' # Detailed errors remain in the protected host record.
        elif k=='schema':
            if v!='mailbox-host-response-v1':raise ValueError('mailbox_public_schema_invalid')
        elif k in {'release_id','update_id'}:
            if not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}',v):raise ValueError('mailbox_public_release_invalid')
        output[k]=v
    return output


def mailbox_recover(context,*,issue_number,state_root,request_fn,host_fn=mailbox_host_request):
    c=mailbox_validate_context(context)
    if c['operation'] in {'release_install','host_runtime_update'}:return host_fn('observe',issue_number)
    if c['operation']=='procedure':
        identity={k:c[k] for k in ('project_id','mission_id','work_id','request_id')}
        key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        if not (Path(state_root)/'technical-mailbox'/(key+'.json')).exists():
            return {'status':'observation_required','request_id':c['request_id']}
    return mailbox_execute(c,issue_number=issue_number,state_root=state_root,request_fn=request_fn,host_fn=host_fn)


def mailbox_publish_receipt(result, *, delivered, request_fn):
    if result.get('intent_code')!='EN_TECHNICAL_MAILBOX_V1':return None
    c=mailbox_validate_context(result['context'])
    payload=result.get('result',{})
    # Build from our typed output contract; exclude context.payload and read_token.
    fields={'status','plan_id','run_id','install_run_id','source_commit','artifact_sha256','procedure_sha256','policy_hash','capability_hash','started_at','finished_at','issue_number','request_id','schema','release_id','error','activation_status','ready_sha256','manifest_sha256','update_id'}
    public_payload=_mb_public_fields(payload, fields)
    record={'schema':'mailbox-public-receipt-v1','job_id':result['id'],'project_id':c['project_id'],'mission_id':c['mission_id'],'work_id':c['work_id'],'request_id':c['request_id'],'operation':c['operation'],'netlify_delivery_acknowledged':bool(delivered),'result':public_payload}
    raw=json.dumps(record,sort_keys=True,separators=(',',':'))
    return request_fn({'operation':'stage_text','content':raw,'expected_sha256':hashlib.sha256(raw.encode()).hexdigest(),'media_type':'application/json','label':'mailbox-receipt-'+result['id']+('-delivered' if delivered else '-pending')})
