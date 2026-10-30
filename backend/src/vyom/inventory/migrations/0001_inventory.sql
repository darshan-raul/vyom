-- R2.1: workspace-scoped inventory foundation.
--
-- Every table carries workspace_id, and every foreign key includes it. A row can therefore
-- only reference rows of its own workspace: cross-workspace links are refused by the
-- database itself, not only by query filters.

CREATE TABLE workspaces (
    id text PRIMARY KEY CHECK (id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$'),
    created_at timestamptz NOT NULL DEFAULT now()
);

-- An authorized connection to one provider target (today: one Kubernetes cluster).
-- cluster_uid is fixed for the life of the connection; the store refuses a change.
CREATE TABLE connections (
    workspace_id text NOT NULL REFERENCES workspaces (id),
    id text NOT NULL CHECK (id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$'),
    provider text NOT NULL CHECK (provider IN ('kubernetes')),
    cluster_uid text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, id)
);

-- One collection attempt and its outcome. The id is the evidence ID that answers cite.
-- Failed attempts are recorded too: they explain staleness without changing resources.
CREATE TABLE collection_runs (
    workspace_id text NOT NULL,
    id text NOT NULL,
    connection_id text NOT NULL,
    path text NOT NULL CHECK (path IN ('direct', 'mcp')),
    collector text,
    mcp jsonb,
    scope_kind text NOT NULL,
    scope_namespace text,  -- NULL would mean cluster-wide; no cluster-wide run exists yet
    collected_at timestamptz NOT NULL,
    state text NOT NULL CHECK (state IN ('complete', 'zero', 'partial', 'denied', 'missing')),
    coverage_complete boolean NOT NULL,
    returned integer NOT NULL CHECK (returned >= 0),
    truncated boolean NOT NULL,
    error_kinds text[] NOT NULL DEFAULT '{}',
    contract_version smallint NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, id),
    FOREIGN KEY (workspace_id, connection_id) REFERENCES connections (workspace_id, id),
    CHECK ((path = 'direct') = (collector IS NOT NULL))
);

-- Durable identity: one row per native object incarnation. A Pod deleted and recreated with
-- the same name has a new UID and therefore a new row; it never inherits the old row's
-- relationships or history. Names are lookup aliases only.
CREATE TABLE resources (
    workspace_id text NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    connection_id text NOT NULL,
    kind text NOT NULL,
    namespace text,
    name text NOT NULL,
    native_uid text NOT NULL,
    legacy_ref text NOT NULL,  -- the transient name-based item ID, for old citations
    attributes jsonb NOT NULL DEFAULT '{}',
    first_seen_at timestamptz NOT NULL,
    first_seen_run_id text NOT NULL,
    last_seen_at timestamptz NOT NULL,
    last_seen_run_id text NOT NULL,
    removed_at timestamptz,
    removed_run_id text,
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, connection_id, kind, native_uid),
    FOREIGN KEY (workspace_id, connection_id) REFERENCES connections (workspace_id, id),
    FOREIGN KEY (workspace_id, first_seen_run_id) REFERENCES collection_runs (workspace_id, id),
    FOREIGN KEY (workspace_id, last_seen_run_id) REFERENCES collection_runs (workspace_id, id),
    FOREIGN KEY (workspace_id, removed_run_id) REFERENCES collection_runs (workspace_id, id),
    CHECK ((removed_at IS NULL) = (removed_run_id IS NULL))
);
CREATE INDEX resources_lookup
    ON resources (workspace_id, connection_id, kind, namespace, name);
CREATE INDEX resources_legacy_ref ON resources (workspace_id, legacy_ref);

-- What one run saw of one item: the evidence an answer cites. Kept when the resource's
-- latest state changes. resource_id is NULL when the source gave no UID (an unresolved
-- reference): the observation stays citable but proves no durable identity.
CREATE TABLE observations (
    workspace_id text NOT NULL,
    run_id text NOT NULL,
    item_id text NOT NULL,
    resource_id uuid,
    kind text NOT NULL,
    namespace text,
    name text NOT NULL,
    native_uid text,
    observed_at timestamptz,  -- the source's own timestamp; NULL when it gave none
    attributes jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (workspace_id, run_id, item_id),
    FOREIGN KEY (workspace_id, run_id) REFERENCES collection_runs (workspace_id, id),
    FOREIGN KEY (workspace_id, resource_id) REFERENCES resources (workspace_id, id),
    CHECK ((resource_id IS NULL) = (native_uid IS NULL))
);
CREATE INDEX observations_resource ON observations (workspace_id, resource_id);

-- A directed edge between two resource incarnations, with the run that last verified it.
-- R3 records the first real edges (Deployment -> ReplicaSet -> Pod ownership).
CREATE TABLE relationships (
    workspace_id text NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL,
    target_id uuid NOT NULL,
    type text NOT NULL,
    first_seen_run_id text NOT NULL,
    last_verified_run_id text NOT NULL,
    last_verified_at timestamptz NOT NULL,
    removed_at timestamptz,
    removed_run_id text,
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, source_id, target_id, type),
    FOREIGN KEY (workspace_id, source_id) REFERENCES resources (workspace_id, id),
    FOREIGN KEY (workspace_id, target_id) REFERENCES resources (workspace_id, id),
    FOREIGN KEY (workspace_id, first_seen_run_id) REFERENCES collection_runs (workspace_id, id),
    FOREIGN KEY (workspace_id, last_verified_run_id)
        REFERENCES collection_runs (workspace_id, id),
    FOREIGN KEY (workspace_id, removed_run_id) REFERENCES collection_runs (workspace_id, id),
    CHECK (source_id <> target_id),
    CHECK ((removed_at IS NULL) = (removed_run_id IS NULL))
);
CREATE INDEX relationships_target ON relationships (workspace_id, target_id);
