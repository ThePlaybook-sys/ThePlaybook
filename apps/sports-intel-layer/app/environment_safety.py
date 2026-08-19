"""Demo/production database isolation guard (DEMO-1, 2026-08-19).

Structural enforcement for Rule 2/Rule 3 of `docs/blueprint/demo-simulation-environment.md`:
a `demo`-tagged deployment must never be able to reach dev/staging/production data, and a
non-`demo` deployment must never be able to reach the isolated demo project. This is checked
once, at process startup (see `app/main.py`), and is a hard failure -- never a warning that lets
the process continue -- because a silent continue here is exactly the failure mode Rule 2 exists
to prevent.

This module only ever compares `SUPABASE_URL` against the demo project's own ref. It does not
(and must not) hold or compare any dev/staging/production project ref or credential -- there is
nothing here for a misconfigured demo deployment to leak.
"""
from __future__ import annotations

#: The isolated `theplaybook-demo` Supabase project's ref (DEMO-1, provisioned 2026-08-19).
#: Not a secret -- a project ref is not a credential, it's an identifier embedded in the
#: project's own public URL (https://<ref>.supabase.co).
DEMO_SUPABASE_PROJECT_REF = "tbxzecbopoxcexggesmk"

#: The Railway environment name that identifies a demo deployment. Matches the existing
#: `RAILWAY_ENVIRONMENT_NAME`-based branching already in `app/main.py` (Sentry tagging, the
#: dev-only `/sentry-debug` route) -- extending that same pattern to a fourth value, not a new
#: mechanism.
DEMO_ENVIRONMENT_NAME = "demo"


class DemoIsolationError(RuntimeError):
    """Raised when a deployment's environment tag and database target disagree about
    whether this is the isolated demo environment. Always fatal -- callers must let this
    propagate and crash startup, never catch-and-continue."""


def assert_demo_isolation(railway_environment_name: str, supabase_url: str) -> None:
    """Hard-fail if a `demo`-tagged process is not pointed at the demo project, or if a
    non-`demo`-tagged process IS pointed at the demo project. No warn-and-continue path.
    """
    is_demo_env = railway_environment_name == DEMO_ENVIRONMENT_NAME
    points_at_demo_db = DEMO_SUPABASE_PROJECT_REF in (supabase_url or "")

    if is_demo_env and not points_at_demo_db:
        raise DemoIsolationError(
            f"RAILWAY_ENVIRONMENT_NAME={DEMO_ENVIRONMENT_NAME!r} but SUPABASE_URL does not "
            f"point at the isolated demo project ({DEMO_SUPABASE_PROJECT_REF!r}). Refusing to "
            "start: a demo deployment must never be able to reach a non-demo database."
        )

    if not is_demo_env and points_at_demo_db:
        raise DemoIsolationError(
            f"RAILWAY_ENVIRONMENT_NAME={railway_environment_name!r} (not "
            f"{DEMO_ENVIRONMENT_NAME!r}) but SUPABASE_URL points at the isolated demo project "
            f"({DEMO_SUPABASE_PROJECT_REF!r}). Refusing to start: a non-demo deployment must "
            "never be able to reach demo data."
        )
