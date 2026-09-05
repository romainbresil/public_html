BEGIN;

CREATE ROLE en_gate12b_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
CREATE ROLE en_gate12b_executor NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
GRANT en_gate12b_executor TO CURRENT_USER WITH INHERIT FALSE, SET TRUE;
GRANT USAGE, CREATE ON SCHEMA elan_naturel TO en_gate12b_owner;
GRANT USAGE ON SCHEMA elan_naturel TO en_gate12b_executor;
GRANT SELECT ON elan_naturel.editorial_publication_plans TO en_gate12b_owner;
GRANT SELECT ON elan_naturel.editorial_publication_occurrences TO en_gate12b_owner;

CREATE TABLE elan_naturel.mig045_gate12b_committed_proofs (
    proof_id text PRIMARY KEY,
    proof_contract_sha256 text NOT NULL,
    result_json jsonb NOT NULL,
    committed_at timestamptz NOT NULL,
    CONSTRAINT mig045_gate12b_proof_id_ck CHECK (
        proof_id ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT mig045_gate12b_contract_sha_ck CHECK (
        proof_contract_sha256 ~ '^[0-9a-f]{64}$'
    )
);
ALTER TABLE elan_naturel.mig045_gate12b_committed_proofs OWNER TO en_gate12b_owner;
REVOKE ALL ON TABLE elan_naturel.mig045_gate12b_committed_proofs FROM PUBLIC;

CREATE OR REPLACE FUNCTION elan_naturel.commit_mig045_gate12b_proof_v1(p_input jsonb)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
    v_proof_id text;
    v_contract_sha text;
    v_existing_contract_sha text;
    v_existing_result jsonb;
    v_existing_committed_at timestamptz;
    v_result jsonb;
    v_committed_at timestamptz;
BEGIN
    IF p_input IS NULL OR jsonb_typeof(p_input) <> 'object' THEN
        RAISE EXCEPTION 'gate12b_proof_input_invalid' USING ERRCODE = '22023';
    END IF;
    IF (SELECT count(*) FROM jsonb_object_keys(p_input)) <> 2
       OR NOT (p_input ? 'proof_id')
       OR NOT (p_input ? 'proof_contract_sha256') THEN
        RAISE EXCEPTION 'gate12b_proof_input_invalid' USING ERRCODE = '22023';
    END IF;
    IF jsonb_typeof(p_input->'proof_id') <> 'string' THEN
        RAISE EXCEPTION 'gate12b_proof_id_invalid' USING ERRCODE = '22023';
    END IF;
    IF jsonb_typeof(p_input->'proof_contract_sha256') <> 'string' THEN
        RAISE EXCEPTION 'gate12b_proof_contract_sha256_invalid' USING ERRCODE = '22023';
    END IF;

    v_proof_id := p_input->>'proof_id';
    v_contract_sha := p_input->>'proof_contract_sha256';

    IF v_proof_id IS NULL OR v_proof_id !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'gate12b_proof_id_invalid' USING ERRCODE = '22023';
    END IF;
    IF v_contract_sha IS NULL OR v_contract_sha !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'gate12b_proof_contract_sha256_invalid' USING ERRCODE = '22023';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(v_proof_id, 20260905));

    SELECT proof_contract_sha256, result_json, committed_at
    INTO v_existing_contract_sha, v_existing_result, v_existing_committed_at
    FROM elan_naturel.mig045_gate12b_committed_proofs
    WHERE proof_id = v_proof_id;

    IF FOUND THEN
        IF v_existing_contract_sha <> v_contract_sha THEN
            RAISE EXCEPTION 'gate12b_proof_contract_collision' USING ERRCODE = '22023';
        END IF;
        RETURN jsonb_build_object(
            'proof_id', v_proof_id,
            'proof_contract_sha256', v_existing_contract_sha,
            'replayed', true,
            'result', v_existing_result,
            'committed_at', v_existing_committed_at
        );
    END IF;

    WITH selected_plans AS MATERIALIZED (
        SELECT
            p.plan_id,
            p.content_ref,
            p.channel,
            p.scheduled_on,
            p.authorization_decision_ref,
            p.source_payload
        FROM elan_naturel.editorial_publication_plans p
        WHERE p.content_ref::text = ANY (ARRAY['CON-020', 'CON-021', 'CON-022', 'CON-023', 'CON-024', 'CON-025', 'CON-026', 'CON-027']::text[])
    ),
    selected_occurrences AS MATERIALIZED (
        SELECT
            o.occurrence_id,
            o.plan_id,
            o.programmed_on,
            o.channel_readback_state
        FROM elan_naturel.editorial_publication_occurrences o
        JOIN selected_plans p ON p.plan_id = o.plan_id
    ),
    plans_json AS (
        SELECT COALESCE(
            jsonb_agg(
                jsonb_build_object(
                    'authorization_decision_ref', p.authorization_decision_ref,
                    'channel', p.channel,
                    'content_ref', p.content_ref,
                    'plan_id', p.plan_id,
                    'scheduled_on', p.scheduled_on,
                    'source_payload', jsonb_build_object(
                        'authorization_source', p.source_payload->'authorization_source',
                        'publication_evidence', p.source_payload->'publication_evidence',
                        'publication_link', p.source_payload->'publication_link',
                        'source_status', p.source_payload->'source_status',
                        'time_precision', p.source_payload->'time_precision'
                    )
                ) ORDER BY p.plan_id
            ),
            '[]'::jsonb
        ) AS value
        FROM selected_plans p
    ),
    occurrences_json AS (
        SELECT COALESCE(
            jsonb_agg(
                jsonb_build_object(
                    'channel_readback_state', o.channel_readback_state,
                    'occurrence_id', o.occurrence_id,
                    'plan_id', o.plan_id,
                    'programmed_on', o.programmed_on
                ) ORDER BY o.occurrence_id
            ),
            '[]'::jsonb
        ) AS value
        FROM selected_occurrences o
    )
    SELECT jsonb_build_object(
        'schema_version', 'en033-m1-mig045-gate12b-expected-identity-v1',
        'authorization_authority', jsonb_build_object(
            'decision_family', 'PUBLICATION_AUTHORIZATION',
            'normalized_status', 'AUTHORIZED',
            'current_required', true,
            'decision_ids_by_content', jsonb_build_object(
                'CON-020', 391072,
                'CON-021', 391076,
                'CON-022', 391080,
                'CON-023', 391084,
                'CON-024', 391088,
                'CON-025', 391092,
                'CON-026', 391096,
                'CON-027', 391100
            ),
            'owner_path', 'docs/en-core-migration/CHECKPOINT-TERMINAL-MIG042-PROD-VALIDATED-2026-08-31.md',
            'owner_ref', '18b12254438573f862861ccd9280dc137f83b051',
            'legacy_sentence_used_to_infer_authorization', false
        ),
        'source_contract', jsonb_build_object(
            'fixture_path', 'en-033/mig042/fixtures/contenus-programmed-con020-con027-2026-08-31.json',
            'fixture_ref', '18b12254438573f862861ccd9280dc137f83b051',
            'source_read', jsonb_build_object(
                'spreadsheet_id', '1MTgjR38FYMeaZwSk-eULvgSYAbvPm1hoLE_aCvxp7XI',
                'sheet', 'Contenus',
                'range', 'A1:V28',
                'read_on', '2026-08-31',
                'rule', 'PROGRAMMED != PUBLISHED'
            ),
            'gate12b_normalization', jsonb_build_object(
                'authorization_source', 'fixture.authorization_evidence (documentary payload only; never authorization authority)',
                'publication_link', 'fixture.publication_url',
                'publication_evidence', false,
                'occurrence_programmed_on', 'fixture.scheduled_on per active MIG-042 projector',
                'non_projected_fixture_fields', jsonb_build_array('title', 'programmed_on', 'source_updated_on')
            )
        ),
        'plans', plans_json.value,
        'occurrences', occurrences_json.value
    )
    INTO v_result
    FROM plans_json
    CROSS JOIN occurrences_json;

    v_committed_at := clock_timestamp();
    INSERT INTO elan_naturel.mig045_gate12b_committed_proofs (
        proof_id,
        proof_contract_sha256,
        result_json,
        committed_at
    ) VALUES (
        v_proof_id,
        v_contract_sha,
        v_result,
        v_committed_at
    );

    RETURN jsonb_build_object(
        'proof_id', v_proof_id,
        'proof_contract_sha256', v_contract_sha,
        'replayed', false,
        'result', v_result,
        'committed_at', v_committed_at
    );
END;
$function$;
ALTER FUNCTION elan_naturel.commit_mig045_gate12b_proof_v1(jsonb) OWNER TO en_gate12b_owner;
REVOKE ALL ON FUNCTION elan_naturel.commit_mig045_gate12b_proof_v1(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION elan_naturel.commit_mig045_gate12b_proof_v1(jsonb) TO en_gate12b_executor;
REVOKE CREATE ON SCHEMA elan_naturel FROM en_gate12b_owner;

INSERT INTO elan_naturel.schema_migrations (migration_id, description)
VALUES (
    'EN033_M1_MIG045_GATE12B_PROOF_LEDGER_V1',
    'MIG-045 Gate12B committed proof transaction ledger and least-privilege closed proof owner'
)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
