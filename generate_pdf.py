"""
generate_pdf.py
----------------
Gera um PDF idêntico à página do relatório mostrado no navegador.

Uso:
    python generate_pdf.py "URL_DO_RELATORIO" [saida.pdf]

Exemplo:
    python generate_pdf.py "http://127.0.0.1:5000/report/42" meu_relatorio.pdf
"""
import asyncio
import sys
from pathlib import Path

from pyppeteer import launch


async def html_to_pdf(url: str, out_path: str = "report.pdf") -> None:
    """Renderiza a URL e salva em PDF."""
    browser = await launch(
        args=["--no-sandbox"],  # evita erro em servidores Linux
        headless=True,          # não abre janela gráfica
    )
    page = await browser.newPage()

    # Carrega a página e espera terminar as requisições
    await page.goto(url, {"waitUntil": "networkidle0"})

    # Garante que use as cores reais da tela
    await page.emulateMediaType("screen")

    # Salva em PDF (A4, fundo colorido, margens leves)
    await page.pdf(
        path=out_path,
        format="A4",
        printBackground=True,
        margin={"top": "20px", "bottom": "20px", "left": "25px", "right": "25px"},
    )

    await browser.close()
    print(f"✅ PDF gerado em: {Path(out_path).resolve()}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python generate_pdf.py <URL> [arquivo_saida.pdf]")
        sys.exit(1)

    url = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "report.pdf"
    asyncio.run(html_to_pdf(url, out_path))


if __name__ == "__main__":
    main()
