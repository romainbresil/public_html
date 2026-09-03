\set ON_ERROR_STOP on
BEGIN;

DELETE FROM elan_naturel.dossier_events
 WHERE dossier_id = '26090300-0000-4000-8000-000000000601'::uuid;

DELETE FROM elan_naturel.dossier_actions
 WHERE dossier_id = '26090300-0000-4000-8000-000000000601'::uuid;

DELETE FROM elan_naturel.dossier_decisions
 WHERE id = '26090300-0000-4000-8000-000000000602'::uuid
   AND dossier_id = '26090300-0000-4000-8000-000000000601'::uuid;

DELETE FROM elan_naturel.dossiers
 WHERE id = '26090300-0000-4000-8000-000000000601'::uuid;

DELETE FROM elan_naturel.schema_migrations
 WHERE migration_id = 'EN2_G6_001';

COMMIT;
