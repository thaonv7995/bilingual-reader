"""Parse multipart/form-data uploads (no cgi — removed in Python 3.13+)."""

from __future__ import annotations

import re
from typing import BinaryIO


def _parse_boundary(content_type: str) -> str:
    m = re.search(r"boundary=([^;\s]+)", content_type, re.I)
    if not m:
        raise ValueError("multipart boundary missing")
    b = m.group(1).strip()
    if b.startswith('"') and b.endswith('"'):
        b = b[1:-1]
    return b


def parse_multipart(
    rfile: BinaryIO,
    content_type: str,
    content_length: int,
) -> dict[str, tuple[str | None, bytes]]:
    """Return field name -> (filename, data)."""
    boundary = _parse_boundary(content_type)
    body = rfile.read(content_length) if content_length > 0 else rfile.read()
    delim = ("--" + boundary).encode("utf-8")
    parts = body.split(delim)
    out: dict[str, tuple[str | None, bytes]] = {}

    for part in parts:
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].strip(b"\r\n")
        header_blob, _, data = part.partition(b"\r\n\r\n")
        if not header_blob:
            continue
        headers = header_blob.decode("utf-8", errors="replace")
        name_m = re.search(r'name="([^"]+)"', headers)
        if not name_m:
            continue
        name = name_m.group(1)
        file_m = re.search(r'filename="([^"]*)"', headers)
        filename = file_m.group(1) if file_m else None
        data = data.rstrip(b"\r\n")
        out[name] = (filename or None, data)
    return out
