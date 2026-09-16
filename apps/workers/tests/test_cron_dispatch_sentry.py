"""Sentry coverage for the cron entry point (2026-09-16, "CRON SENTRY +
ODDS API BUDGET ARMING").

The 2026-09-16 coverage audit found that nine cron services -- the entire
schedule -> odds -> recommendation -> grading pipeline -- reported nothing to
Sentry, because `apps/workers/app/main.py` initializes the SDK but the crons
run `python -m app.cron_dispatch`, a different entry point in the same image.
Three of them had been crashing silently for hours.

These tests pin both halves of the fix:

  * the four failure classes that MUST reach Sentry (unhandled exception,
    transport failure, invalid configuration, non-2xx response), plus the
    structured `status="failed"` payload that no HTTP status code can see;
  * the five normal-operation outcomes that must NEVER raise an event, so
    the alert stays worth reading.

No network, no Sentry transport: `sentry_sdk` is patched at the module
boundary, so these assert what the dispatcher *decides to report*, which is
the behaviour under test.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app import cron_dispatch
from app.cron_dispatch import CronDispatchError, result_failure_summary

BASE_URL = "https://worker-scheduled.test"


class _FakeScope:
    def __init__(self):
        self.level = None
        self.contexts = {}

    def set_level(self, level):
        self.level = level

    def set_context(self, key, value):
        self.contexts[key] = value

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeSentry:
    """Records what the dispatcher asked Sentry to do."""

    def __init__(self):
        self.init_kwargs = None
        self.tags = {}
        self.exceptions = []
        self.messages = []
        self.flushes = 0
        self.scope = _FakeScope()

    def init(self, **kwargs):
        self.init_kwargs = kwargs

    def set_tag(self, key, value):
        self.tags[key] = value

    def capture_exception(self, exc):
        self.exceptions.append(exc)

    def capture_message(self, message):
        self.messages.append(message)

    def new_scope(self):
        return self.scope

    def flush(self, timeout=None):
        self.flushes += 1


@pytest.fixture
def sentry(monkeypatch):
    fake = _FakeSentry()
    monkeypatch.setattr(cron_dispatch, "sentry_sdk", fake)
    return fake


def _env(monkeypatch, **overrides):
    values = {
        "CRON_DISPATCH_TARGET": "odds-worker",
        "CRON_DISPATCH_BASE_URL": BASE_URL,
        "INTERNAL_SERVICE_TOKEN": "secret",
        "RAILWAY_SERVICE_NAME": "cron-odds-worker",
        "RAILWAY_ENVIRONMENT_NAME": "dev",
    }
    values.update(overrides)
    for key in (
        "CRON_DISPATCH_TARGET",
        "CRON_DISPATCH_BASE_URL",
        "INTERNAL_SERVICE_TOKEN",
        "RAILWAY_SERVICE_NAME",
        "RAILWAY_ENVIRONMENT_NAME",
        "SENTRY_DSN",
        "RAILWAY_GIT_COMMIT_SHA",
        "RAILWAY_DEPLOYMENT_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        if value is not None:
            monkeypatch.setenv(key, value)


# ===========================================================================
# Initialization, identity tags, and flush
# ===========================================================================


def test_init_sets_environment_and_identity_tags(sentry, monkeypatch):
    """The audit's §6 finding: four services shared one Sentry project with
    no way to tell them apart. A service tag and a cron-target tag are what
    make a per-service or per-target alert rule possible at all."""
    _env(monkeypatch, RAILWAY_SERVICE_NAME="cron-schedule-refresh", CRON_DISPATCH_TARGET="schedule-refresh")
    monkeypatch.setenv("SENTRY_DSN", "https://key@example.ingest.sentry.io/1")

    cron_dispatch._init_sentry()

    assert sentry.init_kwargs["environment"] == "dev"
    assert sentry.init_kwargs["send_default_pii"] is False
    assert sentry.tags["service"] == "cron-schedule-refresh"
    assert sentry.tags["cron_target"] == "schedule-refresh"


def test_release_prefers_commit_then_deployment_then_none(sentry, monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc123")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "deploy-9")
    cron_dispatch._init_sentry()
    assert sentry.init_kwargs["release"] == "abc123"

    _env(monkeypatch)
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "deploy-9")
    cron_dispatch._init_sentry()
    assert sentry.init_kwargs["release"] == "deploy-9"

    # Neither available: no release, never a fabricated one.
    _env(monkeypatch)
    cron_dispatch._init_sentry()
    assert sentry.init_kwargs["release"] is None


def test_a_missing_dsn_disables_sentry_rather_than_failing_the_job(sentry, monkeypatch):
    """Telemetry must never be the reason a scheduled job fails to run."""
    _env(monkeypatch)  # no SENTRY_DSN
    cron_dispatch._init_sentry()
    assert sentry.init_kwargs["dsn"] is None


@respx.mock
def test_events_are_flushed_before_the_process_exits(sentry, monkeypatch):
    """Sentry's transport is background-threaded. For a finite job that calls
    sys.exit seconds later, an unflushed event is a lost event."""
    _env(monkeypatch)
    respx.post(f"{BASE_URL}/v1/internal/odds-worker/run").mock(
        return_value=httpx.Response(200, json={"status": "success"})
    )
    with pytest.raises(SystemExit) as exit_info:
        cron_dispatch.main()
    assert exit_info.value.code == 0
    assert sentry.flushes == 1


# ===========================================================================
# The four failure classes that MUST be captured
# ===========================================================================


@respx.mock
def test_transport_failure_is_captured(sentry, monkeypatch):
    """The exact shape that had cron-weather-worker crashing every 15 minutes
    unseen: a malformed base URL raising before any response exists."""
    _env(monkeypatch)
    respx.post(f"{BASE_URL}/v1/internal/odds-worker/run").mock(
        side_effect=httpx.ConnectError("no route to host")
    )
    with pytest.raises(SystemExit) as exit_info:
        cron_dispatch.main()

    assert exit_info.value.code == 1
    assert len(sentry.exceptions) == 1
    assert isinstance(sentry.exceptions[0], CronDispatchError)
    assert "transport failure" in str(sentry.exceptions[0])
    assert sentry.flushes == 1


@respx.mock
def test_non_2xx_internal_response_is_captured(sentry, monkeypatch):
    _env(monkeypatch)
    respx.post(f"{BASE_URL}/v1/internal/odds-worker/run").mock(
        return_value=httpx.Response(500, text="internal explosion")
    )
    with pytest.raises(SystemExit) as exit_info:
        cron_dispatch.main()

    assert exit_info.value.code == 1
    assert len(sentry.exceptions) == 1
    assert "returned 500" in str(sentry.exceptions[0])


def test_invalid_configuration_is_captured(sentry, monkeypatch):
    """A missing required variable dies at module entry -- one of the three
    pre-init windows the audit named. Captured explicitly, because the job
    exits immediately afterwards."""
    _env(monkeypatch)
    monkeypatch.delenv("CRON_DISPATCH_BASE_URL")

    with pytest.raises(SystemExit) as exit_info:
        cron_dispatch.main()

    assert exit_info.value.code == 1
    assert len(sentry.exceptions) == 1
    assert isinstance(sentry.exceptions[0], KeyError)
    assert sentry.flushes == 1


@respx.mock
def test_an_unknown_target_is_captured_as_invalid_configuration(sentry, monkeypatch):
    _env(monkeypatch, CRON_DISPATCH_TARGET="not-a-real-target")
    with pytest.raises(SystemExit) as exit_info:
        cron_dispatch.main()

    assert exit_info.value.code == 1
    assert "unknown CRON_DISPATCH_TARGET" in str(sentry.exceptions[0])


@respx.mock
def test_an_unexpected_exception_is_captured_not_left_as_a_bare_traceback(sentry, monkeypatch):
    _env(monkeypatch)
    respx.post(f"{BASE_URL}/v1/internal/odds-worker/run").mock(
        side_effect=RuntimeError("something nobody predicted")
    )
    with pytest.raises(SystemExit) as exit_info:
        cron_dispatch.main()

    assert exit_info.value.code == 1
    assert isinstance(sentry.exceptions[0], RuntimeError)
    assert sentry.flushes == 1


# ===========================================================================
# Structured worker failures -- what no HTTP status code can see
# ===========================================================================


@respx.mock
def test_structured_status_failed_in_a_200_is_captured(sentry, monkeypatch):
    """The gap that let the odds credit leak run unnoticed: workers here are
    deliberately written never to raise, so a total failure arrives as a
    field inside a 200 OK."""
    _env(monkeypatch)
    respx.post(f"{BASE_URL}/v1/internal/odds-worker/run").mock(
        return_value=httpx.Response(
            200, json={"status": "failed", "error": "credit guard read failed: boom", "failures": []}
        )
    )
    with pytest.raises(SystemExit) as exit_info:
        cron_dispatch.main()

    assert len(sentry.messages) == 1
    assert "status=failed" in sentry.messages[0]
    assert sentry.scope.level == "error"
    # The full payload rides along, so the issue is diagnosable from Sentry alone.
    assert sentry.scope.contexts["worker_result"]["error"] == "credit guard read failed: boom"
    # Exit 0: the dispatch worked and the worker answered. Marking the
    # deployment CRASHED would conflate two different conditions.
    assert exit_info.value.code == 0
    assert sentry.flushes == 1


@respx.mock
def test_partial_with_failures_is_reported_at_warning_not_error(sentry, monkeypatch):
    """Twelve consecutive `partial` cycles were the shape of the credit leak.
    HQ's directive named neither side of this case, so it is reported at a
    lower severity rather than silently dropped."""
    _env(monkeypatch)
    respx.post(f"{BASE_URL}/v1/internal/odds-worker/run").mock(
        return_value=httpx.Response(
            200,
            json={"status": "partial", "failures": ["poll state update failed for abc: boom"]},
        )
    )
    with pytest.raises(SystemExit) as exit_info:
        cron_dispatch.main()

    assert len(sentry.messages) == 1
    assert sentry.scope.level == "warning"
    assert exit_info.value.code == 0


# ===========================================================================
# Normal operation -- must NEVER raise an event
# ===========================================================================


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"status": "success"}, id="successful_processing"),
        pytest.param({"status": "success", "games_considered": 0}, id="successful_empty"),
        pytest.param({"status": "paused", "run_id": None}, id="paused_gate"),
        pytest.param({"status": "disabled"}, id="disabled"),
        pytest.param({"status": "no_eligible_run", "games": []}, id="nothing_eligible"),
        pytest.param({"status": "completed", "game_ids": []}, id="completed"),
        pytest.param({"status": "skipped_credit_guard", "games_due": 3}, id="monthly_credit_guard"),
        pytest.param({"status": "skipped_daily_budget", "games_due": 3}, id="daily_budget_pause"),
        pytest.param({"status": "success", "failures": []}, id="empty_failures_list"),
    ],
)
@respx.mock
def test_normal_operation_never_raises_a_sentry_event(sentry, monkeypatch, payload):
    """A cron that correctly does nothing is not an error. Treating it as one
    would train the alert to be ignored, which costs more than having no
    alert at all."""
    _env(monkeypatch)
    respx.post(f"{BASE_URL}/v1/internal/odds-worker/run").mock(
        return_value=httpx.Response(200, json=payload)
    )
    with pytest.raises(SystemExit) as exit_info:
        cron_dispatch.main()

    assert exit_info.value.code == 0
    assert sentry.messages == []
    assert sentry.exceptions == []


def test_budget_and_guard_pauses_are_classified_as_normal_not_failure():
    """Pinned directly on the classifier too, because these two are the ones
    a future edit is most likely to get wrong: both mean 'the guard worked'."""
    assert result_failure_summary({"status": "skipped_daily_budget"}) is None
    assert result_failure_summary({"status": "skipped_credit_guard"}) is None
    assert result_failure_summary({"status": "paused"}) is None
    assert result_failure_summary({"status": "success"}) is None


def test_classifier_reports_failed_and_partial_with_failures():
    failed = result_failure_summary({"status": "failed", "error": "boom"})
    assert failed is not None and failed[0] == "error"

    partial = result_failure_summary({"status": "partial", "failures": ["x"]})
    assert partial is not None and partial[0] == "warning"

    # An unknown status with NO failures is not assumed broken.
    assert result_failure_summary({"status": "something_new"}) is None
