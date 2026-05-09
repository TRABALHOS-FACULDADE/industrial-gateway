CREATE TABLE IF NOT EXISTS leds (
    id          INTEGER         PRIMARY KEY,        -- ID do LED (0 a 7)
    toggled     BOOLEAN         NOT NULL DEFAULT FALSE, -- TRUE = aceso
    updated_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()  -- Última atualização
);

INSERT INTO leds (id, toggled) VALUES
    (0, FALSE),
    (1, FALSE),
    (2, FALSE),
    (3, FALSE),
    (4, FALSE),
    (5, FALSE),
    (6, FALSE),
    (7, FALSE)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS led_events (
    id               BIGSERIAL       PRIMARY KEY,
    led_id           INTEGER         NOT NULL REFERENCES leds(id),
    toggled          BOOLEAN         NOT NULL,
    confirmed_by_plc BOOLEAN         NOT NULL DEFAULT FALSE,
    error            TEXT,
    occurred_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_led_events_led_time
    ON led_events (led_id, occurred_at DESC);