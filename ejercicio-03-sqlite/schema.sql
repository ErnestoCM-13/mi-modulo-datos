-- Tabla principal de transacciones
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT    PRIMARY KEY,
    timestamp      TEXT    NOT NULL,
    user_id        INTEGER NOT NULL,
    merchant_id    INTEGER NOT NULL,
    amount         REAL    NOT NULL,
    category       TEXT    NOT NULL,
    country_code   TEXT    NOT NULL,
    status         TEXT    NOT NULL
);

-- Índice compuesto para P2, P3 y P4
CREATE INDEX idx_user_timestamp ON transactions(user_id, timestamp);

-- Índice compuesto para P5
CREATE INDEX idx_country_user ON transactions(country_code, user_id);
