-- Schema for promotion history.
-- Optional: history is mirrored in config/param_history.yaml so a human can
-- diff it in version control. The sqlite copy is convenient for queries.

CREATE TABLE IF NOT EXISTS sfa_promotions (
    history_entry_id TEXT PRIMARY KEY,
    strategy_name TEXT NOT NULL,
    walkforward_id TEXT,
    from_params_json TEXT NOT NULL,
    to_params_json TEXT NOT NULL,
    diff_json TEXT NOT NULL,
    gate_json TEXT NOT NULL,
    git_commit TEXT,
    promoted_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sfa_promotions_strategy ON sfa_promotions(strategy_name);
