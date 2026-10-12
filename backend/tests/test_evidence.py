from datetime import UTC, datetime, timedelta

from mcp_fixture import CONTEXT

from vyom.evidence import ErrorKind, ItemDraft, State, build_evidence

POD = ItemDraft(kind="Pod", namespace="demo", name="web-1", attributes={"phase": "Running"})


def test_missing_partial_stale_denied_and_zero_are_distinct_states():
    def state(**kwargs):
        return build_evidence(context=CONTEXT, path="direct", **kwargs).state

    assert state(drafts=[POD]) is State.COMPLETE
    assert state() is State.ZERO
    assert state(drafts=[POD], complete=False) is State.PARTIAL
    assert state(drafts=[POD, POD], max_items=1) is State.PARTIAL
    assert state(errors=[ErrorKind.FORBIDDEN]) is State.DENIED
    assert state(errors=[ErrorKind.UNAVAILABLE]) is State.MISSING

    collected = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
    old = build_evidence(context=CONTEXT, path="direct", drafts=[POD], collected_at=collected)
    later = collected + timedelta(minutes=10)
    assert old.state_at(later, max_age=timedelta(minutes=5)) is State.STALE
    assert old.state_at(later, max_age=timedelta(minutes=15)) is State.COMPLETE
    # Age never turns a failure into something that looks like an old answer.
    failed = build_evidence(context=CONTEXT, path="direct", errors=[ErrorKind.TIMEOUT])
    assert failed.state_at(later + timedelta(days=1), max_age=timedelta(minutes=5)) is State.MISSING


def test_a_failed_collection_is_never_reported_as_zero():
    evidence = build_evidence(context=CONTEXT, path="direct", errors=[ErrorKind.TIMEOUT])

    assert evidence.state is State.MISSING
    assert evidence.coverage.complete is False
    assert [error.kind for error in evidence.errors] == [ErrorKind.TIMEOUT]


def test_resources_outside_the_trusted_namespace_are_discarded_not_returned():
    stray = ItemDraft(kind="Pod", namespace="kube-system", name="etcd-0")

    evidence = build_evidence(context=CONTEXT, path="direct", drafts=[POD, stray])

    assert evidence.state is State.DENIED
    assert evidence.items == ()
    assert [error.kind for error in evidence.errors] == [ErrorKind.SCOPE_VIOLATION]


def test_source_timestamp_is_absent_unless_the_source_supplied_one():
    evidence = build_evidence(context=CONTEXT, path="direct", drafts=[POD])

    assert evidence.items[0].observed_at is None
    assert evidence.collected_at.tzinfo is UTC
