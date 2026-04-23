CREATE TABLE IF NOT EXISTS tag_readings (
    id          BIGSERIAL       PRIMARY KEY,
    tag_name    VARCHAR(100)    NOT NULL,
    value       DOUBLE PRECISION NOT NULL,
    unit        VARCHAR(20)     DEFAULT '',
    recorded_at TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tag_readings_name_time
    ON tag_readings (tag_name, recorded_at DESC);

CREATE TABLE IF NOT EXISTS setpoints (
    id           SERIAL          PRIMARY KEY,
    tag_name     VARCHAR(100)    NOT NULL,
    target_value DOUBLE PRECISION NOT NULL,
    applied      BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    applied_at   TIMESTAMPTZ     NULL
);

CREATE TABLE IF NOT EXISTS tag_catalog (
    id              SERIAL       PRIMARY KEY,
    tag_name        VARCHAR(100) NOT NULL UNIQUE,
    description     TEXT,
    modbus_address  INT,
    modbus_type     VARCHAR(20),
    scale_factor    FLOAT        DEFAULT 1.0,
    unit            VARCHAR(20),
    active          BOOLEAN      DEFAULT TRUE
);

INSERT INTO tag_catalog (tag_name, description, modbus_address, modbus_type, scale_factor, unit)
VALUES
    ('TEMPERATURA_TANQUE', 'Temperatura do tanque principal', 100, 'holding_register', 0.01, '°C'),
    ('PRESSAO_LINHA',      'Pressão da linha de processo',   101, 'holding_register', 0.01, 'bar'),
    ('SETPOINT_TEMPERATURA','Setpoint de temperatura',       110, 'holding_register', 0.01, '°C'),
    ('BOMBA_LIGADA',       'Estado da bomba principal',       0, 'coil',             1.0,  'bool'),
    ('ALARME_ATIVO',       'Alarme geral do sistema',         1, 'coil',             1.0,  'bool')
ON CONFLICT DO NOTHING;