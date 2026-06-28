ALTER TABLE devices
    ADD COLUMN IF NOT EXISTS unregistered_at BIGINT;

ALTER TABLE sim_cards
    ADD COLUMN IF NOT EXISTS unregistered_at BIGINT;
