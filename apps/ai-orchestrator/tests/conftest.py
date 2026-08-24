"""Shared test helpers (Milestone 4.8). `mock_prompt_registry_route`
gives orchestration-layer tests a single respx route standing in for
`resolve_active_prompt`'s live GET, without every test file having to
duplicate the same PostgREST-filter-parsing logic."""
from __future__ import annotations

import httpx
import respx


def mock_prompt_registry_route(supabase_url: str) -> "respx.Route":
    """Registers a GET /rest/v1/prompt_registry route that echoes back
    exactly one active v1 row for whatever `prompt_name` was requested --
    deterministic and agent-agnostic, so a test never needs to know the
    full agent roster in advance. FakeModelAdapter ignores prompt content
    entirely, so this text is never asserted against by orchestration
    tests -- only by the dedicated prompt-provenance tests, which query
    a per-agent route directly instead of this catch-all."""

    def _respond(request: httpx.Request) -> httpx.Response:
        raw = request.url.params.get("prompt_name", "")
        prompt_name = raw[len("eq.") :] if raw.startswith("eq.") else raw
        return httpx.Response(
            200,
            json=[{"prompt_name": prompt_name, "version": 1, "prompt_text": f"You are the {prompt_name}. TEST PROMPT."}],
        )

    return respx.get(f"{supabase_url}/rest/v1/prompt_registry").mock(side_effect=_respond)
