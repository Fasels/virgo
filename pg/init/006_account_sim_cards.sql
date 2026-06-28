CREATE TABLE IF NOT EXISTS account_sim_cards (
    account_id  VARCHAR(64) NOT NULL
                REFERENCES accounts(id) ON DELETE CASCADE,
    sim_card_id VARCHAR(64) NOT NULL
                REFERENCES sim_cards(id) ON DELETE CASCADE,
    created_at  BIGINT NOT NULL DEFAULT ((EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::BIGINT),

    PRIMARY KEY (account_id, sim_card_id)
);

CREATE INDEX IF NOT EXISTS idx_account_sim_cards_sim_card
    ON account_sim_cards(sim_card_id);

INSERT INTO account_sim_cards (account_id, sim_card_id)
SELECT id, use_sims_id
FROM accounts
WHERE use_sims_id IS NOT NULL
ON CONFLICT (account_id, sim_card_id) DO NOTHING;
