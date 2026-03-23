"""
Server MCP per GEO Optimizer.

Espone le funzionalità core come tool MCP utilizzabili da
Claude Code, Cursor, Windsurf e qualsiasi client MCP.

Tool disponibili:
    geo_audit            — Audit GEO completo (score 0-100)
    geo_fix              — Genera fix automatici (robots, llms, schema, meta)
    geo_llms_generate    — Genera contenuto llms.txt da sitemap
    geo_schema_validate  — Valida schema JSON-LD

Resource disponibili:
    geo://ai-bots        — Lista bot AI tracciati
    geo://score-bands    — Fasce di punteggio GEO

Avvio:
    geo-mcp              # Entry point da pyproject.toml
    python -m geo_optimizer.mcp.server  # Diretto
"""

from __future__ import annotations

import json
from dataclasses import asdict
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("geo-optimizer")


# ─── Helper serializzazione ──────────────────────────────────────────────────


def _to_json(data: object) -> str:
    """Serializza dataclass o dict in JSON leggibile."""
    if hasattr(data, "__dataclass_fields__"):
        data = asdict(data)
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def _normalize_url(url: str) -> str:
    """Normalizza URL aggiungendo schema se mancante."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


# ─── Tool 1: geo_audit ───────────────────────────────────────────────────────


@mcp.tool()
def geo_audit(url: str) -> str:
    """Esegue un audit GEO completo su un sito web.

    Analizza 5 aree: robots.txt (accesso bot AI), llms.txt (indice AI),
    schema JSON-LD, meta tag SEO e qualità contenuto.
    Restituisce score 0-100 con dettagli e raccomandazioni.

    Args:
        url: URL del sito da auditare (es. https://example.com)
    """
    from geo_optimizer.utils.validators import validate_public_url

    url = _normalize_url(url)

    # Validazione anti-SSRF
    safe, reason = validate_public_url(url)
    if not safe:
        return json.dumps({"error": f"URL non sicuro: {reason}"})

    try:
        from geo_optimizer.core.audit import run_full_audit

        result = run_full_audit(url)
        return _to_json(result)
    except Exception as e:
        return json.dumps({"error": str(e), "url": url})


# ─── Tool 2: geo_fix ─────────────────────────────────────────────────────────


@mcp.tool()
def geo_fix(url: str, only: str = "") -> str:
    """Genera fix GEO automatici per un sito web.

    Analizza il sito e genera artefatti correttivi:
    - robots.txt con bot AI mancanti
    - llms.txt completo via sitemap
    - Schema JSON-LD mancanti (WebSite, Organization)
    - Meta tag HTML mancanti

    Args:
        url: URL del sito da ottimizzare (es. https://example.com)
        only: Filtra categorie (virgola-separato): robots,llms,schema,meta.
              Vuoto = tutte le categorie.
    """
    from geo_optimizer.utils.validators import validate_public_url

    url = _normalize_url(url)

    safe, reason = validate_public_url(url)
    if not safe:
        return json.dumps({"error": f"URL non sicuro: {reason}"})

    # Parsing filtro categorie
    only_set = None
    if only:
        only_set = {c.strip().lower() for c in only.split(",")}

    try:
        from geo_optimizer.core.fixer import run_all_fixes

        plan = run_all_fixes(url=url, only=only_set)
        return _to_json(plan)
    except Exception as e:
        return json.dumps({"error": str(e), "url": url})


# ─── Tool 3: geo_llms_generate ───────────────────────────────────────────────


@mcp.tool()
def geo_llms_generate(url: str) -> str:
    """Genera il contenuto llms.txt per un sito web.

    llms.txt è il file indice AI alla radice del sito (spec llmstxt.org).
    Scopre il sitemap, categorizza gli URL e genera il file completo
    con header H1, descrizione, sezioni H2 e link markdown.

    Args:
        url: URL base del sito (es. https://example.com)
    """
    from geo_optimizer.utils.validators import validate_public_url

    url = _normalize_url(url)

    safe, reason = validate_public_url(url)
    if not safe:
        return f"Errore: URL non sicuro — {reason}"

    try:
        from geo_optimizer.core.llms_generator import (
            discover_sitemap,
            fetch_sitemap,
            generate_llms_txt,
        )

        parsed = urlparse(url)
        site_name = parsed.netloc.replace("www.", "")

        # Scopri e scarica sitemap
        sitemap_url = discover_sitemap(url)
        urls = []
        if sitemap_url:
            urls = fetch_sitemap(sitemap_url)

        # Genera llms.txt
        content = generate_llms_txt(
            base_url=url,
            urls=urls,
            site_name=site_name,
            description=f"Informazioni su {site_name} per motori di ricerca AI",
        )
        return content
    except Exception as e:
        return f"Errore: {e}"


# ─── Tool 4: geo_schema_validate ─────────────────────────────────────────────


@mcp.tool()
def geo_schema_validate(json_string: str, schema_type: str = "") -> str:
    """Valida uno schema JSON-LD contro i requisiti schema.org.

    Verifica che il JSON-LD contenga tutti i campi obbligatori
    per il tipo schema specificato (es. WebSite, FAQPage, Article).

    Args:
        json_string: Stringa JSON-LD da validare
        schema_type: Tipo schema (es. "website", "faqpage"). Se vuoto, viene rilevato automaticamente.
    """
    try:
        from geo_optimizer.core.schema_validator import validate_jsonld_string

        schema_t = schema_type.strip().lower() if schema_type else None
        is_valid, error_msg = validate_jsonld_string(json_string, schema_t)

        return json.dumps(
            {
                "valid": is_valid,
                "error": error_msg,
                "schema_type": schema_type or "auto-detected",
            }
        )
    except Exception as e:
        return json.dumps({"valid": False, "error": str(e)})


# ─── Resource: AI Bots ────────────────────────────────────────────────────────


@mcp.resource("geo://ai-bots")
def get_ai_bots() -> str:
    """Lista dei 14 bot AI tracciati da GEO Optimizer con descrizioni."""
    from geo_optimizer.models.config import AI_BOTS, CITATION_BOTS

    return json.dumps(
        {
            "ai_bots": AI_BOTS,
            "citation_bots": list(CITATION_BOTS),
            "total": len(AI_BOTS),
        },
        indent=2,
    )


# ─── Resource: Score Bands ────────────────────────────────────────────────────


@mcp.resource("geo://score-bands")
def get_score_bands() -> str:
    """Fasce di punteggio GEO (critical 0-40, foundation 41-70, good 71-90, excellent 91-100)."""
    from geo_optimizer.models.config import SCORE_BANDS

    return json.dumps(SCORE_BANDS, indent=2)


# ─── Entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point per il server MCP (stdio transport)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
