-- Contrato 5 v1.0.0 - identidad exclusiva de AUTH
-- PostgreSQL 16 - esquema auth
-- Uso: psql "$AUTH_DATABASE_URL" -v ON_ERROR_STOP=1 -f db/auth/001_init.sql

CREATE SCHEMA IF NOT EXISTS auth;
SET search_path TO auth, public;

-- ---------------------------------------------------------------- usuarios
CREATE TABLE IF NOT EXISTS auth.users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username      text NOT NULL,
    email         text NOT NULL,
    password_hash text NOT NULL,
    status        text NOT NULL DEFAULT 'active',
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT users_username_len   CHECK (char_length(username) BETWEEN 3 AND 64),
    CONSTRAINT users_email_format   CHECK (email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'),
    CONSTRAINT users_status_enum    CHECK (status IN ('active', 'inactive', 'locked')),
    CONSTRAINT users_hash_not_empty CHECK (char_length(password_hash) >= 20)
);

CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower_uniq ON auth.users (lower(username));
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_uniq    ON auth.users (lower(email));

-- ------------------------------------------------------------------- roles
CREATE TABLE IF NOT EXISTS auth.roles (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    description text,
    status      text NOT NULL DEFAULT 'active',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT roles_name_format CHECK (name ~ '^[A-Z][A-Z0-9_]{2,31}$'),
    CONSTRAINT roles_status_enum CHECK (status IN ('active', 'inactive'))
);

CREATE UNIQUE INDEX IF NOT EXISTS roles_name_lower_uniq ON auth.roles (lower(name));

-- ------------------------------------------------------ relación N:M user_roles
CREATE TABLE IF NOT EXISTS auth.user_roles (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    role_id     uuid NOT NULL REFERENCES auth.roles (id) ON DELETE RESTRICT,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    assigned_by uuid REFERENCES auth.users (id) ON DELETE SET NULL,
    status      text NOT NULL DEFAULT 'active',
    CONSTRAINT user_roles_unique      UNIQUE (user_id, role_id),
    CONSTRAINT user_roles_status_enum CHECK (status IN ('active', 'inactive'))
);

CREATE INDEX IF NOT EXISTS user_roles_user_id_idx ON auth.user_roles (user_id);
CREATE INDEX IF NOT EXISTS user_roles_role_id_idx ON auth.user_roles (role_id);
CREATE INDEX IF NOT EXISTS user_roles_active_idx  ON auth.user_roles (user_id, status);

-- --------------------------------------------- revocación de JWT (logout)
CREATE TABLE IF NOT EXISTS auth.revoked_tokens (
    jti        uuid PRIMARY KEY,
    subject_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz NOT NULL DEFAULT now(),
    reason     text NOT NULL DEFAULT 'logout'
);

CREATE INDEX IF NOT EXISTS revoked_tokens_expires_at_idx ON auth.revoked_tokens (expires_at);

-- ------------------------------------------ clientes de servicio (contrato 3)
CREATE TABLE IF NOT EXISTS auth.service_clients (
    client_id   text PRIMARY KEY,
    secret_hash text NOT NULL,
    status      text NOT NULL DEFAULT 'active',
    audience    text NOT NULL DEFAULT 'auth-internal',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT service_clients_status_enum CHECK (status IN ('active', 'inactive'))
);

-- ---------------------------------------------------- updated_at automático
CREATE OR REPLACE FUNCTION auth.touch_updated_at()
RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS users_touch_updated_at ON auth.users;
CREATE TRIGGER users_touch_updated_at
    BEFORE UPDATE ON auth.users
    FOR EACH ROW EXECUTE FUNCTION auth.touch_updated_at();

DROP TRIGGER IF EXISTS roles_touch_updated_at ON auth.roles;
CREATE TRIGGER roles_touch_updated_at
    BEFORE UPDATE ON auth.roles
    FOR EACH ROW EXECUTE FUNCTION auth.touch_updated_at();

DROP TRIGGER IF EXISTS service_clients_touch_updated_at ON auth.service_clients;
CREATE TRIGGER service_clients_touch_updated_at
    BEFORE UPDATE ON auth.service_clients
    FOR EACH ROW EXECUTE FUNCTION auth.touch_updated_at();

-- ------------------------------------------------- sembrado idempotente de roles
INSERT INTO auth.roles (name, description)
VALUES
    ('ADMIN',   'Administración de identidades, roles y asignaciones'),
    ('ANALYST', 'Análisis de imágenes y consulta de sus resultados'),
    ('USER',    'Acceso al propio perfil')
ON CONFLICT DO NOTHING;
