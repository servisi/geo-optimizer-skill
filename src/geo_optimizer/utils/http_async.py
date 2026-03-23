"""
Client HTTP asincrono con httpx per fetch parallelo.

Velocizza l'audit eseguendo robots.txt, llms.txt e homepage in parallelo
(speedup 2-3x rispetto al fetch sequenziale con requests).

Implementa protezione anti-SSRF con redirect manuale: ogni redirect
viene rivalidato con validate_public_url() prima di seguirlo (fix #179).

Richiede httpx come dipendenza opzionale:
    pip install geo-optimizer-skill[async]
"""

from __future__ import annotations

import asyncio

from geo_optimizer.models.config import HEADERS
from geo_optimizer.utils.http import MAX_RESPONSE_SIZE

# Numero massimo di redirect da seguire manualmente
_MAX_REDIRECTS = 10


def is_httpx_available() -> bool:
    """Verifica se httpx è installato."""
    try:
        import httpx  # noqa: F401

        return True
    except ImportError:
        return False


async def fetch_url_async(
    url: str,
    client=None,
    timeout: int = 10,
    max_size: int = MAX_RESPONSE_SIZE,
) -> tuple[object | None, str | None]:
    """Fetch asincrono di un URL con httpx.

    Implementa validazione anti-SSRF completa:
    - Ogni URL viene verificato con validate_public_url() prima del fetch
    - I redirect vengono seguiti manualmente con rivalidazione SSRF su ogni hop
    - Dimensione risposta verificata contro max_size

    Args:
        url: URL da scaricare.
        client: httpx.AsyncClient opzionale (riutilizza connessioni).
        timeout: Timeout in secondi.
        max_size: Dimensione massima risposta in bytes.

    Returns:
        Tupla (response, error_msg) — response è None in caso di errore.
    """
    from geo_optimizer.utils.validators import validate_public_url

    # Validazione anti-SSRF prima di qualsiasi fetch
    safe, reason = validate_public_url(url)
    if not safe:
        return None, f"Unsafe URL: {reason}"

    import httpx

    own_client = client is None

    try:
        if own_client:
            client = httpx.AsyncClient(
                headers=HEADERS,
                follow_redirects=False,  # Redirect manuale con rivalidazione SSRF (fix #179)
                timeout=httpx.Timeout(timeout),
            )

        # Redirect manuale con rivalidazione anti-SSRF su ogni hop
        current_url = url
        for _ in range(_MAX_REDIRECTS):
            r = await client.get(current_url)

            # Risposta non-redirect: verifica dimensione e ritorna
            if r.status_code not in (301, 302, 303, 307, 308):
                content_length = r.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > max_size:
                            return None, f"Response too large: {int(content_length)} bytes (max: {max_size})"
                    except (ValueError, TypeError):
                        pass

                if len(r.content) > max_size:
                    return None, f"Response too large: {len(r.content)} bytes (max: {max_size})"

                return r, None

            # Redirect: rivalida il target URL prima di seguirlo
            location = r.headers.get("location", "").strip()
            if not location:
                return None, "Redirect without Location header"

            # Risolvi URL relativo
            if not location.startswith(("http://", "https://")):
                from urllib.parse import urljoin

                location = urljoin(current_url, location)

            safe, reason = validate_public_url(location)
            if not safe:
                return None, f"Redirect to unsafe URL: {reason}"

            current_url = location

        return None, f"Too many redirects (max: {_MAX_REDIRECTS})"

    except httpx.TimeoutException:
        return None, f"Timeout ({timeout}s)"
    except httpx.ConnectError as e:
        return None, f"Connection failed: {e}"
    except Exception as e:
        return None, str(e)
    finally:
        if own_client and client:
            await client.aclose()


async def fetch_urls_async(
    urls: list,
    timeout: int = 10,
    max_size: int = MAX_RESPONSE_SIZE,
) -> dict:
    """Fetch parallelo di più URL con un singolo client httpx.

    Args:
        urls: Lista di URL da scaricare.
        timeout: Timeout per singola richiesta.
        max_size: Dimensione massima per risposta.

    Returns:
        Dict {url: (response, error_msg)} per ogni URL.
    """
    import httpx

    results = {}

    async with httpx.AsyncClient(
        headers=HEADERS,
        follow_redirects=False,  # Redirect gestito in fetch_url_async (fix #179)
        timeout=httpx.Timeout(timeout),
    ) as client:
        tasks = {url: fetch_url_async(url, client=client, timeout=timeout, max_size=max_size) for url in urls}

        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)

        for url, result in zip(tasks.keys(), gathered):
            if isinstance(result, Exception):
                results[url] = (None, str(result))
            else:
                results[url] = result

    return results
