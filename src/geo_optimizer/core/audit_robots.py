"""
Audit robots.txt per AI bot access.

Estratto da audit.py (#402-bis) — separazione responsabilità.
Tutte le funzioni ritornano dataclass, MAI stampano.
"""

from __future__ import annotations

from urllib.parse import urljoin

from geo_optimizer.models.config import AI_BOTS, CITATION_BOTS
from geo_optimizer.models.results import RobotsResult
from geo_optimizer.utils.http import fetch_url
from geo_optimizer.utils.robots_parser import classify_bot, parse_robots_txt


def audit_robots_txt(base_url: str, bots: dict = None) -> RobotsResult:
    """Check robots.txt for AI bot access. Returns RobotsResult.

    Args:
        base_url: Base URL of the site.
        bots: Dictionary of bots to check. Default: AI_BOTS from config.
              Fix #120: allows passing extra bots from project_config.extra_bots.
    """
    robots_url = urljoin(base_url, "/robots.txt")
    r, err = fetch_url(robots_url)

    result = RobotsResult()

    if err or not r:
        return result

    # Solo le risposte 200 contengono un robots.txt valido (403, 500, ecc. non lo sono)
    if r.status_code != 200:
        return result

    result.found = True

    content = r.text

    # Analisi robots.txt in regole strutturate
    agent_rules = parse_robots_txt(content)

    # Usa i bot passati oppure AI_BOTS di default
    effective_bots = bots if bots is not None else AI_BOTS

    # Classifica ogni AI bot
    for bot, description in effective_bots.items():
        bot_status = classify_bot(bot, description, agent_rules)

        if bot_status.status == "missing":
            result.bots_missing.append(bot)
        elif bot_status.status == "blocked":
            result.bots_blocked.append(bot)
        elif bot_status.status == "partial":
            # #106 — Parzialmente bloccato: trattato come allowed per compatibilità
            # ma tracciato separatamente in bots_partial
            result.bots_allowed.append(bot)
            result.bots_partial.append(bot)
        else:
            # "allowed" (completamente permesso)
            result.bots_allowed.append(bot)

    # Check citation bots (allowed includes partial matches)
    result.citation_bots_ok = all(b in result.bots_allowed for b in CITATION_BOTS)

    # #111 — Verifica che i citation bots siano ESPLICITAMENTE permessi (non solo via wildcard)
    # Punteggio pieno solo con regole specifiche per i citation bots
    citation_explicit = []
    for bot in CITATION_BOTS:
        bot_status = classify_bot(bot, "", agent_rules)
        if bot_status.status in ("allowed", "partial") and not bot_status.via_wildcard:
            citation_explicit.append(bot)
    result.citation_bots_explicit = len(citation_explicit) == len(CITATION_BOTS)

    return result


def _audit_robots_from_response(r, bots: dict = None) -> RobotsResult:
    """Analyze robots.txt from an already-downloaded HTTP response.

    Args:
        r: HTTP response (or None if fetch failed).
        bots: Dictionary of bots to check. Default: AI_BOTS from config.
              Allows passing extra bots from project_config.extra_bots.
    """
    result = RobotsResult()

    if not r or r.status_code != 200:
        return result

    effective_bots = bots if bots is not None else AI_BOTS

    result.found = True
    content = r.text
    agent_rules = parse_robots_txt(content)

    for bot, description in effective_bots.items():
        bot_status = classify_bot(bot, description, agent_rules)

        if bot_status.status == "missing":
            result.bots_missing.append(bot)
        elif bot_status.status == "blocked":
            result.bots_blocked.append(bot)
        elif bot_status.status == "partial":
            result.bots_allowed.append(bot)
            result.bots_partial.append(bot)
        else:
            result.bots_allowed.append(bot)

    result.citation_bots_ok = all(b in result.bots_allowed for b in CITATION_BOTS)

    # #111 — Distingue permesso esplicito da fallback wildcard
    citation_explicit = []
    for bot in CITATION_BOTS:
        bot_status = classify_bot(bot, "", agent_rules)
        if bot_status.status in ("allowed", "partial") and not bot_status.via_wildcard:
            citation_explicit.append(bot)
    result.citation_bots_explicit = len(citation_explicit) == len(CITATION_BOTS)

    return result
