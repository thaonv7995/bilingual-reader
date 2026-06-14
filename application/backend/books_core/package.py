"""Book packaging utilities to create and extract .bkb (Bilingual Book Package) archives."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any
from books_core.paths import BookPaths

def pack_book(book_dir: str | Path, output_path: str | Path | None = None) -> dict[str, Any]:
    """
    Pack a processed book's metadata and output deliverables into a .bkb (ZIP) archive.
    
    Structure inside .bkb:
    - manifest.json (contains metadata from book.json and slug)
    - output/ (all rendered pages and assets)
    """
    import shutil
    from books_core.library_cover import cover_file, ensure_cover

    book_path = Path(book_dir).expanduser().resolve()
    if not book_path.is_dir():
        raise NotADirectoryError(f"Book directory does not exist: {book_path}")
        
    book = BookPaths.open(book_path)
    book_json_path = book.book_json
    output_dir = book.output_dir
    
    if not output_dir.is_dir():
        raise FileNotFoundError(f"Book has no output deliverables directory: {output_dir}")
        
    # Read book metadata
    metadata = book.load_book_json()
    metadata["slug"] = book_path.name
    
    # Process author
    if not metadata.get("author"):
        # Try to read from PDF metadata
        pdf_author = None
        if book.source_pdf.is_file():
            try:
                import fitz
                with fitz.open(book.source_pdf) as doc:
                    pdf_author = doc.metadata.get("author")
            except Exception:
                pass
        if pdf_author and pdf_author.lower() not in ("unknown", "none", ""):
            metadata["author"] = pdf_author.strip()
        else:
            # Try to infer from slug (e.g. animal-farm-by-george-orwell -> George Orwell)
            slug = book_path.name
            if "-by-" in slug:
                inferred = slug.split("-by-")[-1].replace("-", " ").title()
                metadata["author"] = inferred
            else:
                metadata["author"] = "Unknown"
        
        # Save the inferred author back to book.json so it's persisted
        try:
            book_json_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    # Ensure cover image exists at output/assets/images/page_0001_cover_logo.png
    target_cover = output_dir / "assets" / "images" / "page_0001_cover_logo.png"
    
    src_cover = None
    # 1. Search for Priority 1: assets/cover.jpg
    for base in (output_dir / "assets", book_path / "assets"):
        p = base / "cover.jpg"
        if p.is_file():
            src_cover = p
            break
            
    # 2. Search for Priority 2: assets/cover.png
    if not src_cover:
        for base in (output_dir / "assets", book_path / "assets"):
            p = base / "cover.png"
            if p.is_file():
                src_cover = p
                break
                
    # If not found, try to generate it using ensure_cover(book)
    if not src_cover:
        try:
            src_cover = ensure_cover(book)
        except Exception:
            pass
            
    # 3. Search for Priority 3: assets/images/page_0001_cover_logo.png
    if not src_cover:
        for base in (output_dir / "assets", book_path / "assets"):
            p = base / "images" / "page_0001_cover_logo.png"
            if p.is_file():
                src_cover = p
                break
                
    # If still not found, use existing target_cover as fallback
    if not src_cover and target_cover.is_file():
        src_cover = target_cover
        
    # Copy to target_cover if we found a source cover and it is not already there
    if src_cover and src_cover.is_file() and src_cover.resolve() != target_cover.resolve():
        target_cover.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src_cover, target_cover)
            
    # Determine output archive path
    if output_path is None:
        output_bkb = book_path.parent / f"{book_path.name}.bkb"
    else:
        output_bkb = Path(output_path).expanduser().resolve()
        
    # Ensure parent directory of output archive exists
    output_bkb.parent.mkdir(parents=True, exist_ok=True)
    
    # Write package ZIP
    with zipfile.ZipFile(output_bkb, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # Write manifest.json
        zip_file.writestr("manifest.json", json.dumps(metadata, indent=2, ensure_ascii=False))
        
        # Write all contents of the output directory
        for file in output_dir.rglob("*"):
            if file.is_file():
                # Write with relative path inside output/
                arcname = Path("output") / file.relative_to(output_dir)
                zip_file.write(file, arcname=arcname)
                
    return {
        "ok": True,
        "slug": book_path.name,
        "archive": str(output_bkb),
        "page_count": metadata.get("page_count", 0),
        "title": metadata.get("title", book_path.name)
    }

def unpack_book(bkb_path: str | Path, dest_parent_dir: str | Path) -> dict[str, Any]:
    """
    Extract a .bkb archive into the destination parent directory.
    Recreates the directory structure:
    dest_parent_dir/<slug>/
      ├── book.json (reconstructed from manifest.json)
      └── output/ (extracted output deliverables)
    """
    archive_path = Path(bkb_path).expanduser().resolve()
    if not archive_path.is_file():
        raise FileNotFoundError(f"Archive file not found: {archive_path}")
        
    parent_path = Path(dest_parent_dir).expanduser().resolve()
    parent_path.mkdir(parents=True, exist_ok=True)
    
    with zipfile.ZipFile(archive_path, "r") as zip_file:
        # Read manifest.json to get slug
        try:
            manifest_data = zip_file.read("manifest.json").decode("utf-8")
            metadata = json.loads(manifest_data)
        except Exception as e:
            raise ValueError(f"Failed to read manifest.json from archive: {e}")
            
        slug = metadata.get("slug") or archive_path.stem
        book_dir = parent_path / slug
        book_dir.mkdir(parents=True, exist_ok=True)
        
        # Write book.json
        book_json_dest = book_dir / "book.json"
        book_json_dest.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        
        # Extract files that belong under output/
        extracted_count = 0
        for name in zip_file.namelist():
            if name.startswith("output/"):
                # Get the relative path after output/
                rel_path = Path(name).relative_to("output")
                dest_file = book_dir / "output" / rel_path
                
                # Check if it is a directory or file
                if name.endswith("/"):
                    dest_file.mkdir(parents=True, exist_ok=True)
                else:
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    with zip_file.open(name) as src, open(dest_file, "wb") as dst:
                        dst.write(src.read())
                    extracted_count += 1
                    
    return {
        "ok": True,
        "slug": slug,
        "dest_dir": str(book_dir),
        "files_extracted": extracted_count,
        "title": metadata.get("title", slug)
    }
