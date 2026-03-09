"""
Funzioni di calcolo punteggio GEO condivise tra tutti i formatter CLI.

Centralizza le 5 funzioni di scoring per eliminare la duplicazione
tra formatters.py, rich_formatter.py, html_formatter.py, github_formatter.py.
Fix #77.
"""

from geo_optimizer.models.config import SCORING
from geo_optimizer.models.results import AuditResult


def robots_score(r: AuditResult) -> int:
    """Punteggio robots.txt allineato a SCORING (config.py)."""
    if r.robots.citation_bots_ok:
        return SCORING["robots_found"] + SCORING["robots_citation_ok"]
    if r.robots.bots_allowed:
        return SCORING["robots_found"] + SCORING["robots_some_allowed"]
    if r.robots.found:
        return SCORING["robots_found"]
    return 0


def llms_score(r: AuditResult) -> int:
    """Punteggio llms.txt allineato a SCORING (config.py).

    Guardia: senza llms.txt trovato il punteggio è zero (#105).
    """
    if not r.llms.found:
        return 0
    s = SCORING["llms_found"]
    s += SCORING["llms_h1"] if r.llms.has_h1 else 0
    s += SCORING["llms_sections"] if r.llms.has_sections else 0
    s += SCORING["llms_links"] if r.llms.has_links else 0
    return s


def schema_score(r: AuditResult) -> int:
    """Punteggio schema JSON-LD allineato a SCORING (config.py)."""
    s = SCORING["schema_website"] if r.schema.has_website else 0
    s += SCORING["schema_faq"] if r.schema.has_faq else 0
    s += SCORING["schema_webapp"] if r.schema.has_webapp else 0
    return s


def meta_score(r: AuditResult) -> int:
    """Punteggio meta tags allineato a SCORING (config.py)."""
    s = SCORING["meta_title"] if r.meta.has_title else 0
    s += SCORING["meta_description"] if r.meta.has_description else 0
    s += SCORING["meta_canonical"] if r.meta.has_canonical else 0
    s += SCORING["meta_og"] if (r.meta.has_og_title and r.meta.has_og_description) else 0
    return s


def content_score(r: AuditResult) -> int:
    """Punteggio content quality allineato a SCORING (config.py)."""
    s = SCORING["content_h1"] if r.content.has_h1 else 0
    s += SCORING["content_numbers"] if r.content.has_numbers else 0
    s += SCORING["content_links"] if r.content.has_links else 0
    return s
