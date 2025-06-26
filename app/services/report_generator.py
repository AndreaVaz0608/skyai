# app/services/report_generator.py

import pdfkit
import os
import platform
from flask import current_app

def generate_pdf_from_html(html_content, output_path=None):
    """
    Generates a PDF from a rendered HTML string.
    Uses wkhtmltopdf configuration if needed.
    """

    config = None

    # Define path for local dev on Windows
    if platform.system() == "Windows":
        wkhtmltopdf_path = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
        if os.path.exists(wkhtmltopdf_path):
            config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)

    # Define default output path if not provided
    if not output_path:
        output_path = os.path.join(os.getcwd(), "skyai_report.pdf")  # 🔥 Atualizado

    try:
        pdfkit.from_string(html_content, output_path, configuration=config)
        return output_path
    except Exception as e:
        current_app.logger.error(f"[PDF ERROR] Failed to generate PDF: {e}")
        raise
