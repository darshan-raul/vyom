-- R3.1: the controller each observation reported, so a cited Pod or ReplicaSet shows which
-- object controlled it at that time. The current edge lives in relationships; these columns
-- are the evidence for it and are kept when the edge later changes. All three are set or
-- none: a path that cannot see owner references (MCP) stores none.

ALTER TABLE observations
    ADD COLUMN owner_kind text,
    ADD COLUMN owner_name text,
    ADD COLUMN owner_uid text,
    ADD CONSTRAINT observations_owner_complete CHECK (
        (owner_kind IS NULL) = (owner_name IS NULL)
        AND (owner_kind IS NULL) = (owner_uid IS NULL)
    );
