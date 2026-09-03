-- EN2-G6 — bounded synthetic decision absorption canary.
-- Uses the existing dossier_decisions/dossier_events model and cockpit DECISION_RESOLVE facade.
\set ON_ERROR_STOP on

BEGIN;

DO $$
DECLARE
  v_actor_id uuid;
  v_dossier_id constant uuid := '26090300-0000-4000-8000-000000000601'::uuid;
  v_decision_id constant uuid := '26090300-0000-4000-8000-000000000602'::uuid;
  v_idempotency_key constant text := 'en2-g6-decision-resolved-20260903-v1';
  v_first jsonb;
  v_replay jsonb;
  v_active_count bigint;
  v_event_count bigint;
  v_status text;
  v_resolution_text text;
BEGIN
  IF to_regprocedure('elan_naturel.cockpit_business_command_v1(jsonb)') IS NULL THEN
    RAISE EXCEPTION 'EN2_G6_COCKPIT_BUSINESS_COMMAND_REQUIRED';
  END IF;
  IF to_regprocedure('elan_naturel.record_human_decision_v1(jsonb)') IS NULL THEN
    RAISE EXCEPTION 'EN2_G6_RECORD_HUMAN_DECISION_REQUIRED';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM elan_naturel.ref_dossier_decision_types WHERE code = 'QUALIFICATION'
  ) THEN
    RAISE EXCEPTION 'EN2_G6_QUALIFICATION_DECISION_TYPE_REQUIRED';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM elan_naturel.ref_decision_statuses WHERE code = 'REQUESTED'
  ) OR NOT EXISTS (
    SELECT 1 FROM elan_naturel.ref_decision_statuses WHERE code = 'APPROVED'
  ) THEN
    RAISE EXCEPTION 'EN2_G6_DECISION_STATUSES_REQUIRED';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM elan_naturel.ref_dossier_event_types WHERE code = 'DECISION_RESOLVED'
  ) THEN
    RAISE EXCEPTION 'EN2_G6_DECISION_RESOLVED_EVENT_REQUIRED';
  END IF;

  SELECT p.id
    INTO v_actor_id
    FROM elan_naturel.parties p
   WHERE p.metadata->>'system_key' = 'ROMAIN_BECQUART_PROVIDER';

  IF v_actor_id IS NULL THEN
    RAISE EXCEPTION 'EN2_G6_ROMAIN_SYSTEM_ACTOR_REQUIRED';
  END IF;

  IF EXISTS (SELECT 1 FROM elan_naturel.dossiers WHERE id = v_dossier_id)
     OR EXISTS (SELECT 1 FROM elan_naturel.dossier_decisions WHERE id = v_decision_id) THEN
    RAISE EXCEPTION 'EN2_G6_SYNTHETIC_FIXTURE_ALREADY_EXISTS_WITHOUT_MIGRATION';
  END IF;

  INSERT INTO elan_naturel.dossiers (
    id,
    dossier_type_code,
    title,
    summary,
    phase_code,
    stage_code,
    status_code,
    metadata
  )
  VALUES (
    v_dossier_id,
    'UNCLASSIFIED',
    'EN2-G6 SYNTHETIC CANARY — DO NOT CONTACT',
    'Synthetic-only decision absorption qualification fixture. No external action is authorized.',
    'INTAKE',
    'RECEIVED',
    'ACTIVE',
    jsonb_build_object(
      'en2_gate', 'EN2-G6',
      'synthetic_canary', true,
      'external_action_allowed', false
    )
  );

  INSERT INTO elan_naturel.dossier_decisions (
    id,
    dossier_id,
    decision_type_code,
    status_code,
    question,
    context,
    requested_by_party_id,
    assigned_to_party_id,
    due_at,
    metadata
  )
  VALUES (
    v_decision_id,
    v_dossier_id,
    'QUALIFICATION',
    'REQUESTED',
    'EN2-G6 SYNTHETIC CANARY — absorber cette décision ?',
    'Synthetic-only qualification decision. Do not contact anyone.',
    v_actor_id,
    v_actor_id,
    '2099-01-01T00:00:00Z'::timestamptz,
    jsonb_build_object(
      'en2_gate', 'EN2-G6',
      'synthetic_canary', true,
      'external_action_allowed', false
    )
  );

  SELECT count(*)
    INTO v_active_count
    FROM elan_naturel.dossier_decisions
   WHERE id = v_decision_id
     AND dossier_id = v_dossier_id
     AND status_code = ANY (ARRAY['REQUESTED'::text, 'UNDER_REVIEW'::text, 'DEFERRED'::text]);

  IF v_active_count <> 1 THEN
    RAISE EXCEPTION 'EN2_G6_CANARY_ACTIVE_BEFORE_RESOLVE_MUST_BE_ONE: %', v_active_count;
  END IF;

  v_first := elan_naturel.cockpit_business_command_v1(
    jsonb_build_object(
      'mode', 'DECISION_RESOLVE',
      'dossier_id', v_dossier_id,
      'decision_id', v_decision_id,
      'resolution_status', 'APPROVED',
      'resolution_text', 'EN2-G6 synthetic owner decision absorbed; no external action.',
      'idempotency_key', v_idempotency_key
    )
  );

  v_replay := elan_naturel.cockpit_business_command_v1(
    jsonb_build_object(
      'mode', 'DECISION_RESOLVE',
      'dossier_id', v_dossier_id,
      'decision_id', v_decision_id,
      'resolution_status', 'APPROVED',
      'resolution_text', 'EN2-G6 synthetic owner decision absorbed; no external action.',
      'idempotency_key', v_idempotency_key
    )
  );

  IF coalesce((v_first#>>'{result,duplicate}')::boolean, true) THEN
    RAISE EXCEPTION 'EN2_G6_CANARY_FIRST_MUST_NOT_BE_DUPLICATE: %', v_first;
  END IF;
  IF NOT coalesce((v_replay#>>'{result,duplicate}')::boolean, false) THEN
    RAISE EXCEPTION 'EN2_G6_CANARY_REPLAY_MUST_BE_DUPLICATE: %', v_replay;
  END IF;
  IF v_first->>'dossier_id' IS DISTINCT FROM v_dossier_id::text
     OR v_first->>'decision_id' IS DISTINCT FROM v_decision_id::text
     OR v_replay->>'dossier_id' IS DISTINCT FROM v_dossier_id::text
     OR v_replay->>'decision_id' IS DISTINCT FROM v_decision_id::text THEN
    RAISE EXCEPTION 'EN2_G6_CANARY_IDENTITY_MISMATCH';
  END IF;

  SELECT status_code, resolution_text
    INTO v_status, v_resolution_text
    FROM elan_naturel.dossier_decisions
   WHERE id = v_decision_id
     AND dossier_id = v_dossier_id;

  IF v_status <> 'APPROVED'
     OR v_resolution_text <> 'EN2-G6 synthetic owner decision absorbed; no external action.' THEN
    RAISE EXCEPTION 'EN2_G6_CANARY_RESOLUTION_READBACK_MISMATCH: %, %', v_status, v_resolution_text;
  END IF;

  SELECT count(*)
    INTO v_active_count
    FROM elan_naturel.dossier_decisions
   WHERE id = v_decision_id
     AND dossier_id = v_dossier_id
     AND status_code = ANY (ARRAY['REQUESTED'::text, 'UNDER_REVIEW'::text, 'DEFERRED'::text]);

  IF v_active_count <> 0 THEN
    RAISE EXCEPTION 'EN2_G6_CANARY_ACTIVE_QUEUE_NOT_REMOVED: %', v_active_count;
  END IF;

  SELECT count(*)
    INTO v_event_count
    FROM elan_naturel.dossier_events
   WHERE dossier_id = v_dossier_id
     AND decision_id = v_decision_id
     AND event_type_code = 'DECISION_RESOLVED'
     AND source_system = 'human:EN-019-M3'
     AND idempotency_key = v_idempotency_key;

  IF v_event_count <> 1 THEN
    RAISE EXCEPTION 'EN2_G6_CANARY_HISTORY_EVENT_COUNT_MISMATCH: %', v_event_count;
  END IF;
END;
$$;

INSERT INTO elan_naturel.schema_migrations(migration_id, description)
VALUES (
  'EN2_G6_001',
  '{"gate":"EN2-G6","fixture":"synthetic_only","dossier_id":"26090300-0000-4000-8000-000000000601","decision_id":"26090300-0000-4000-8000-000000000602","active_queue_removed":true,"historical_retained":true,"resolution_event_count":1,"idempotent_replay":true,"external_action_allowed":false}'
)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
