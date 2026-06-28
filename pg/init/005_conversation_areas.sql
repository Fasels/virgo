ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS areas VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_conversations_areas ON conversations(areas);
