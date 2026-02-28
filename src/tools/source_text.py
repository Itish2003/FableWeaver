"""
Source text ingestion and retrieval tools.

Provides:
- PDF ingestion (local files or Google Drive URLs) via ``pypdf``
- Agent-facing tools: ``get_source_text`` and ``search_source_text``
- Bulk folder ingestion for Google Drive folders via Playwright
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from sqlalchemy import select, or_

from src.database import AsyncSessionLocal
from src.models import SourceText

logger = logging.getLogger("fable.source_text")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_pdf_text(pdf_path: str) -> str:
    """Extract all text from a PDF using pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


async def _download_gdrive_file(url: str, dest_path: str) -> None:
    """Download a file from Google Drive using Playwright (handles redirect).

    Google Drive direct-download URLs (``/uc?export=download``) immediately
    trigger a file download which Playwright treats as a navigation error.
    We handle this by:
    1. Enabling ``accept_downloads`` on the browser context
    2. Wrapping ``page.goto`` inside ``page.expect_download`` so the download
       event is captured rather than raising an exception
    3. For large files that show a "Download anyway" confirmation page, we
       click through before the download starts
    """
    from playwright.async_api import async_playwright

    match = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
    if match:
        file_id = match.group(1)
        download_url = f"https://drive.google.com/uc?id={file_id}&export=download"
    else:
        download_url = url

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # Try navigating — small files start downloading immediately
            async with page.expect_download(timeout=120_000) as download_info:
                # goto will raise "Download is starting" for direct downloads;
                # expect_download captures the event regardless
                try:
                    await page.goto(download_url, wait_until="commit", timeout=30_000)
                except Exception:
                    pass  # Expected — the navigation becomes a download

                # For large files, Drive shows a confirmation page instead of
                # starting the download. Check for the confirm button.
                try:
                    confirm = page.locator(
                        "a:has-text('Download anyway'), "
                        "form#download-form input[type=submit], "
                        "#uc-download-link"
                    )
                    if await confirm.count() > 0:
                        await confirm.first.click()
                except Exception:
                    pass  # Already downloading

            download = await download_info.value
            await download.save_as(dest_path)
        finally:
            await context.close()
            await browser.close()

    logger.info("Downloaded %s → %s", url, dest_path)


# ---------------------------------------------------------------------------
# Ingestion functions (called from admin/CLI, not agent tools)
# ---------------------------------------------------------------------------

async def ingest_pdf(
    universe: str,
    volume: str,
    pdf_path_or_url: str,
) -> dict:
    """
    Ingest a PDF into the source_text table.

    - If ``pdf_path_or_url`` is a local path, reads directly.
    - If it looks like a URL (starts with http), downloads first via Playwright.
    - Deduplicates on (universe, volume): skips if already exists.

    Returns a summary dict with keys: universe, volume, word_count, status.
    """
    universe = universe.lower().strip()
    volume = volume.strip()

    # Check for existing entry
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SourceText).where(
                SourceText.universe == universe,
                SourceText.volume == volume,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            logger.info("Source text already exists for %s / %s (id=%d)", universe, volume, existing.id)
            return {
                "universe": universe,
                "volume": volume,
                "word_count": existing.word_count,
                "status": "already_exists",
            }

    # Download if URL
    pdf_path = pdf_path_or_url
    tmp_file = None
    if pdf_path_or_url.startswith("http"):
        tmp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp_file.close()
        await _download_gdrive_file(pdf_path_or_url, tmp_file.name)
        pdf_path = tmp_file.name

    try:
        text = _extract_pdf_text(pdf_path)
        # Strip null bytes — some PDFs contain 0x00 which PostgreSQL rejects
        text = text.replace("\x00", "")
    finally:
        if tmp_file:
            os.unlink(tmp_file.name)

    word_count = len(text.split())
    logger.info(
        "Extracted %d chars / %d words from %s (%s / %s)",
        len(text), word_count, pdf_path_or_url, universe, volume,
    )

    # Store in DB
    source_url = pdf_path_or_url if pdf_path_or_url.startswith("http") else None
    async with AsyncSessionLocal() as db:
        entry = SourceText(
            universe=universe,
            volume=volume,
            content=text,
            word_count=word_count,
            source_url=source_url,
        )
        db.add(entry)
        await db.commit()

    return {
        "universe": universe,
        "volume": volume,
        "word_count": word_count,
        "status": "ingested",
    }


async def ingest_gdrive_folder(universe: str, folder_url: str) -> list[dict]:
    """
    List PDFs in a Google Drive folder and ingest each one.

    Folder URL format: https://drive.google.com/drive/folders/FOLDER_ID
    Volume names are derived from filenames (e.g., "Volume 01.pdf" → "Volume 01").
    """
    from playwright.async_api import async_playwright

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(folder_url, timeout=30_000)
        await page.wait_for_load_state("networkidle", timeout=15_000)

        # Extract file links from Drive folder listing
        links = await page.evaluate("""
            () => {
                const items = document.querySelectorAll('[data-id]');
                return Array.from(items).map(el => ({
                    name: el.getAttribute('aria-label') || el.textContent.trim(),
                    id: el.getAttribute('data-id')
                })).filter(i => i.name.toLowerCase().endsWith('.pdf'));
            }
        """)
        await browser.close()

    logger.info("Found %d PDFs in folder: %s", len(links), folder_url)

    for link in links:
        file_url = f"https://drive.google.com/file/d/{link['id']}/view"
        # Derive volume name from filename (strip .pdf extension)
        vol_name = re.sub(r"\.pdf$", "", link["name"], flags=re.IGNORECASE).strip()
        try:
            result = await ingest_pdf(universe, vol_name, file_url)
            results.append(result)
        except Exception as e:
            logger.error("Failed to ingest %s: %s", link["name"], e)
            results.append({"universe": universe, "volume": vol_name, "status": "error", "error": str(e)})

    return results


# ---------------------------------------------------------------------------
# Agent-facing tools (registered with ADK agents)
# ---------------------------------------------------------------------------

async def get_source_text(universe: str, volume: str) -> str:
    """Retrieve the full text of a specific volume from the source text database.

    Use this when building event_playbooks for canon events — the source text
    contains the actual novel/manga prose with scene-level narrative detail.

    Args:
        universe: The universe key (e.g., "mahouka", "jjk").
        volume: The volume identifier (e.g., "Volume 2", "Volume 26").

    Returns:
        The full extracted text of the volume, or an error message if not found.
    """
    universe = universe.lower().strip()
    volume = volume.strip()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SourceText).where(
                SourceText.universe == universe,
                SourceText.volume == volume,
            )
        )
        entry = result.scalar_one_or_none()

    if not entry:
        # Try fuzzy match on volume name
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(SourceText).where(
                    SourceText.universe == universe,
                )
            )
            all_vols = result.scalars().all()

        if all_vols:
            vol_list = ", ".join(f'"{v.volume}"' for v in all_vols)
            return f"Volume '{volume}' not found for universe '{universe}'. Available volumes: {vol_list}"
        return f"No source text found for universe '{universe}'. Source text has not been ingested yet."

    return entry.content


async def search_source_text(universe: str, query: str) -> str:
    """Search source text across all volumes of a universe for relevant passages.

    Searches for keyword matches and returns surrounding context (500 chars
    before and after each match). Useful for finding specific scenes, character
    interactions, or event descriptions.

    Args:
        universe: The universe key (e.g., "mahouka", "jjk").
        query: The search term or phrase to find in the source text.

    Returns:
        Matching excerpts with volume and position context, or a message if no matches.
    """
    universe = universe.lower().strip()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SourceText).where(SourceText.universe == universe)
        )
        volumes = result.scalars().all()

    if not volumes:
        return f"No source text found for universe '{universe}'."

    matches = []
    query_lower = query.lower()
    context_chars = 500

    for vol in volumes:
        content_lower = vol.content.lower()
        search_start = 0
        vol_matches = 0
        while vol_matches < 5:  # Max 5 matches per volume
            idx = content_lower.find(query_lower, search_start)
            if idx == -1:
                break
            start = max(0, idx - context_chars)
            end = min(len(vol.content), idx + len(query) + context_chars)
            excerpt = vol.content[start:end]
            # Clean up excerpt boundaries
            if start > 0:
                excerpt = "..." + excerpt
            if end < len(vol.content):
                excerpt = excerpt + "..."
            matches.append(f"[{vol.volume}, pos {idx}]\n{excerpt}")
            search_start = idx + len(query)
            vol_matches += 1

    if not matches:
        vol_list = ", ".join(f'"{v.volume}"' for v in volumes)
        return f"No matches for '{query}' in {universe}. Searched volumes: {vol_list}"

    header = f"Found {len(matches)} match(es) for '{query}' in {universe}:\n\n"
    return header + "\n\n---\n\n".join(matches[:10])  # Cap at 10 total matches


async def list_source_texts(universe: str = None) -> str:
    """List all ingested source texts, optionally filtered by universe.

    Args:
        universe: Optional universe filter. If None, lists all.

    Returns:
        A formatted list of available source texts with word counts.
    """
    async with AsyncSessionLocal() as db:
        stmt = select(SourceText)
        if universe:
            stmt = stmt.where(SourceText.universe == universe.lower().strip())
        stmt = stmt.order_by(SourceText.universe, SourceText.volume)
        result = await db.execute(stmt)
        entries = result.scalars().all()

    if not entries:
        return "No source texts ingested yet."

    lines = []
    for e in entries:
        lines.append(f"- {e.universe} / {e.volume}: {e.word_count:,} words (id={e.id})")
    return "\n".join(lines)
