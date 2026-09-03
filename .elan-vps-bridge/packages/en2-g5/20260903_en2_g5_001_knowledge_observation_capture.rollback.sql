-- EN2-G5 rollback — remove the bounded knowledge observation specialization.
\set ON_ERROR_STOP on

BEGIN;

DELETE FROM elan_naturel.information_objects
 WHERE id IN (
   SELECT information_id
     FROM elan_naturel.knowledge_observations
    WHERE idempotency_key = 'en2-g5-canary-20260903-v1'
 );

DROP FUNCTION IF EXISTS elan_naturel.capture_knowledge_observation_v1(jsonb);
DROP TABLE IF EXISTS elan_naturel.knowledge_observations;

DELETE FROM elan_naturel.schema_migrations
 WHERE migration_id = 'EN2_G5_001';

COMMIT;
