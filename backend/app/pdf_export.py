"""
HTML → PDF for client success reports via Playwright (Chromium).
Falls back gracefully when Playwright/Chromium is not installed.
"""

from __future__ import annotations

import html as html_mod
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def playwright_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except ImportError:
        return False


def html_to_pdf(
    html: str,
    *,
    header_left: str = "",
    footer_left: str = "Confidential",
) -> Optional[bytes]:
    """Render HTML string to PDF bytes. Returns None if Playwright is unavailable."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright not installed — PDF generation unavailable")
        return None

    left_h = html_mod.escape(header_left or "")
    left_f = html_mod.escape(footer_left or "Confidential")
    header_template = f"""
      <div style="width:100%;font-size:9px;color:#8A93A6;font-family:Public Sans,Segoe UI,sans-serif;
                  padding:0 0.65in;display:flex;justify-content:space-between;">
        <span>{left_h}</span>
        <span></span>
      </div>
    """
    footer_template = f"""
      <div style="width:100%;font-size:9px;color:#8A93A6;font-family:Public Sans,Segoe UI,sans-serif;
                  padding:0 0.65in;display:flex;justify-content:space-between;">
        <span>{left_f}</span>
        <span><span class="pageNumber"></span> / <span class="totalPages"></span></span>
      </div>
    """

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(html, wait_until="networkidle")
                pdf_bytes = page.pdf(
                    format=os.getenv("KINEAXIS_PDF_FORMAT", "Letter"),
                    print_background=True,
                    display_header_footer=True,
                    header_template=header_template,
                    footer_template=footer_template,
                    margin={
                        "top": "0.75in",
                        "bottom": "0.75in",
                        "left": "0.65in",
                        "right": "0.65in",
                    },
                )
                return pdf_bytes
            finally:
                browser.close()
    except Exception as e:
        logger.error("PDF generation failed: %s", e)
        return None
