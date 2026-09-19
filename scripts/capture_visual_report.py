"""Export the report's share card with optional Playwright (no inference calls).

uv run --with playwright playwright install chromium
uv run --with playwright python scripts/capture_visual_report.py
"""

from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    source = ROOT / "docs/report/index.html"
    if not source.is_file():
        raise SystemExit("Build the report first: uv run python scripts/build_visual_report.py")
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(
            headless=True, executable_path=os.environ.get("REPORT_CHROMIUM_PATH") or None
        )
        try:
            page = browser.new_page(viewport={"width": 1200, "height": 1000}, device_scale_factor=1)
            page.goto(source.as_uri() + "?share=1")
            page.wait_for_function("window.reportReady === true")
            page.evaluate("document.fonts.ready")
            page.locator("#share-card").screenshot(path=str(ROOT / "docs/report/summary.png"))
        finally:
            browser.close()
    print("Saved docs/report/summary.png from the recorded-results report.")


if __name__ == "__main__":
    main()
