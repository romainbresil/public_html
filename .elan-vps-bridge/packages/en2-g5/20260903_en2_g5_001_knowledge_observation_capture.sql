-- EN2-G5 — bounded knowledge observation capture.
-- Synthetic production canary only; no automatic canonical promotion.
\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS elan_naturel.knowledge_observations (
  information_id uuid PRIMARY KEY
    REFERENCES elan_naturel.information_objects(id) ON DELETE CASCADE,
  epistemic_nature text NOT NULL DEFAULT 'OBSERVATION'
    CHECK (epistemic_nature = 'OBSERVATION'),
  maturity text NOT NULL DEFAULT 'CAPTURED'
    CHECK (maturity IN ('CAPTURED','REVIEWED','SUPERSEDED')),
  canonical_status text NOT NULL DEFAULT 'NON_CANONICAL'
    CHECK (canonical_status = 'NON_CANONICAL'),
  source_system text NOT NULL,
  source_reference text NOT NULL,
  source_occurred_at timestamptz,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key text NOT NULL UNIQUE,
  captured_at timestamptz NOT NULL DEFAULT now(),
  CHECK (btrim(source_system) <> ''),
  CHECK (btrim(source_reference) <> ''),
  CHECK (btrim(idempotency_key) <> '')
);

CREATE OR REPLACE FUNCTION elan_naturel.capture_knowledge_observation_v1(p_payload jsonb)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
  v_information_id uuid;
  v_existing elan_naturel.knowledge_observations%ROWTYPE;
  v_key text := btrim(coalesce(p_payload->>'idempotency_key',''));
  v_content text := nullif(btrim(coalesce(p_payload->>'content_text','')), '');
  v_source_system text := btrim(coalesce(p_payload->>'source_system',''));
  v_source_reference text := btrim(coalesce(p_payload->>'source_reference',''));
  v_source_occurred_at timestamptz;
  v_provenance jsonb := coalesce(p_payload->'provenance','{}'::jsonb);
BEGIN
  IF jsonb_typeof(p_payload) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'EN2_G5_PAYLOAD_OBJECT_REQUIRED';
  END IF;

  IF p_payload ?| ARRAY[
    'canonical_status',
    'canonical_knowledge',
    'promote',
    'promote_canonical',
    'validated_knowledge',
    'validated_by'
  ] THEN
    RAISE EXCEPTION 'EN2_G5_CANONICAL_PROMOTION_FORBIDDEN';
  END IF;

  IF v_key = '' OR v_content IS NULL OR v_source_system = '' OR v_source_reference = '' THEN
    RAISE EXCEPTION 'EN2_G5_REQUIRED_FIELD_MISSING';
  END IF;

  IF jsonb_typeof(v_provenance) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'EN2_G5_PROVENANCE_OBJECT_REQUIRED';
  END IF;

  IF p_payload ? 'source_occurred_at' THEN
    v_source_occurred_at := (p_payload->>'source_occurred_at')::timestamptz;
  END IF;

  SELECT *
    INTO v_existing
    FROM elan_naturel.knowledge_observations
   WHERE idempotency_key = v_key;

  IF FOUND THEN
    RETURN jsonb_build_object(
      'ok', true,
      'duplicate', true,
      'information_id', v_existing.information_id,
      'epistemic_nature', v_existing.epistemic_nature,
      'maturity', v_existing.maturity,
      'canonical_status', v_existing.canonical_status,
      'external_action_allowed', false
    );
  END IF;

  INSERT INTO elan_naturel.information_objects (
    information_type_code,
    confidentiality_code,
    title,
    content_text,
    occurred_at,
    source_system,
    metadata
  )
  VALUES (
    'INTERNAL_NOTE',
    'INTERNAL_ROMAIN',
    'SYNTHETIC CANARY — EN2-G5 KNOWLEDGE OBSERVATION — DO NOT USE AS CANON',
    v_content,
    v_source_occurred_at,
    v_source_system,
    jsonb_build_object(
      'en2_gate', 'EN2-G5',
      'synthetic_canary', true,
      'canonical_status', 'NON_CANONICAL',
      'idempotency_key', v_key
    )
  )
  RETURNING id INTO v_information_id;

  INSERT INTO elan_naturel.knowledge_observations (
    information_id,
    source_system,
    source_reference,
    source_occurred_at,
    provenance,
    idempotency_key
  )
  VALUES (
    v_information_id,
    v_source_system,
    v_source_reference,
    v_source_occurred_at,
    v_provenance,
    v_key
  );

  RETURN jsonb_build_object(
    'ok', true,
    'duplicate', false,
    'information_id', v_information_id,
    'epistemic_nature', 'OBSERVATION',
    'maturity', 'CAPTURED',
    'canonical_status', 'NON_CANONICAL',
    'external_action_allowed', false
  );
END;
$$;

DO $$
DECLARE
  v_payload jsonb := jsonb_build_object(
    'idempotency_key', 'en2-g5-canary-20260903-v1',
    'content_text', 'SYNTHETIC CANARY — observation de connaissance non canonique — aucune personne réelle.',
    'source_system', 'EN2_G5_SYNTHETIC_CANARY',
    'source_reference', 'EN2-G5-CANARY-001',
    'source_occurred_at', '2099-01-01T00:00:00Z',
    'provenance', jsonb_build_object(
      'synthetic_only', true,
      'gate', 'EN2-G5',
      'capture_reason', 'production qualification'
    )
  );
  v_first jsonb;
  v_replay jsonb;
  v_count bigint;
BEGIN
  v_first := elan_naturel.capture_knowledge_observation_v1(v_payload);
  v_replay := elan_naturel.capture_knowledge_observation_v1(v_payload);

  IF coalesce((v_first->>'duplicate')::boolean, true) THEN
    RAISE EXCEPTION 'EN2_G5_CANARY_FIRST_MUST_CREATE: %', v_first;
  END IF;
  IF NOT coalesce((v_replay->>'duplicate')::boolean, false) THEN
    RAISE EXCEPTION 'EN2_G5_CANARY_REPLAY_MUST_DUPLICATE: %', v_replay;
  END IF;
  IF v_first->>'information_id' IS DISTINCT FROM v_replay->>'information_id' THEN
    RAISE EXCEPTION 'EN2_G5_CANARY_IDEMPOTENCY_ID_MISMATCH';
  END IF;
  IF v_first->>'maturity' <> 'CAPTURED'
     OR v_first->>'canonical_status' <> 'NON_CANONICAL'
     OR coalesce((v_first->>'external_action_allowed')::boolean, true) THEN
    RAISE EXCEPTION 'EN2_G5_CANARY_CONTRACT_MISMATCH: %', v_first;
  END IF;

  SELECT count(*)
    INTO v_count
    FROM elan_naturel.knowledge_observations
   WHERE idempotency_key = 'en2-g5-canary-20260903-v1'
     AND epistemic_nature = 'OBSERVATION'
     AND maturity = 'CAPTURED'
     AND canonical_status = 'NON_CANONICAL';

  IF v_count <> 1 THEN
    RAISE EXCEPTION 'EN2_G5_CANARY_READBACK_COUNT_MISMATCH: %', v_count;
  END IF;
END;
$$;

INSERT INTO elan_naturel.schema_migrations(migration_id, description)
VALUES (
  'EN2_G5_001',
  'EN2 G5 bounded knowledge observation capture with non-canonical invariant and synthetic idempotency canary'
)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
