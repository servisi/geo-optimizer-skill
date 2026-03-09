"""
FastAPI app per GEO Optimizer Web Demo.

Endpoint principali:
    GET  /              — Homepage con form di audit
    POST /api/audit     — Esegui audit e ritorna JSON
    GET  /api/audit     — Esegui audit via query param
    GET  /report/{id}   — Report HTML permanente
    GET  /badge          — Badge SVG dinamico
    GET  /health        — Health check
"""

import asyncio
import hashlib
import logging
import os
import secrets
import time
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from geo_optimizer import __version__

logger = logging.getLogger(__name__)

app = FastAPI(
    title="GEO Optimizer",
    description="Audit your website's visibility to AI search engines",
    version=__version__,
    docs_url="/docs",
    redoc_url=None,
)


# ─── Middleware: Limite dimensione body POST ───────────────────────────────────
_MAX_BODY_BYTES = 4 * 1024  # 4 KB — previene DoS con body POST illimitati


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Rifiuta richieste POST con body superiore a _MAX_BODY_BYTES (fix #102)."""

    async def dispatch(self, request: Request, call_next):
        if request.method == "POST":
            content_length = request.headers.get("content-length")
            if content_length is not None:
                # Rifiuta subito se Content-Length supera il limite
                if int(content_length) > _MAX_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": f"Body troppo grande. Limite: {_MAX_BODY_BYTES} byte."},
                    )
        return await call_next(request)


# ─── Middleware: Security Headers ─────────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Aggiunge header di sicurezza HTTP a tutte le risposte.

    Fix #75: usa nonce per script inline invece di 'unsafe-inline'.
    Il nonce viene generato per ogni risposta e inserito nella CSP
    e nella pagina HTML tramite request.state.
    """

    async def dispatch(self, request: Request, call_next):
        # Genera nonce crittograficamente sicuro per ogni richiesta
        nonce = secrets.token_urlsafe(16)
        # Rende il nonce accessibile agli endpoint (es. homepage)
        request.state.csp_nonce = nonce
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Usa 'nonce-{value}' invece di 'unsafe-inline' per la protezione XSS (fix #75)
        response.headers["Content-Security-Policy"] = (
            f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "frame-ancestors 'none'"
        )
        return response


app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# CORS: wildcard "*" va bene per una demo pubblica read-only senza cookie/auth.
# NOTA per produzione: sostituire allow_origins=["*"] con la lista dei domini
# autorizzati (es. ["https://yourdomain.com"]) e valutare allow_credentials.
# Con allow_origins=["*"] NON si può usare allow_credentials=True (violazione CORS spec).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],  # Metodi espliciti, no wildcard
    allow_headers=["Content-Type"],            # Header minimi necessari
    max_age=3600,
)

# ─── Rate Limiter in-memory ───────────────────────────────────────────────────
_rate_limit_store: dict = {}  # {ip: [timestamp, ...]}
_RATE_LIMIT_WINDOW = 60       # secondi
_RATE_LIMIT_MAX_REQUESTS = 30  # richieste per finestra per IP
_RATE_LIMIT_MAX_IPS = 10000   # numero massimo di IP tracciati

# ─── Proxy trust: lista CIDR/IP di proxy fidati ───────────────────────────────
# Configurabile tramite variabile d'ambiente TRUSTED_PROXIES (CSV di IP/CIDR).
# Solo se il proxy è trusted si legge X-Forwarded-For (fix #68).
_TRUSTED_PROXIES: set[str] = set(
    filter(None, os.environ.get("TRUSTED_PROXIES", "").split(","))
)


def _get_client_ip(request: Request) -> str:
    """Estrae l'IP reale del client dalla richiesta.

    - Se request.client è None (ambienti proxy/test), ritorna "unknown" (fix #95).
    - Se il proxy è trusted, legge X-Forwarded-For (fix #68).
    - Altrimenti usa request.client.host direttamente.
    """
    # Fix #95: request.client può essere None in ambienti proxy/test
    proxy_ip = request.client.host if request.client else None

    if proxy_ip is None:
        return "unknown"

    # Fix #68: leggi X-Forwarded-For solo se il proxy è nella lista trusted
    if proxy_ip in _TRUSTED_PROXIES:
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            # Prendi il primo IP della catena (IP originale del client)
            real_ip = forwarded_for.split(",")[0].strip()
            if real_ip:
                return real_ip

    return proxy_ip


def _evict_oldest_rate_limit_entries(count: int = 1) -> None:
    """Rimuove le `count` entry più vecchie dal rate limit store (LRU eviction).

    Fix #70/#99: invece di _rate_limit_store.clear() che azzera tutti,
    rimuoviamo solo le entry con l'ultima richiesta più datata.
    """
    if not _rate_limit_store:
        return
    # Ordina per timestamp dell'ultima richiesta (il più recente nell'array)
    sorted_keys = sorted(
        _rate_limit_store,
        key=lambda ip: _rate_limit_store[ip][-1] if _rate_limit_store[ip] else 0,
    )
    for key in sorted_keys[:count]:
        _rate_limit_store.pop(key, None)


def _check_rate_limit(client_ip: str) -> bool:
    """Verifica rate limit per IP. Ritorna True se consentito."""
    now = time.time()
    timestamps = _rate_limit_store.get(client_ip, [])
    # Rimuovi timestamp fuori finestra temporale
    timestamps = [t for t in timestamps if (now - t) < _RATE_LIMIT_WINDOW]
    if len(timestamps) >= _RATE_LIMIT_MAX_REQUESTS:
        _rate_limit_store[client_ip] = timestamps
        return False
    timestamps.append(now)
    _rate_limit_store[client_ip] = timestamps
    # Fix #70/#99: LRU eviction — rimuovi solo le entry più vecchie, non tutto
    if len(_rate_limit_store) > _RATE_LIMIT_MAX_IPS:
        entries_to_remove = len(_rate_limit_store) - _RATE_LIMIT_MAX_IPS
        _evict_oldest_rate_limit_entries(entries_to_remove)
    return True


# Cache in-memory per risultati audit (TTL 1 ora, max 500 entry)
_audit_cache: dict = {}
_CACHE_TTL = 3600
_MAX_CACHE_SIZE = 500


def _cache_key(url: str) -> str:
    """Genera chiave cache da URL.

    Fix #103: usa i primi 32 caratteri hex (128 bit) invece di 16 (64 bit)
    per ridurre drasticamente il rischio di collisione.
    """
    return hashlib.sha256(url.lower().strip().encode()).hexdigest()[:32]


def _get_cached(url: str) -> Optional[dict]:
    """Recupera risultato dalla cache se valido."""
    key = _cache_key(url)
    entry = _audit_cache.get(key)
    if entry and (time.time() - entry["cached_at"]) < _CACHE_TTL:
        return entry["data"]
    # Rimuovi entry scaduta
    if entry:
        _audit_cache.pop(key, None)
    return None


def _evict_expired() -> None:
    """Rimuovi entry scadute dalla cache."""
    now = time.time()
    expired = [k for k, v in _audit_cache.items() if (now - v["cached_at"]) >= _CACHE_TTL]
    for k in expired:
        _audit_cache.pop(k, None)


def _set_cached(url: str, data: dict) -> str:
    """Salva risultato nella cache con limite dimensione. Ritorna l'ID del report."""
    key = _cache_key(url)
    # Evita crescita illimitata: evict scadute, poi rimuovi le più vecchie
    if len(_audit_cache) >= _MAX_CACHE_SIZE:
        _evict_expired()
    if len(_audit_cache) >= _MAX_CACHE_SIZE:
        oldest_key = min(_audit_cache, key=lambda k: _audit_cache[k]["cached_at"])
        _audit_cache.pop(oldest_key, None)
    _audit_cache[key] = {"data": data, "cached_at": time.time()}
    return key


@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    """Homepage con form per audit GEO."""
    # Fix #75: recupera il nonce CSP impostato dal SecurityHeadersMiddleware
    nonce = getattr(request.state, "csp_nonce", "")
    return _render_homepage(nonce=nonce)


@app.get("/health")
async def health():
    """Health check per monitoring."""
    return {"status": "ok", "version": __version__}


# ─── Modello Pydantic per validazione body POST ───────────────────────────────

class AuditRequest(BaseModel):
    """Schema per il body della richiesta POST /api/audit.

    Fix #149: validazione Pydantic previene crash 500 con input non-stringa
    (es. {"url": 123} ora ritorna 422 Unprocessable Entity invece di 500).
    """

    url: str


@app.get("/api/audit")
async def audit_get(
    request: Request,
    url: str = Query(..., description="URL del sito da analizzare"),
):
    """Esegui audit GEO via GET."""
    # Fix #95: usa _get_client_ip per gestire request.client None e proxy trusted
    if not _check_rate_limit(_get_client_ip(request)):
        raise HTTPException(status_code=429, detail="Troppe richieste. Riprova tra poco.")
    return await _run_audit(url)


@app.post("/api/audit")
async def audit_post(request: Request, body: AuditRequest):
    """Esegui audit GEO via POST (body JSON con campo 'url').

    Fix #149: Pydantic valida il body — url deve essere stringa.
    Fix #95: usa _get_client_ip per gestire request.client None e proxy trusted.
    """
    if not _check_rate_limit(_get_client_ip(request)):
        raise HTTPException(status_code=429, detail="Troppe richieste. Riprova tra poco.")
    return await _run_audit(body.url)


@app.get("/report/{report_id}", response_class=HTMLResponse)
async def report(report_id: str):
    """Report HTML permanente (condivisibile)."""
    # Valida che report_id sia un hash esadecimale valido
    if not report_id.isalnum() or len(report_id) > 64:
        raise HTTPException(status_code=400, detail="ID report non valido")

    entry = _audit_cache.get(report_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Report non trovato o scaduto")

    from geo_optimizer.cli.html_formatter import format_audit_html

    data = entry["data"]
    result = _dict_to_audit_result(data)
    return HTMLResponse(content=format_audit_html(result))


@app.get("/badge")
async def badge(
    request: Request,
    url: str = Query(..., description="URL del sito per il badge"),
    label: str = Query("GEO Score", max_length=50, description="Etichetta lato sinistro"),
):
    """Badge SVG dinamico con GEO Score (stile Shields.io).

    Uso in Markdown:
        ![GEO Score](https://geo.example.com/badge?url=https://yoursite.com)
    """
    from fastapi.responses import Response

    from geo_optimizer.utils.validators import validate_public_url

    # Fix #95: usa _get_client_ip per gestire request.client None e proxy trusted
    if not _check_rate_limit(_get_client_ip(request)):
        raise HTTPException(status_code=429, detail="Troppe richieste. Riprova tra poco.")

    # Normalizza URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Validazione anti-SSRF
    safe, reason = validate_public_url(url)
    if not safe:
        raise HTTPException(status_code=400, detail=f"URL non sicuro: {reason}")

    # Controlla cache o esegui audit
    cached = _get_cached(url)
    if cached:
        score = cached.get("score", 0)
        band = cached.get("band", "critical")
    else:
        try:
            from geo_optimizer.core.audit import run_full_audit

            # Esegui in thread separato per non bloccare l'event loop
            result = await asyncio.to_thread(run_full_audit, url)
            data = _audit_result_to_dict(result)
            _set_cached(url, data)
            score = data["score"]
            band = data["band"]
        except Exception:
            # In caso di errore, mostra badge con score 0
            score = 0
            band = "critical"

    from geo_optimizer.web.badge import generate_badge_svg

    svg = generate_badge_svg(score, band, label=label)
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=3600",
            "ETag": f'"{_cache_key(url)}-{score}"',
        },
    )


async def _run_audit(url: str) -> JSONResponse:
    """Logica comune per eseguire un audit."""
    from geo_optimizer.utils.validators import validate_public_url

    # Normalizza URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Validazione anti-SSRF
    safe, reason = validate_public_url(url)
    if not safe:
        raise HTTPException(status_code=400, detail=f"URL non sicuro: {reason}")

    # Controlla cache
    cached = _get_cached(url)
    if cached:
        report_id = _cache_key(url)
        response_data = dict(cached)
        response_data["report_url"] = f"/report/{report_id}"
        return JSONResponse(content=response_data)

    # Esegui audit
    try:
        from geo_optimizer.core.audit import run_full_audit

        # Esegui in thread separato per non bloccare l'event loop
        result = await asyncio.to_thread(run_full_audit, url)
    except Exception as e:
        logger.error("Errore audit per %s: %s", url, e)
        raise HTTPException(
            status_code=500,
            detail="Errore interno durante l'audit. Riprova più tardi.",
        )

    # Serializza risultato
    data = _audit_result_to_dict(result)

    # Salva in cache
    report_id = _set_cached(url, data)
    data["report_url"] = f"/report/{report_id}"

    return JSONResponse(content=data)


def _audit_result_to_dict(result) -> dict:
    """Converte AuditResult in dizionario serializzabile."""
    return {
        "url": result.url,
        "score": result.score,
        "band": result.band,
        "timestamp": result.timestamp,
        "http_status": result.http_status,
        "page_size": result.page_size,
        "checks": {
            "robots_txt": {
                "found": result.robots.found,
                "citation_bots_ok": result.robots.citation_bots_ok,
                "bots_allowed": result.robots.bots_allowed,
                "bots_blocked": result.robots.bots_blocked,
                "bots_missing": result.robots.bots_missing,
            },
            "llms_txt": {
                "found": result.llms.found,
                "has_h1": result.llms.has_h1,
                "has_sections": result.llms.has_sections,
                "has_links": result.llms.has_links,
                "word_count": result.llms.word_count,
            },
            "schema_jsonld": {
                "found_types": result.schema.found_types,
                "has_website": result.schema.has_website,
                "has_faq": result.schema.has_faq,
                "has_webapp": result.schema.has_webapp,
            },
            "meta_tags": {
                "has_title": result.meta.has_title,
                "has_description": result.meta.has_description,
                "has_canonical": result.meta.has_canonical,
                "has_og_title": result.meta.has_og_title,
                "has_og_description": result.meta.has_og_description,
                "title_text": result.meta.title_text,
                "description_length": result.meta.description_length,
            },
            "content": {
                "has_h1": result.content.has_h1,
                "heading_count": result.content.heading_count,
                "has_numbers": result.content.has_numbers,
                "has_links": result.content.has_links,
                "word_count": result.content.word_count,
            },
        },
        "recommendations": result.recommendations,
    }


def _dict_to_audit_result(data: dict):
    """Ricostruisce AuditResult da dizionario (per report HTML)."""
    from geo_optimizer.models.results import (
        AuditResult,
        ContentResult,
        LlmsTxtResult,
        MetaResult,
        RobotsResult,
        SchemaResult,
    )

    checks = data.get("checks", {})
    r = checks.get("robots_txt", {})
    ll = checks.get("llms_txt", {})
    s = checks.get("schema_jsonld", {})
    m = checks.get("meta_tags", {})
    c = checks.get("content", {})

    return AuditResult(
        url=data.get("url", ""),
        score=data.get("score", 0),
        band=data.get("band", "critical"),
        robots=RobotsResult(
            found=r.get("found", False),
            citation_bots_ok=r.get("citation_bots_ok", False),
            bots_allowed=r.get("bots_allowed", []),
            bots_blocked=r.get("bots_blocked", []),
            bots_missing=r.get("bots_missing", []),
        ),
        llms=LlmsTxtResult(
            found=ll.get("found", False),
            has_h1=ll.get("has_h1", False),
            has_sections=ll.get("has_sections", False),
            has_links=ll.get("has_links", False),
            word_count=ll.get("word_count", 0),
        ),
        schema=SchemaResult(
            found_types=s.get("found_types", []),
            has_website=s.get("has_website", False),
            has_faq=s.get("has_faq", False),
            has_webapp=s.get("has_webapp", False),
        ),
        meta=MetaResult(
            has_title=m.get("has_title", False),
            has_description=m.get("has_description", False),
            has_canonical=m.get("has_canonical", False),
            has_og_title=m.get("has_og_title", False),
            has_og_description=m.get("has_og_description", False),
            title_text=m.get("title_text", ""),
            description_length=m.get("description_length", 0),
        ),
        content=ContentResult(
            has_h1=c.get("has_h1", False),
            heading_count=c.get("heading_count", 0),
            has_numbers=c.get("has_numbers", False),
            has_links=c.get("has_links", False),
            word_count=c.get("word_count", 0),
        ),
        recommendations=data.get("recommendations", []),
        http_status=data.get("http_status", 0),
        page_size=data.get("page_size", 0),
    )


def _render_homepage(nonce: str = "") -> str:
    """Genera HTML homepage con form di audit.

    Fix #75: accetta il nonce CSP per il tag <script> inline.
    Nota: il frontend usa textContent per i dati dell'audit
    per prevenire XSS. Solo struttura HTML statica viene costruita
    con metodi DOM sicuri.
    """
    # Usa "__NONCE_ATTR__" come placeholder nell'HTML — sostituito a fine funzione.
    # Evita f-string sull'intero HTML perché { } in CSS/JS causerebbero conflitti.
    nonce_attr = f' nonce="{nonce}"' if nonce else ""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GEO Optimizer — AI Search Visibility Audit</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
background:#0f172a;color:#e2e8f0;min-height:100vh;display:flex;flex-direction:column;
align-items:center;justify-content:center;padding:2rem}
.container{max-width:600px;width:100%;text-align:center}
h1{font-size:2.5rem;margin-bottom:.5rem;background:linear-gradient(135deg,#60a5fa,#a78bfa);
-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.subtitle{color:#94a3b8;margin-bottom:2rem;font-size:1.1rem}
.form-group{display:flex;gap:.5rem;margin-bottom:1.5rem}
input[type="url"]{flex:1;padding:.75rem 1rem;border:2px solid #334155;border-radius:8px;
background:#1e293b;color:#e2e8f0;font-size:1rem;outline:none;transition:border-color .2s}
input[type="url"]:focus{border-color:#60a5fa}
button{padding:.75rem 1.5rem;border:none;border-radius:8px;background:#3b82f6;
color:#fff;font-size:1rem;font-weight:600;cursor:pointer;transition:background .2s}
button:hover{background:#2563eb}
button:disabled{opacity:.5;cursor:not-allowed}
.result{background:#1e293b;border-radius:12px;padding:1.5rem;margin-top:1rem;
text-align:left;display:none}
.score-display{text-align:center;margin:1rem 0}
.score-number{font-size:3rem;font-weight:700}
.score-band{font-size:1.2rem;font-weight:600;margin-top:.25rem}
.checks{margin:1rem 0}
.check-row{display:flex;justify-content:space-between;padding:.5rem 0;
border-bottom:1px solid #334155}
.recs{margin-top:1rem}
.recs li{margin:.25rem 0;color:#94a3b8}
.links{margin-top:2rem;color:#64748b;font-size:.85rem}
.links a{color:#60a5fa;text-decoration:none}
.spinner{display:none;margin:1rem auto}
.spinner.active{display:block}
.error{color:#ef4444;margin-top:1rem;display:none}
.report-link{margin-top:1rem;text-align:center}
.report-link a{color:#60a5fa;text-decoration:none;font-size:.9rem}
</style>
</head>
<body>
<div class="container">
    <h1>GEO Optimizer</h1>
    <p class="subtitle">Audit your website's visibility to AI search engines</p>

    <div class="form-group">
        <input type="url" id="url-input" placeholder="https://example.com" required>
        <button id="btn" onclick="runAudit()">Audit</button>
    </div>

    <div class="spinner" id="spinner">Analyzing...</div>
    <div class="error" id="error"></div>

    <div class="result" id="result">
        <div class="score-display">
            <div class="score-number" id="score"></div>
            <div class="score-band" id="band"></div>
        </div>
        <div class="checks" id="checks"></div>
        <div class="recs"><ol id="recs"></ol></div>
        <div class="report-link" id="report-link"></div>
    </div>

    <div class="links">
        <p>CLI: <code>pip install geo-optimizer-skill</code></p>
        <p><a href="https://github.com/auriti-labs/geo-optimizer-skill">GitHub</a> &middot;
           <a href="/docs">API Docs</a></p>
    </div>
</div>

<script__NONCE_ATTR__>
async function runAudit() {
    const url = document.getElementById('url-input').value;
    if (!url) return;

    const btn = document.getElementById('btn');
    const spinner = document.getElementById('spinner');
    const errorEl = document.getElementById('error');
    const resultEl = document.getElementById('result');

    btn.disabled = true;
    spinner.classList.add('active');
    errorEl.style.display = 'none';
    resultEl.style.display = 'none';

    try {
        const res = await fetch('/api/audit?url=' + encodeURIComponent(url));
        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.detail || 'Errore audit');
        }

        const colors = {excellent:'#22c55e',good:'#06b6d4',foundation:'#eab308',critical:'#ef4444'};
        const color = colors[data.band] || '#888';

        // Usa textContent per prevenire XSS
        const scoreEl = document.getElementById('score');
        scoreEl.textContent = data.score + '/100';
        scoreEl.style.color = color;

        const bandEl = document.getElementById('band');
        bandEl.textContent = data.band.toUpperCase();
        bandEl.style.color = color;

        // Costruisci check rows con metodi DOM sicuri
        const checksEl = document.getElementById('checks');
        checksEl.textContent = '';
        const checkNames = {robots_txt:'Robots.txt',llms_txt:'llms.txt',
            schema_jsonld:'Schema JSON-LD',meta_tags:'Meta Tags',content:'Content Quality'};
        const checks = data.checks;
        for (const [key, label] of Object.entries(checkNames)) {
            const c = checks[key];
            const ok = key === 'robots_txt' ? c.citation_bots_ok :
                       key === 'llms_txt' ? c.found :
                       key === 'schema_jsonld' ? c.has_website :
                       key === 'meta_tags' ? (c.has_title && c.has_description) :
                       c.has_h1;
            const row = document.createElement('div');
            row.className = 'check-row';
            const nameSpan = document.createElement('span');
            nameSpan.textContent = label;
            const statusSpan = document.createElement('span');
            statusSpan.textContent = ok ? '\\u2705' : '\\u274c';
            row.appendChild(nameSpan);
            row.appendChild(statusSpan);
            checksEl.appendChild(row);
        }

        // Raccomandazioni con metodi DOM sicuri
        const recsEl = document.getElementById('recs');
        recsEl.textContent = '';
        for (const rec of data.recommendations) {
            const li = document.createElement('li');
            li.textContent = rec;
            recsEl.appendChild(li);
        }

        // Link report con metodi DOM sicuri
        const reportLinkEl = document.getElementById('report-link');
        reportLinkEl.textContent = '';
        if (data.report_url) {
            const a = document.createElement('a');
            a.href = data.report_url;
            a.target = '_blank';
            a.rel = 'noopener';
            a.textContent = 'View full HTML report';
            reportLinkEl.appendChild(a);
        }

        resultEl.style.display = 'block';
    } catch (e) {
        errorEl.textContent = e.message;
        errorEl.style.display = 'block';
    } finally {
        btn.disabled = false;
        spinner.classList.remove('active');
    }
}

document.getElementById('url-input').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') runAudit();
});
</script>
</body>
</html>"""
    # Fix #75: sostituisce il placeholder con l'attributo nonce reale
    return html.replace("__NONCE_ATTR__", nonce_attr)
