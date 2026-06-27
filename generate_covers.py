import os
from pathlib import Path
import pypdfium2 as pdfium

books_dir = Path("books")
for item in books_dir.iterdir():
    if item.is_dir() and not item.name.startswith("_") and item.name not in ["bkbs", "done", "inbox"]:
        pdf_path = item / "input" / "original.pdf"
        cover_path = item / "cover.jpg"
        if pdf_path.is_file() and not cover_path.is_file():
            print(f"Generating cover for {item.name}")
            try:
                doc = pdfium.PdfDocument(str(pdf_path))
                page = doc.get_page(0)
                bitmap = page.render(scale=1.0)
                pil_image = bitmap.to_pil()
                pil_image.save(str(cover_path), format="JPEG")
                print(f"Cover generated for {item.name}")
            except Exception as e:
                print(f"Error generating cover for {item.name}: {e}")
