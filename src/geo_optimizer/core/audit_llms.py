"""
Audit llms.txt per AI indexing.

Estratto da audit.py (#402-bis) — separazione responsabilità.
Tutte le funzioni ritornano dataclass, MAI stampano.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from geo_optimizer.models.results import LlmsTxtResult
from geo_optimizer.utils.http import fetch_url


def _validate_llms_content(result: LlmsTxtResult, content: str) -> None:
    """Validate llms.txt content against spec v2 and populate result fields.

    Popola has_blockquote, has_optional_section, companion_files_hint
    e validation_warnings sul result passato.

    Args:
        result: LlmsTxtResult già inizializzato con i campi base.
        content: Contenuto testuale del file llms.txt (già senza BOM).
    """
    lines = content.splitlines()
    warnings: list[str] = []

    # Validazione blockquote (> description) — OBBLIGATORIA per spec
    blockquotes = [line for line in lines if line.startswith("> ")]
    if blockquotes:
        result.has_blockquote = True
    else:
        warnings.append("llms.txt should have a > blockquote description after H1")

    # Validazione H1 — deve essere la prima riga non vuota
    non_empty_lines = [line for line in lines if line.strip()]
    if non_empty_lines and not non_empty_lines[0].startswith("# "):
        warnings.append("H1 should be the first line of llms.txt")

    # Validazione link markdown
    if not result.has_links:
        warnings.append("llms.txt should contain markdown links to site pages")

    # Validazione lunghezza minima
    if result.word_count < 100:
        warnings.append("llms.txt is too short, consider adding more content")

    # ## Optional section — best practice
    h2_lines = [line for line in lines if line.startswith("## ")]
    for h2 in h2_lines:
        if "optional" in h2.lower():
            result.has_optional_section = True
            break

    # Companion files: link a file .md (es. something.html.md)
    links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)
    for _text, url in links:
        if url.endswith(".md"):
            result.companion_files_hint = True
            break

    result.validation_warnings = warnings


def audit_llms_txt(base_url: str) -> LlmsTxtResult:
    """Check for presence and quality of llms.txt. Returns LlmsTxtResult."""
    llms_url = urljoin(base_url, "/llms.txt")
    r, err = fetch_url(llms_url)

    result = LlmsTxtResult()

    if err or not r:
        return result

    # Solo le risposte 200 contengono un llms.txt valido
    if r.status_code != 200:
        return result

    result.found = True
    # Rimuovi UTF-8 BOM se presente (es. file generati da Yoast SEO)
    content = r.text.lstrip("\ufeff")
    lines = content.splitlines()
    result.word_count = len(content.split())

    # Check H1 (required)
    h1_lines = [line for line in lines if line.startswith("# ")]
    if h1_lines:
        result.has_h1 = True

    # Check blockquote description
    blockquotes = [line for line in lines if line.startswith("> ")]
    if blockquotes:
        # Fix #317: sincronizza has_description (alias backward-compat) con has_blockquote
        result.has_blockquote = True
        result.has_description = True

    # Check H2 sections
    h2_lines = [line for line in lines if line.startswith("## ")]
    if h2_lines:
        result.has_sections = True
    # #247: conta le sezioni H2 per Policy Intelligence
    result.sections_count = len(h2_lines)

    # Check markdown links
    links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)
    if links:
        result.has_links = True
    # #247: conta i link per Policy Intelligence
    result.links_count = len(links)

    # #39: validazione v2 — conformità spec completa
    _validate_llms_content(result, content)

    # Check /llms-full.txt (llmstxt.org spec — optional extended version)
    full_url = urljoin(base_url, "/llms-full.txt")
    r_full, err_full = fetch_url(full_url)
    if r_full and r_full.status_code == 200 and len(r_full.text.strip()) > 0:
        result.has_full = True

    return result


def _audit_llms_from_response(r, r_full=None) -> LlmsTxtResult:
    """Analyze llms.txt from an already-downloaded HTTP response.

    Args:
        r: HTTP response for /llms.txt (or None).
        r_full: HTTP response for /llms-full.txt (or None). Fix #184.
    """
    result = LlmsTxtResult()

    if not r or r.status_code != 200:
        return result

    result.found = True
    content = r.text.lstrip("\ufeff")
    lines = content.splitlines()
    result.word_count = len(content.split())

    h1_lines = [line for line in lines if line.startswith("# ")]
    if h1_lines:
        result.has_h1 = True

    blockquotes = [line for line in lines if line.startswith("> ")]
    if blockquotes:
        # Fix #317: sincronizza has_description (alias backward-compat) con has_blockquote
        result.has_blockquote = True
        result.has_description = True

    h2_lines = [line for line in lines if line.startswith("## ")]
    if h2_lines:
        result.has_sections = True
    # #247: conta le sezioni H2 per Policy Intelligence
    result.sections_count = len(h2_lines)

    links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)
    if links:
        result.has_links = True
    # #247: conta i link per Policy Intelligence
    result.links_count = len(links)

    # #39: validazione v2 — conformità spec completa
    _validate_llms_content(result, content)

    # Check /llms-full.txt — fix #184: now works in the async path too
    if r_full and r_full.status_code == 200 and len(r_full.text.strip()) > 0:
        result.has_full = True

    return result
