CREATE TABLE history (
    trace_id    UUID      NOT NULL,
    session_id  UUID      NOT NULL,
    question    TEXT      NOT NULL,
    answer      TEXT      NOT NULL,
    "user"            VARCHAR(255),
    input_tokens  INTEGER,
    output_tokens INTEGER,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    retrieved_contexts text,
    -- Feedback humano (06_agent_llmops_obs): NULL = sin feedback,
    -- TRUE = 👍, FALSE = 👎. El trace_id es también el run_id del trace en LangSmith.
    is_ok             BOOLEAN,
    feedback_comment  TEXT,
    feedback_at       TIMESTAMP,
    CONSTRAINT pk_history PRIMARY KEY (trace_id)
);
CREATE INDEX ix_history_session_id ON history (session_id);

-- Migración para una tabla history ya creada (labs 01-05).
-- Las columnas son NULL, así que no afectan a los labs anteriores.
ALTER TABLE history ADD COLUMN IF NOT EXISTS is_ok BOOLEAN;
ALTER TABLE history ADD COLUMN IF NOT EXISTS feedback_comment TEXT;
ALTER TABLE history ADD COLUMN IF NOT EXISTS feedback_at TIMESTAMP;
