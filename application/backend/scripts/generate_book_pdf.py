#!/usr/bin/env python3
"""Compile one assembled HTML book to a verified A4 PDF."""

import sys
import asyncio
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from books_core.pdf_export import export_html_pdf

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 generate_book_pdf.py <input.html> <output.pdf>")
        sys.exit(1)
        
    html_path = Path(sys.argv[1])
    pdf_path = Path(sys.argv[2])
    
    if not html_path.is_file():
        print(f"Error: {html_path} does not exist.")
        sys.exit(1)
        
    result = asyncio.run(export_html_pdf(html_path, pdf_path))
    print(f"PDF generation complete: {result['pages']} A4 pages, {result['bytes']} bytes")

if __name__ == "__main__":
    main()
