"""
GEO Audit — JS Rendering sub-audit.

Extracted from core/audit.py for maintainability (#402).
"""

from __future__ import annotations

import copy

from geo_optimizer.models.results import JsRenderingResult


def audit_js_rendering(soup, raw_html: str) -> JsRenderingResult:
    """Check if page content is accessible without JavaScript (#226).

    Analyzes raw HTML (as fetched by requests, without JS execution) for
    content indicators. AI crawlers typically don't execute JavaScript,
    so content that requires JS rendering is invisible to them.

    Based on OtterlyAI Citation Report 2026: JS rendering is barrier #3.

    Args:
        soup: BeautifulSoup of the page (parsed from raw HTML).
        raw_html: Raw HTML string of the page.

    Returns:
        JsRenderingResult with content analysis.
    """
    result = JsRenderingResult()

    if not soup or not raw_html:
        return result

    result.checked = True

    # Estrai il testo del body (escludendo tag script/style)
    body = soup.find("body")
    if not body:
        result.js_dependent = True
        result.details = "No <body> tag found in raw HTML"
        return result

    # Fix #24: usa deepcopy per evitare di mutare il soup originale
    # (audit_citability ha bisogno dei tag <script type="application/ld+json"> intatti)
    body_clean = copy.deepcopy(body)
    for tag in body_clean.find_all(["script", "style", "noscript"]):
        tag.decompose()

    body_text = body_clean.get_text(separator=" ", strip=True)
    result.raw_word_count = len(body_text.split())

    # Conta le intestazioni nell'HTML grezzo (dal body pulito, fix #24)
    headings = body_clean.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    result.raw_heading_count = len(headings)

    # Controlla container SPA radice vuoti
    spa_indicators = [
        ("div", {"id": "root"}),
        ("div", {"id": "app"}),
        ("div", {"id": "__next"}),
        ("div", {"id": "__nuxt"}),
        ("div", {"id": "gatsby-focus-wrapper"}),
    ]
    for tag_name, attrs in spa_indicators:
        el = body_clean.find(tag_name, attrs)
        if el:
            # Controlla se l'elemento è essenzialmente vuoto (< 50 caratteri di testo)
            inner_text = el.get_text(strip=True)
            if len(inner_text) < 50:
                result.has_empty_root = True
                break

    # Controlla contenuto <noscript>
    # Fix #27: usa il soup originale (non mutato, grazie al fix #24)
    noscript_tags = soup.find_all("noscript")
    for ns in noscript_tags:
        ns_text = ns.get_text(strip=True)
        if len(ns_text) > 20:
            result.has_noscript_content = True
            break

    # Rileva framework JS dall'HTML grezzo
    html_lower = raw_html[:10000].lower()
    if "/__next/" in html_lower or "_next/static" in html_lower or "__next" in html_lower:
        result.framework_detected = "next.js"
    elif "__nuxt" in html_lower or "_nuxt/" in html_lower:
        result.framework_detected = "nuxt"
    elif "react" in html_lower and ('id="root"' in html_lower or "createroot" in html_lower):
        result.framework_detected = "react"
    elif "ng-version" in html_lower or "ng-app" in html_lower:
        result.framework_detected = "angular"
    elif "data-v-" in html_lower or 'id="app"' in html_lower:
        result.framework_detected = "vue"
    elif "gatsby" in html_lower:
        result.framework_detected = "gatsby"
    elif "astro" in html_lower or "_astro/" in html_lower:
        result.framework_detected = "astro"

    # Determina se il contenuto dipende da JS
    # Soglie: < 100 parole nel body E 0 intestazioni → probabilmente SPA
    if result.raw_word_count < 100 and result.raw_heading_count == 0:
        result.js_dependent = True
        result.details = (
            f"Only {result.raw_word_count} words and 0 headings in raw HTML. "
            "Content likely requires JavaScript to render. "
            "AI crawlers won't see it. Consider SSR/SSG or pre-rendering."
        )
    elif result.has_empty_root and result.raw_word_count < 200:
        result.js_dependent = True
        result.details = (
            f"Empty SPA root container detected with only {result.raw_word_count} words. "
            f"Framework: {result.framework_detected or 'unknown'}. "
            "Implement server-side rendering for AI crawler accessibility."
        )
    elif result.raw_word_count < 50:
        result.js_dependent = True
        result.details = (
            f"Critically low content: {result.raw_word_count} words in raw HTML. "
            "Page appears to be a JavaScript-only application."
        )
    else:
        result.details = (
            f"{result.raw_word_count} words and {result.raw_heading_count} headings "
            "found in raw HTML. Content is accessible without JavaScript."
        )

    return result
