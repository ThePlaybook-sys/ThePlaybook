"""DEMO-1 isolation-guard tests (docs/blueprint/demo-simulation-environment.md
Rule 2/Rule 3). Proves `assert_demo_isolation` hard-fails in both directions and
never warns-and-continues, per Mac's explicit "no warn and continue" instruction.
"""
import inspect

import pytest

from app import main as main_module
from app.environment_safety import (
    DEMO_SUPABASE_PROJECT_REF,
    DemoIsolationError,
    assert_demo_isolation,
)

# The four Supabase projects' own refs (not secrets -- each is embedded in that
# project's own public https://<ref>.supabase.co URL). dev/staging/production
# refs confirmed via direct Supabase inspection this session; demo is the one
# provisioned in DEMO-1.
DEV_URL = "https://nhwjtsdebgiwskshzqiq.supabase.co"
STAGING_URL = "https://jhpjdjtvzzmhxvprsfaq.supabase.co"
PRODUCTION_URL = "https://dronhltumzkngwwktesf.supabase.co"
DEMO_URL = f"https://{DEMO_SUPABASE_PROJECT_REF}.supabase.co"


def test_demo_environment_with_demo_url_is_allowed():
    assert_demo_isolation(railway_environment_name="demo", supabase_url=DEMO_URL)


@pytest.mark.parametrize("wrong_url", [DEV_URL, STAGING_URL, PRODUCTION_URL, ""])
def test_demo_environment_pointed_at_anything_else_hard_fails(wrong_url):
    with pytest.raises(DemoIsolationError):
        assert_demo_isolation(railway_environment_name="demo", supabase_url=wrong_url)


@pytest.mark.parametrize("real_env_name", ["dev", "staging", "production"])
def test_real_environment_pointed_at_demo_url_hard_fails(real_env_name):
    with pytest.raises(DemoIsolationError):
        assert_demo_isolation(railway_environment_name=real_env_name, supabase_url=DEMO_URL)


@pytest.mark.parametrize(
    ("env_name", "url"),
    [("dev", DEV_URL), ("staging", STAGING_URL), ("production", PRODUCTION_URL), ("dev", "")],
)
def test_real_environment_pointed_at_its_own_or_no_url_is_allowed(env_name, url):
    assert_demo_isolation(railway_environment_name=env_name, supabase_url=url)


def test_the_four_project_urls_are_pairwise_distinct():
    urls = [DEV_URL, STAGING_URL, PRODUCTION_URL, DEMO_URL]
    assert len(urls) == len(set(urls))


def test_main_module_calls_the_isolation_guard_before_app_construction():
    # Confirms the wiring, not just the guard function in isolation: main.py's
    # own source must call assert_demo_isolation before constructing the
    # FastAPI app, so a violation prevents the app from ever existing.
    source = inspect.getsource(main_module)
    guard_call_pos = source.index("assert_demo_isolation(")
    app_construction_pos = source.index("FastAPI(")
    assert guard_call_pos < app_construction_pos


def test_main_module_reads_no_provider_or_service_role_credential_by_name():
    # DEMO-1 sets no provider keys and no SUPABASE_SERVICE_ROLE_KEY on the demo
    # environment (Decision 6/Decision on credentials) -- main.py's own startup
    # path must not reference any of them by name, so there's nothing for a
    # misconfigured demo deploy to leak even if one were later set by mistake.
    source = inspect.getsource(main_module)
    forbidden_names = [
        "SPORTSDATAIO_API_KEY",
        "SPORTSDATAIO_DIAGNOSTIC_TOKEN",
        "THE_ODDS_API_KEY",
        "WEATHERAPI_API_KEY",
        "NEWSAPI_API_KEY",
        "GNEWS_API_KEY",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "SUPABASE_SERVICE_ROLE_KEY",
    ]
    for name in forbidden_names:
        assert name not in source
