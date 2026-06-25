ALTER TABLE messages DROP CONSTRAINT IF EXISTS chk_message_content;

ALTER TABLE messages ADD CONSTRAINT chk_message_content CHECK (
    (
        message_type = 'SMS'
        AND text_content IS NOT NULL
        AND data_base64 IS NULL
        AND data_port IS NULL
    )
    OR
    (
        message_type = 'DATA_SMS'
        AND text_content IS NULL
        AND data_base64 IS NOT NULL
        AND (direction = 'INBOUND' OR data_port IS NOT NULL)
    )
);
