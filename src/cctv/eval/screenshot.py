"""Headless UI capture for one evaluation answer.

The page asks the question itself, so this is a second live turn. It needs the
API and UI running (``make up``).
"""

from __future__ import annotations

from pathlib import Path

UI_URL = "http://127.0.0.1:5173"
_ANSWER_TIMEOUT_MS = 20 * 60 * 1000
_CHOICE_LABELS = {
    "default": "Default",
    "none": "None",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "xhigh": "Extra high",
    "max": "Max",
}


class ScreenshotError(RuntimeError):
    pass


def capture_chat_screenshot(
    *,
    question: str,
    model_label: str,
    verbosity: str | None,
    path: Path,
    ui_url: str = UI_URL,
) -> None:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ScreenshotError(
            "Playwright is not installed. Run `uv sync --group dev` and "
            "`uv run playwright install chromium`."
        ) from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            try:
                page.goto(ui_url, wait_until="domcontentloaded", timeout=30_000)
                composer = page.get_by_placeholder("Ask about the cameras")
                composer.wait_for(state="visible", timeout=30_000)
                _select_combobox(page, "Model", model_label)
                if verbosity is not None:
                    _select_combobox(page, "Verbosity", _CHOICE_LABELS.get(verbosity, verbosity))
                page.get_by_role("button", name="New chat").click()
                composer.fill(question)
                page.get_by_role("button", name="Send").click()
                progress = page.get_by_role("progressbar")
                progress.wait_for(state="visible", timeout=30_000)
                progress.wait_for(state="hidden", timeout=_ANSWER_TIMEOUT_MS)
                page.wait_for_function(
                    "() => [...document.images].every((img) => img.complete)",
                    timeout=30_000,
                )
                _scroll_transcript(page)
                page.screenshot(path=str(path))
            finally:
                browser.close()
    except PlaywrightTimeout as exc:
        raise ScreenshotError(f"Timed out waiting for the UI at {ui_url}: {exc}") from exc
    except ScreenshotError:
        raise
    except Exception as exc:
        raise ScreenshotError(str(exc)) from exc


def _select_combobox(page, name: str, option: str) -> None:
    combo = page.get_by_role("combobox", name=name)
    if option in (combo.inner_text() or ""):
        return
    combo.click()
    with page.expect_response(
        lambda response: response.url.endswith("/api/config") and response.request.method == "PUT",
        timeout=15_000,
    ):
        page.get_by_role("option", name=option, exact=True).click()


def _scroll_transcript(page) -> None:
    page.evaluate(
        """() => {
          const scroller = [...document.querySelectorAll("div")].find((el) => {
            const style = getComputedStyle(el);
            return (style.overflowY === "auto" || style.overflowY === "scroll")
              && el.scrollHeight > el.clientHeight + 8;
          });
          if (scroller) scroller.scrollTop = scroller.scrollHeight;
        }"""
    )
