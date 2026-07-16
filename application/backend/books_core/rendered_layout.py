"""Measure standalone book pages in Chromium and report clipped/overflowing content."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Iterable

from books_core.pdf_export import find_chromium


A4_WIDTH_PX = 210 * 96 / 25.4
A4_HEIGHT_296_PX = 296 * 96 / 25.4
A4_HEIGHT_297_PX = 297 * 96 / 25.4
SHELL_TOLERANCE_PX = 2.0
CONTENT_TOLERANCE_PX = 4.5


_MEASURE_LAYOUT = r"""() => {
  const sheets = Array.from(document.querySelectorAll('.book-page.book-page--sheet'));
  if (sheets.length !== 1) return {sheetCount: sheets.length};
  const sheet = sheets[0];
  const sheetRect = sheet.getBoundingClientRect();
  const tolerance = 4.5;
  const bounds = {left: 0, right: 0, top: 0, bottom: 0};
  const offenders = {left: '', right: '', top: '', bottom: ''};
  const clipped = [];

  const describe = (element) => {
    if (!element) return 'unknown element';
    let value = element.tagName.toLowerCase();
    if (element.id) value += `#${element.id}`;
    const classes = Array.from(element.classList || []).slice(0, 3);
    if (classes.length) value += `.${classes.join('.')}`;
    return value;
  };

  const skipped = (element) => {
    if (!element || element === sheet) return false;
    if (element.closest('.page-nav, [data-studio-overlay]')) return true;
    const style = getComputedStyle(element);
    return style.display === 'none' || style.visibility === 'hidden' ||
      style.contentVisibility === 'hidden' || Number(style.opacity) === 0 ||
      style.position === 'fixed';
  };

  // Respect intentional clipping inside figures/boxes, but deliberately do not
  // intersect with the sheet: sheet overflow:hidden must not conceal page loss.
  const visibleRect = (rect, element) => {
    const visible = {left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom};
    for (let parent = element.parentElement; parent && parent !== sheet; parent = parent.parentElement) {
      const style = getComputedStyle(parent);
      const parentRect = parent.getBoundingClientRect();
      if (['hidden', 'clip', 'auto', 'scroll'].includes(style.overflowX)) {
        visible.left = Math.max(visible.left, parentRect.left);
        visible.right = Math.min(visible.right, parentRect.right);
      }
      if (['hidden', 'clip', 'auto', 'scroll'].includes(style.overflowY)) {
        visible.top = Math.max(visible.top, parentRect.top);
        visible.bottom = Math.min(visible.bottom, parentRect.bottom);
      }
    }
    return visible;
  };

  const recordBounds = (rect, label) => {
    if (rect.right <= rect.left || rect.bottom <= rect.top) return;
    const values = {
      left: sheetRect.left - rect.left,
      right: rect.right - sheetRect.right,
      top: sheetRect.top - rect.top,
      bottom: rect.bottom - sheetRect.bottom,
    };
    for (const edge of Object.keys(values)) {
      if (values[edge] > bounds[edge]) {
        bounds[edge] = values[edge];
        offenders[edge] = label;
      }
    }
  };

  for (const element of sheet.querySelectorAll('*')) {
    if (skipped(element)) continue;
    const rect = element.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    recordBounds(visibleRect(rect, element), describe(element));

    const style = getComputedStyle(element);
    const hasText = Boolean((element.innerText || '').trim());
    if (!hasText || element.clientWidth <= 0 || element.clientHeight <= 0) continue;
    const clippedX = element.scrollWidth - element.clientWidth;
    const clippedY = element.scrollHeight - element.clientHeight;
    const clipsX = ['hidden', 'clip', 'auto', 'scroll'].includes(style.overflowX);
    const clipsY = ['hidden', 'clip', 'auto', 'scroll'].includes(style.overflowY);
    if ((clipsX && clippedX > tolerance) || (clipsY && clippedY > tolerance)) {
      clipped.push({
        selector: describe(element),
        x: clipsX ? clippedX : 0,
        y: clipsY ? clippedY : 0,
      });
    }
  }

  const walker = document.createTreeWalker(sheet, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    if (!node.nodeValue.trim()) continue;
    const parent = node.parentElement;
    if (skipped(parent)) continue;
    const range = document.createRange();
    range.selectNodeContents(node);
    for (const rect of range.getClientRects()) {
      recordBounds(visibleRect(rect, parent), `${describe(parent)} text`);
    }
  }

  return {
    sheetCount: 1,
    shell: {width: sheetRect.width, height: sheetRect.height},
    bounds,
    offenders,
    clipped: clipped.slice(0, 8),
  };
}"""


def issues_from_layout_metrics(
    metrics: dict[str, Any],
    *,
    allow_vertical_overflow: bool = False,
) -> list[str]:
    """Turn browser geometry into stable, page-level validation messages."""
    sheet_count = int(metrics.get("sheetCount", 0))
    if sheet_count != 1:
        return [f"rendered page must contain exactly one A4 sheet (found {sheet_count})"]

    issues: list[str] = []
    shell = metrics.get("shell") or {}
    width = float(shell.get("width", 0))
    height = float(shell.get("height", 0))
    if abs(width - A4_WIDTH_PX) > SHELL_TOLERANCE_PX:
        issues.append(
            f"rendered page width is {width:.1f}px; expected 210mm "
            f"({A4_WIDTH_PX:.1f}px)"
        )
    if not allow_vertical_overflow and min(
        abs(height - A4_HEIGHT_296_PX), abs(height - A4_HEIGHT_297_PX)
    ) > SHELL_TOLERANCE_PX:
        issues.append(
            f"rendered page height is {height:.1f}px; expected 296–297mm A4 height"
        )

    bounds = metrics.get("bounds") or {}
    offenders = metrics.get("offenders") or {}
    left = float(bounds.get("left", 0))
    right = float(bounds.get("right", 0))
    top = float(bounds.get("top", 0))
    bottom = float(bounds.get("bottom", 0))
    horizontal = max(left, right)
    if horizontal > CONTENT_TOLERANCE_PX:
        edge = "left" if left >= right else "right"
        issues.append(
            f"horizontal overflow by {horizontal:.1f}px near "
            f"{offenders.get(edge) or 'page content'}"
        )
    if not allow_vertical_overflow:
        vertical = max(top, bottom)
        if vertical > CONTENT_TOLERANCE_PX:
            edge = "top" if top >= bottom else "bottom"
            issues.append(
                f"vertical overflow by {vertical:.1f}px near "
                f"{offenders.get(edge) or 'page content'}"
            )

    for item in metrics.get("clipped") or []:
        x = float(item.get("x", 0))
        y = float(item.get("y", 0))
        parts: list[str] = []
        if x > CONTENT_TOLERANCE_PX:
            parts.append(f"{x:.1f}px horizontally")
        if not allow_vertical_overflow and y > CONTENT_TOLERANCE_PX:
            parts.append(f"{y:.1f}px vertically")
        if parts:
            issues.append(
                f"clipped text/content overflow in {item.get('selector') or 'element'}: "
                + " and ".join(parts)
            )
        if len(issues) >= 6:
            break
    return issues


async def _validate_rendered_pages(
    paths: list[Path],
    *,
    browser_path: Path,
    concurrency: int,
    timeout_ms: int,
) -> dict[Path, list[str]]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed; reinstall/update Books Studio") from exc

    results: dict[Path, list[str]] = {}
    queue: asyncio.Queue[Path] = asyncio.Queue()
    for path in paths:
        queue.put_nowait(path)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=str(browser_path),
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--allow-file-access-from-files",
            ],
        )
        context = await browser.new_context(viewport={"width": 794, "height": 1123})

        async def worker() -> None:
            page = await context.new_page()
            page.set_default_timeout(timeout_ms)
            await page.emulate_media(media="print")
            try:
                while not queue.empty():
                    try:
                        path = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    try:
                        await page.goto(path.as_uri(), wait_until="load", timeout=timeout_ms)
                        await page.evaluate(
                            """async () => {
                              const ready = document.fonts?.ready || Promise.resolve();
                              const images = Promise.all(Array.from(document.images).map((image) => {
                                if (image.complete) return Promise.resolve();
                                return new Promise((resolve) => {
                                  image.addEventListener('load', resolve, {once: true});
                                  image.addEventListener('error', resolve, {once: true});
                                });
                              }));
                              await Promise.race([
                                Promise.all([ready, images]),
                                new Promise((resolve) => setTimeout(resolve, 5000)),
                              ]);
                            }"""
                        )
                        metrics = await page.evaluate(_MEASURE_LAYOUT)
                        results[path] = issues_from_layout_metrics(
                            metrics,
                            allow_vertical_overflow=path.parent.name == "en-ipa",
                        )
                    except Exception as exc:  # browser errors must fail validation, not disappear
                        results[path] = [f"rendered layout check failed: {exc}"]
                    finally:
                        queue.task_done()
            finally:
                await page.close()

        workers = [
            asyncio.create_task(worker())
            for _ in range(max(1, min(concurrency, len(paths))))
        ]
        await asyncio.gather(*workers)
        await context.close()
        await browser.close()
    return results


def validate_rendered_pages(
    paths: Iterable[Path],
    *,
    browser_path: Path | None = None,
    concurrency: int = 4,
    timeout_ms: int = 30_000,
) -> dict[Path, list[str]]:
    """Render pages with print CSS and return issues keyed by source path."""
    normalized = [Path(path).resolve() for path in paths]
    if not normalized:
        return {}
    resolved_browser = browser_path or find_chromium()
    return asyncio.run(
        _validate_rendered_pages(
            normalized,
            browser_path=resolved_browser,
            concurrency=concurrency,
            timeout_ms=timeout_ms,
        )
    )
