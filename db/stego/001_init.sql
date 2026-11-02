-- Contrato 6 v1.0.0 - resultados de análisis exclusivos de STEGO
-- PostgreSQL 16 - esquema stego
-- Uso: psql "$STEGO_DATABASE_URL" -v ON_ERROR_STOP=1 -f db/stego/001_init.sql
--
-- Sin claves foráneas hacia auth: son bases distintas y el acoplamiento
-- entre servicios está prohibido a propósito. user_id es una referencia
-- lógica verificada con AUTH en cada petición.

CREATE SCHEMA IF NOT EXISTS stego;
SET search_path TO stego, public;

CREATE TABLE IF NOT EXISTS stego.analyses (
    analysis_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL,
    filename     text NOT NULL,
    stored_path  text NOT NULL,
    sha256       char(64) NOT NULL,
    content_type text NOT NULL,
    size_bytes   bigint NOT NULL,
    technique    text NOT NULL,
    status       text NOT NULL,
    indicators   jsonb NOT NULL DEFAULT '{}'::jsonb,
    action       text NOT NULL,
    limitations  text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT analyses_status_enum       CHECK (status IN ('sin_indicios', 'sospechosos', 'no_concluyentes', 'error')),
    CONSTRAINT analyses_action_enum       CHECK (action IN ('ninguna', 'advertencia', 'cuarentena', 'rechazo')),
    CONSTRAINT analyses_sha256_hex        CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT analyses_size_positive     CHECK (size_bytes > 0),
    CONSTRAINT analyses_limitations_filled CHECK (char_length(limitations) > 0),
    CONSTRAINT analyses_technique_enum    CHECK (technique = 'lsb_statistical_analysis')
);

CREATE INDEX IF NOT EXISTS analyses_user_created_idx ON stego.analyses (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS analyses_sha256_idx       ON stego.analyses (sha256);
