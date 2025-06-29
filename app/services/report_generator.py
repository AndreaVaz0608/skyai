# app/services/report_generator.py
"""
Gera PDF a partir de HTML usando Chromium headless (Pyppeteer).
Retorna o caminho completo do arquivo salvo.
"""

import os
import asyncio
from datetime import datetime
from flask import current_app
from pyppeteer import launch


# ── Helper interno ────────────────────────────────────────────────────────────
async def _html_to_pdf_bytes(html: str) -> bytes:
    """Converte uma string HTML em bytes PDF (A4, sem moldura)."""
    browser = await launch(args=["--no-sandbox"], headless=True)
    page = await browser.newPage()
    await page.setContent(html, waitUntil="networkidle0")
    await page.emulateMediaType("screen")
    pdf = await page.pdf(
        format="A4",
        printBackground=True,
        margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
    )
    await browser.close()
    return pdf


# ── Função pública ────────────────────────────────────────────────────────────
def generate_pdf_from_html(html_content: str, output_path: str | None = None) -> str:
    """
    Gera um PDF a partir de um HTML *renderizado*.
    • html_content: string contendo HTML completo
    • output_path : caminho do arquivo de saída (opcional)
    Retorna o caminho absoluto do PDF salvo.
    """
    if output_path is None:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(os.getcwd(), f"skyai_report_{timestamp}.pdf")

    try:
        pdf_bytes = asyncio.run(_html_to_pdf_bytes(html_content))
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        return os.path.abspath(output_path)

    except Exception as e:
        current_app.logger.error(f"[PDF ERROR] Failed to generate PDF: {e}")
        raise
