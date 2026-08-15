-- ============================================
-- Inventory Master OS Web - PostgreSQL
-- Este script es OPCIONAL: la aplicación crea
-- las tablas automáticamente al iniciar.
-- Se usa para crear el esquema de forma manual
-- o a través de docker-compose.
-- ============================================

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    email         VARCHAR(255),
    password_hash TEXT         NOT NULL,
    role          VARCHAR(20)  NOT NULL DEFAULT 'operador',
    security_question VARCHAR(255),
    security_answer    VARCHAR(255),
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
    last_login    TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id            SERIAL PRIMARY KEY,
    code          VARCHAR(50)  NOT NULL UNIQUE,
    name          VARCHAR(255) NOT NULL,
    stock         INTEGER      NOT NULL DEFAULT 0,
    purchase_price NUMERIC(12,2) NOT NULL DEFAULT 0,
    sale_price    NUMERIC(12,2) NOT NULL DEFAULT 0,
    location1     VARCHAR(255),
    location2     VARCHAR(255),
    location3     VARCHAR(255),
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS loans (
    id            SERIAL PRIMARY KEY,
    seller        VARCHAR(120) NOT NULL,
    phone         VARCHAR(40),
    product_id    INTEGER      REFERENCES products(id) ON DELETE SET NULL,
    product_name  VARCHAR(255) NOT NULL,
    quantity      INTEGER      NOT NULL,
    returned_qty  INTEGER      NOT NULL DEFAULT 0,
    loan_date     TIMESTAMP    NOT NULL DEFAULT NOW(),
    due_date      DATE         NOT NULL,
    photo_path    TEXT,
    created_by    INTEGER      REFERENCES users(id),
    note          TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id            SERIAL PRIMARY KEY,
    timestamp     TIMESTAMP    NOT NULL DEFAULT NOW(),
    user_id       INTEGER      REFERENCES users(id),
    action        VARCHAR(60)  NOT NULL,
    detail        TEXT,
    product_name  VARCHAR(255),
    quantity      INTEGER
);

CREATE TABLE IF NOT EXISTS settings (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    company_name  VARCHAR(120),
    logo_path     TEXT,
    low_stock_threshold INTEGER NOT NULL DEFAULT 5
);

CREATE TABLE IF NOT EXISTS licenses (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    is_active     BOOLEAN      NOT NULL DEFAULT FALSE,
    activated_at  TIMESTAMP,
    expires_at    DATE,
    last_key      VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS used_license_keys (
    id          SERIAL PRIMARY KEY,
    key_value   VARCHAR(20) NOT NULL UNIQUE,
    used_at     TIMESTAMP   NOT NULL DEFAULT NOW()
);

-- Admin por defecto (contraseña: admin1234)
INSERT INTO users (username, password_hash, role, is_active)
SELECT 'admin',
       '$2b$12$C6UzMDM.H6dfI/f/IKcEeOZKlbO9yNGB2QzVf8V6bU7X0Qp6O0wzC', -- hash bcrypt de "admin1234"
       'admin', TRUE
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'admin');

INSERT INTO settings (id, company_name, low_stock_threshold)
SELECT 1, 'Mi Empresa', 5
WHERE NOT EXISTS (SELECT 1 FROM settings WHERE id = 1);

INSERT INTO licenses (id, is_active)
SELECT 1, FALSE
WHERE NOT EXISTS (SELECT 1 FROM licenses WHERE id = 1);
