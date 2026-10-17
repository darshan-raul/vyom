# datetime/timedelta build dates and durations for the staleness checks.
from datetime import UTC, datetime, timedelta

# Shared test data (a fake trusted context) from tests/mcp_fixture.py.
from mcp_fixture import CONTEXT

from vyom.evidence import ErrorKind, ItemDraft, State, build_evidence

# One sample pod reused by the tests below.
POD = ItemDraft(kind="Pod", namespace="demo", name="web-1", attributes={"phase": "Running"})


# Each state means something different, so each input must lead to its own state.
def test_missing_partial_stale_denied_and_zero_are_distinct_states():
    # A helper defined inside the test. ``**kwargs`` collects any named arguments into a dict
    # and passes them on, so each assert only states what differs.
    def state(**kwargs):
        return build_evidence(context=CONTEXT, path="direct", **kwargs).state

    # ``is`` checks the exact same object, the normal way to compare enum members.
    assert state(drafts=[POD]) is State.COMPLETE
    assert state() is State.ZERO
    assert state(drafts=[POD], complete=False) is State.PARTIAL
    assert state(drafts=[POD, POD], max_items=1) is State.PARTIAL
    assert state(errors=[ErrorKind.FORBIDDEN]) is State.DENIED
    assert state(errors=[ErrorKind.UNAVAILABLE]) is State.MISSING

    # Fixed dates make the age maths exact. tzinfo=UTC marks it as a timezone-aware time.
    collected = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
    old = build_evidence(context=CONTEXT, path="direct", drafts=[POD], collected_at=collected)
    later = collected + timedelta(minutes=10)
    assert old.state_at(later, max_age=timedelta(minutes=5)) is State.STALE
    assert old.state_at(later, max_age=timedelta(minutes=15)) is State.COMPLETE
    # Age never turns a failure into something that looks like an old answer.
    failed = build_evidence(context=CONTEXT, path="direct", errors=[ErrorKind.TIMEOUT])
    assert failed.state_at(later + timedelta(days=1), max_age=timedelta(minutes=5)) is State.MISSING


# A failure must never look like "zero results".
def test_a_failed_collection_is_never_reported_as_zero():
    evidence = build_evidence(context=CONTEXT, path="direct", errors=[ErrorKind.TIMEOUT])

    assert evidence.state is State.MISSING
    assert evidence.coverage.complete is False
    assert [error.kind for error in evidence.errors] == [ErrorKind.TIMEOUT]


# An item from another namespace is a scope violation: nothing is returned.
def test_resources_outside_the_trusted_namespace_are_discarded_not_returned():
    # "stray": a pod from kube-system, outside the allowed namespace.
    stray = ItemDraft(kind="Pod", namespace="kube-system", name="etcd-0")

    evidence = build_evidence(context=CONTEXT, path="direct", drafts=[POD, stray])

    assert evidence.state is State.DENIED
    assert evidence.items == ()
    assert [error.kind for error in evidence.errors] == [ErrorKind.SCOPE_VIOLATION]


# observed_at stays None unless the source gave a time; collected_at is always UTC.
def test_source_timestamp_is_absent_unless_the_source_supplied_one():
    evidence = build_evidence(context=CONTEXT, path="direct", drafts=[POD])

    assert evidence.items[0].observed_at is None
    assert evidence.collected_at.tzinfo is UTC
