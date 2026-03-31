"""Audit WebMCP Readiness — agent-readiness signals per AI e MCP (#233).

Estratto da audit.py per separazione delle responsabilità.
Zero fetch HTTP — lavora solo su dati già disponibili.
"""

from __future__ import annotations

import json  # noqa: F401 (disponibile per future estensioni)
import re  # noqa: F401 (disponibile per future estensioni)

from geo_optimizer.models.results import WebMcpResult


def _extract_actions(schema_obj, action_types: set) -> None:
    """Estrae potentialAction da un oggetto schema JSON-LD (ricorsivo).

    Args:
        schema_obj: Oggetto schema (dict, list o valore primitivo).
        action_types: Set in cui aggiungere i tipi azione trovati.
    """
    if isinstance(schema_obj, dict):
        # Supporta @graph (Yoast SEO, RankMath)
        if "@graph" in schema_obj:
            for item in schema_obj["@graph"]:
                _extract_actions(item, action_types)
            return

        potential = schema_obj.get("potentialAction")
        if potential:
            if isinstance(potential, dict):
                action_type = potential.get("@type", "")
                if action_type:
                    action_types.add(action_type)
            elif isinstance(potential, list):
                for action in potential:
                    if isinstance(action, dict):
                        action_type = action.get("@type", "")
                        if action_type:
                            action_types.add(action_type)
    elif isinstance(schema_obj, list):
        for item in schema_obj:
            _extract_actions(item, action_types)


def audit_webmcp_readiness(soup, raw_html: str, schema_result) -> WebMcpResult:
    """Verifica WebMCP readiness e agent-readiness signals (#233).

    Analizza:
    1. WebMCP API: registerTool(), attributi toolname/tooldescription
    2. Schema potentialAction: SearchAction, BuyAction, OrderAction
    3. Form accessibili: form con label + aria-label/placeholder
    4. OpenAPI: link a /api-docs, /swagger, openapi.json

    Zero fetch HTTP — lavora solo su dati già disponibili.

    Args:
        soup: BeautifulSoup della pagina.
        raw_html: HTML grezzo della pagina.
        schema_result: SchemaResult con gli schema JSON-LD trovati.

    Returns:
        WebMcpResult con i segnali di readiness rilevati.
    """
    result = WebMcpResult()
    if soup is None or not raw_html:
        return result

    result.checked = True

    # ── 1. WebMCP Detection ──────────────────────────────────────
    # API imperativa: navigator.modelContext.registerTool()
    if "modelContext" in raw_html and "registerTool" in raw_html:
        result.has_register_tool = True

    # API dichiarativa: attributi toolname/tooldescription sugli elementi HTML
    tool_elements = soup.find_all(attrs={"toolname": True})
    if tool_elements:
        result.has_tool_attributes = True
        result.tool_count = len(tool_elements)

    # ── 2. Schema potentialAction ────────────────────────────────
    action_types: set = set()
    for raw_schema in schema_result.raw_schemas:
        _extract_actions(raw_schema, action_types)

    if action_types:
        result.has_potential_action = True
        result.potential_actions = sorted(action_types)

    # ── 3. Form accessibili (usabili da agent) ───────────────────
    forms = soup.find_all("form")
    labeled_count = 0
    for form in forms:
        # Un form è "agent-usable" se ha:
        # - almeno 1 input con label associata OPPURE aria-label OPPURE placeholder descrittivo
        # - una action o method definiti
        inputs = form.find_all(["input", "select", "textarea"])
        has_labels = False
        for inp in inputs:
            inp_type = (inp.get("type") or "text").lower()
            if inp_type in ("hidden", "submit", "button"):
                continue
            # Label associata via for/id
            inp_id = inp.get("id")
            if inp_id and form.find("label", attrs={"for": inp_id}):
                has_labels = True
                break
            # aria-label o placeholder
            if inp.get("aria-label") or inp.get("placeholder"):
                has_labels = True
                break
        if has_labels and len(inputs) > 0:
            labeled_count += 1

    if labeled_count > 0:
        result.has_labeled_forms = True
        result.labeled_forms_count = labeled_count

    # ── 4. Rilevazione OpenAPI/Swagger ───────────────────────────
    openapi_patterns = ["/api-docs", "/swagger", "openapi.json", "openapi.yaml", "swagger.json"]
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].lower()
        if any(pattern in href for pattern in openapi_patterns):
            result.has_openapi = True
            break
    # Controlla anche tag link
    if not result.has_openapi:
        for link in soup.find_all("link", href=True):
            href = link["href"].lower()
            if any(pattern in href for pattern in openapi_patterns):
                result.has_openapi = True
                break

    # ── Livello di readiness ─────────────────────────────────────
    webmcp_signals = sum([result.has_register_tool, result.has_tool_attributes])
    agent_signals = sum([result.has_potential_action, result.has_labeled_forms, result.has_openapi])

    if webmcp_signals > 0 and agent_signals >= 2:
        result.readiness_level = "advanced"
        result.agent_ready = True
    elif webmcp_signals > 0 or agent_signals >= 2:
        result.readiness_level = "ready"
        result.agent_ready = True
    elif agent_signals >= 1:
        result.readiness_level = "basic"
    else:
        result.readiness_level = "none"

    return result
