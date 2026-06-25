-- 账号表。
CREATE TABLE accounts (
    id            VARCHAR(64) PRIMARY KEY,
    username      VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    areas         VARCHAR(100),
    use_sims_id   VARCHAR(64)
                  REFERENCES sim_cards(id) ON DELETE SET NULL,
    status        VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',

    CONSTRAINT chk_account_status
        CHECK (status IN ('ACTIVE', 'DISABLED'))
);

CREATE INDEX idx_accounts_areas ON accounts(areas);
CREATE INDEX idx_accounts_use_sims ON accounts(use_sims_id);
CREATE INDEX idx_accounts_status ON accounts(status);

-- 商品/客服提醒表。update_time 为 UTC Unix 毫秒。
CREATE TABLE products (
    id          VARCHAR(64) PRIMARY KEY,
    menu        TEXT,
    update_time BIGINT NOT NULL DEFAULT ((EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::BIGINT),
    update_by   VARCHAR(64)
                REFERENCES accounts(id) ON DELETE SET NULL,
    areas       VARCHAR(100)
);

CREATE INDEX idx_products_areas ON products(areas);
CREATE INDEX idx_products_update_time ON products(update_time DESC);
