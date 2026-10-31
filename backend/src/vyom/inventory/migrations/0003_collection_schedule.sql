-- R3.2: scheduled collection. Both tables describe the collector, not the resources: a
-- failing collector changes neither resources nor their health.

-- At most one worker sweeps a connection at a time. expires_at is computed on the database
-- clock, so workers with skewed clocks agree on when a lease has lapsed.
CREATE TABLE collection_leases (
    workspace_id text NOT NULL,
    connection_id text NOT NULL,
    holder text NOT NULL,
    acquired_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    PRIMARY KEY (workspace_id, connection_id),
    FOREIGN KEY (workspace_id, connection_id) REFERENCES connections (workspace_id, id),
    CHECK (expires_at > acquired_at)
);

-- The latest attempt and latest success per collected kind and namespace, and when the
-- kind is next due. Run IDs are not kept: runs are pruned, these rows are not.
CREATE TABLE collection_health (
    workspace_id text NOT NULL,
    connection_id text NOT NULL,
    kind text NOT NULL,
    namespace text NOT NULL,
    last_attempt_at timestamptz NOT NULL,
    last_state text NOT NULL
        CHECK (last_state IN ('complete', 'zero', 'partial', 'denied', 'missing')),
    last_error_kinds text[] NOT NULL DEFAULT '{}',
    last_success_at timestamptz,
    consecutive_failures integer NOT NULL CHECK (consecutive_failures >= 0),
    next_due_at timestamptz NOT NULL,
    PRIMARY KEY (workspace_id, connection_id, kind, namespace),
    FOREIGN KEY (workspace_id, connection_id) REFERENCES connections (workspace_id, id)
);
