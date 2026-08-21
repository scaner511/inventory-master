-- ============================================================================
-- Migración 001: Aceptación obligatoria de Términos y Condiciones y
--                Política de Privacidad (Inventory Master OS Web v2026)
-- Fecha: Agosto 2026
--
-- NOTA: el backend aplica estos cambios automáticamente al arrancar
-- (_migrate_accept_terms en app/main.py), tanto en SQLite como en PostgreSQL.
-- Este archivo queda como registro formal / ejecución manual si se prefiere.
--
-- Ejecución manual en PostgreSQL (Render):
--   psql $DATABASE_URL -f migrations/001_terminos_y_condiciones.sql
-- ============================================================================

-- Todo usuario existente queda con accepted_terms = FALSE y verá el modal
-- obligatorio en su próximo inicio de sesión (comportamiento deseado).
ALTER TABLE users ADD COLUMN IF NOT EXISTS accepted_terms BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS accepted_terms_date TIMESTAMP NULL;

-- La aceptación queda registrada en audit_logs con action = 'TERMS_ACCEPTED'
-- (lo escribe el endpoint POST /api/auth/accept-terms; no requiere DDL extra).
