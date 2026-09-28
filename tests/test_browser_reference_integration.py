"""Real Chromium reference actions, including labels copied from content."""
from pathlib import Path

import pytest


@pytest.mark.parametrize("reference", ["button 1", "[button 1]", "1"])
def test_real_browser_content_label_clicks_exact_element_once(reference):
    patchright = pytest.importorskip("patchright.sync_api")
    assets = Path(__file__).resolve().parents[1] / "plugins/_browser/assets"
    with patchright.sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            pytest.skip("Patchright Chromium runtime is unavailable")
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content("""<button onclick="document.body.dataset.clicks=String(
                Number(document.body.dataset.clicks||0)+1)">Choose source</button>""")
            for name in ("browser-dom-helper.js", "browser-page-content.js"):
                page.evaluate((assets / name).read_text(encoding="utf-8"), isolated_context=True)
            content = page.evaluate("() => globalThis.__spaceBrowserPageContent__.capture()",
                                    isolated_context=True)
            assert "[button 1]" in content["document"]
            page.evaluate("ref => globalThis.__spaceBrowserPageContent__.click(ref)",
                          reference, isolated_context=True)
            assert page.locator("body").get_attribute("data-clicks") == "1"
        finally:
            browser.close()
