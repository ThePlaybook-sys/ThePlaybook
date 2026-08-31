"""One-off diagnostic script for the Phase 6 Milestone 3 mandatory visual
review handoff (HQ-authorized, "M3 VISUAL REVIEW BLOCKER RESOLUTION").

Runs only inside the visual-review-handoff GitHub Actions workflow, which
has real internet access -- unlike the build sandbox, whose egress policy
explicitly denies both the Supabase and Railway hosts this needs (confirmed
via the agent-proxy's own status endpoint), mirroring the exact restriction
scripts/phase2_e2e_test.py already documented and worked around the same
way (run in Actions instead of the sandbox).

Never fabricates recommendation data. Every screenshot is either real DEV
data or an honestly-empty state -- the script queries the live API first
to find out what actually exists (a specific graded/withdrawn/no_bet/
bankroll_preservation/corrected/mixed_settled row, or none at all) rather
than assuming last-known DEV state still holds, and any state it can't
find a real row for is skipped and recorded as skipped, never faked.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

SUPABASE_URL = "https://nhwjtsdebgiwskshzqiq.supabase.co"
ANON_KEY = os.environ["DEV_ANON_KEY"]
API_GATEWAY_URL = "https://api-gateway-dev-005e.up.railway.app"
FRONTEND_URL = "https://frontend-dev-ab32.up.railway.app"
SEED_EMAIL = "seed-free-user@example.com"
SEED_PASSWORD = "seedpassword"

OUT_DIR = Path("visual-review-output")
OUT_DIR.mkdir(exist_ok=True)

DESKTOP = {"width": 1440, "height": 900}
MOBILE = {"width": 390, "height": 844}

manifest: list[dict] = []


def record(name: str, *, route: str, viewport: dict, authenticated: bool, data_state: str) -> None:
    manifest.append(
        {
            "file": name,
            "route": route,
            "viewport": f"{viewport['width']}x{viewport['height']}",
            "authenticated": authenticated,
            "data_state": data_state,  # "real" | "empty" | "unauthenticated"
        }
    )


def login() -> str:
    response = httpx.post(
        f"{SUPABASE_URL}/auth/v1/token",
        params={"grant_type": "password"},
        json={"email": SEED_EMAIL, "password": SEED_PASSWORD},
        headers={"apikey": ANON_KEY},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def analyze_recommendations(token: str) -> dict:
    """Queries the real feed once and classifies what special states (if
    any) genuinely exist right now -- never assumes an earlier snapshot
    still holds."""
    response = httpx.get(
        f"{API_GATEWAY_URL}/v1/recommendations",
        headers={"Authorization": f"Bearer {token}"},
        params={"limit": "200"},
        timeout=30.0,
    )
    response.raise_for_status()
    rows = response.json()

    by_state: dict[str, str | None] = {
        "no_bet": None,
        "bankroll_preservation": None,
        "withdrawn": None,
        "graded": None,
        "corrected": None,
        "mixed_settled": None,
    }
    for row in rows:
        if row["recommendationType"] == "no_bet" and by_state["no_bet"] is None:
            by_state["no_bet"] = row["displayId"]
        if row["recommendationType"] == "bankroll_preservation" and by_state["bankroll_preservation"] is None:
            by_state["bankroll_preservation"] = row["displayId"]
        if row["status"] == "withdrawn" and by_state["withdrawn"] is None:
            by_state["withdrawn"] = row["displayId"]
        grade = row.get("grade")
        if grade:
            if by_state["graded"] is None:
                by_state["graded"] = row["displayId"]
            if grade.get("isCorrection") and by_state["corrected"] is None:
                by_state["corrected"] = row["displayId"]
            if grade.get("outcome") == "MIXED_SETTLED" and by_state["mixed_settled"] is None:
                by_state["mixed_settled"] = row["displayId"]

    return {"rows": rows, "by_state": by_state, "first_display_id": rows[0]["displayId"] if rows else None}


def _cookie(token: str) -> dict:
    return {
        "name": "pb_session_token",
        "value": token,
        "domain": "frontend-dev-ab32.up.railway.app",
        "path": "/",
        "httpOnly": True,
        "secure": True,
    }


def _capture_detail(browser, token: str, display_id: str, *, file_prefix: str, data_state: str) -> None:
    """Layer 1 collapsed, then every native <details> disclosure expanded
    (Layers 3-4), desktop and mobile."""
    route = f"/recommendations/{display_id}"

    desktop_ctx = browser.new_context(viewport=DESKTOP)
    desktop_ctx.add_cookies([_cookie(token)])
    page = desktop_ctx.new_page()
    page.goto(f"{FRONTEND_URL}{route}", wait_until="networkidle")

    layer1_path = OUT_DIR / f"{file_prefix}-layer1-desktop.png"
    page.screenshot(path=str(layer1_path))
    record(layer1_path.name, route=route, viewport=DESKTOP, authenticated=True, data_state=data_state)

    summaries = page.locator("details summary")
    for i in range(summaries.count()):
        summaries.nth(i).click()
    page.wait_for_timeout(200)

    expanded_path = OUT_DIR / f"{file_prefix}-layers-2-3-4-expanded-desktop.png"
    page.screenshot(path=str(expanded_path), full_page=True)
    record(expanded_path.name, route=route, viewport=DESKTOP, authenticated=True, data_state=data_state)
    desktop_ctx.close()

    mobile_ctx = browser.new_context(viewport=MOBILE)
    mobile_ctx.add_cookies([_cookie(token)])
    page = mobile_ctx.new_page()
    page.goto(f"{FRONTEND_URL}{route}", wait_until="networkidle")
    mobile_path = OUT_DIR / f"{file_prefix}-mobile.png"
    page.screenshot(path=str(mobile_path), full_page=True)
    record(mobile_path.name, route=route, viewport=MOBILE, authenticated=True, data_state=data_state)
    mobile_ctx.close()


def main() -> None:
    token = login()
    print(f"Authenticated as {SEED_EMAIL}")

    analysis = analyze_recommendations(token)
    print(f"Live DEV feed: {len(analysis['rows'])} row(s). Special states found: {analysis['by_state']}")

    data_state = "real" if analysis["rows"] else "empty"

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # Unauthenticated -- fresh context, no cookie.
        anon_ctx = browser.new_context(viewport=DESKTOP)
        page = anon_ctx.new_page()
        page.goto(f"{FRONTEND_URL}/today", wait_until="networkidle")
        path = OUT_DIR / "01-today-unauthenticated-desktop.png"
        page.screenshot(path=str(path))
        record(path.name, route="/today", viewport=DESKTOP, authenticated=False, data_state="unauthenticated")
        anon_ctx.close()

        # Authenticated feed pages, desktop + mobile.
        for viewport, suffix in ((DESKTOP, "desktop"), (MOBILE, "mobile")):
            ctx = browser.new_context(viewport=viewport)
            ctx.add_cookies([_cookie(token)])
            page = ctx.new_page()
            for route, prefix in (("/today", "02-today"), ("/recommendations", "03-recommendations")):
                page.goto(f"{FRONTEND_URL}{route}", wait_until="networkidle")
                shot_path = OUT_DIR / f"{prefix}-{suffix}.png"
                page.screenshot(path=str(shot_path), full_page=True)
                record(shot_path.name, route=route, viewport=viewport, authenticated=True, data_state=data_state)
            ctx.close()

        # Detail page -- only if a real row exists. Never fabricated.
        if analysis["first_display_id"]:
            _capture_detail(browser, token, analysis["first_display_id"], file_prefix="04-detail", data_state="real")
        else:
            print("SKIPPED: detail-page screenshots -- no real recommendation_products row exists in DEV.")

        # Special states -- only the ones the live feed actually contains.
        state_prefix = {
            "no_bet": "05-no-bet",
            "bankroll_preservation": "06-bankroll-preservation",
            "withdrawn": "07-withdrawn",
            "graded": "08-graded",
            "corrected": "09-corrected",
            "mixed_settled": "10-mixed-settled",
        }
        for state, display_id in analysis["by_state"].items():
            if display_id and display_id != analysis["first_display_id"]:
                _capture_detail(browser, token, display_id, file_prefix=state_prefix[state], data_state="real")
            elif not display_id:
                print(f"SKIPPED: {state} state -- no real row with this state exists in DEV.")

        browser.close()

    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "feedRowCount": len(analysis["rows"]),
                "specialStatesFound": analysis["by_state"],
                "screenshots": manifest,
            },
            indent=2,
        )
    )
    print(f"Wrote {len(manifest)} screenshots + manifest to {OUT_DIR}/")


if __name__ == "__main__":
    main()
