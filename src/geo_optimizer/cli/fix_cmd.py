"""
CLI command: geo fix

Genera automaticamente artefatti GEO mancanti basandosi sull'audit.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from geo_optimizer.utils.validators import validate_public_url


@click.command()
@click.option("--url", required=True, help="URL del sito da ottimizzare")
@click.option(
    "--output-dir",
    default="./geo-fixes",
    help="Directory di output per i file generati (default: ./geo-fixes/)",
)
@click.option("--dry-run", is_flag=True, default=True, help="Mostra preview senza scrivere (default)")
@click.option("--apply", "do_apply", is_flag=True, help="Scrivi i file generati nella directory di output")
@click.option(
    "--only",
    default=None,
    help="Filtra categorie: robots,llms,schema,meta (separate da virgola)",
)
@click.option("--config", "config_file", default=None, help="Percorso .geo-optimizer.yml")
def fix(url, output_dir, dry_run, do_apply, only, config_file):
    """Genera automaticamente fix GEO per il sito."""
    # Se --apply è specificato, disabilita dry-run
    if do_apply:
        dry_run = False

    # Validazione anti-SSRF
    safe_url = url if url.startswith(("http://", "https://")) else f"https://{url}"
    safe, reason = validate_public_url(safe_url)
    if not safe:
        click.echo(f"\n❌ URL non sicuro: {reason}", err=True)
        sys.exit(1)

    # Parsing filtro --only
    only_set = None
    if only:
        only_set = {c.strip().lower() for c in only.split(",")}
        valid_categories = {"robots", "llms", "schema", "meta"}
        invalid = only_set - valid_categories
        if invalid:
            click.echo(f"❌ Categorie non valide: {', '.join(invalid)}", err=True)
            click.echo(f"   Categorie valide: {', '.join(sorted(valid_categories))}", err=True)
            sys.exit(1)

    # Esegui audit
    click.echo("⏳ Esecuzione audit GEO...", err=True)
    from geo_optimizer.core.audit import run_full_audit

    # Carica configurazione progetto
    from geo_optimizer.models.project_config import load_config

    config_path = Path(config_file) if config_file else None
    project_config = load_config(config_path)

    result = run_full_audit(safe_url, project_config=project_config)
    click.echo(f"📊 Score attuale: {result.score}/100 ({result.band})\n", err=True)

    # Genera fix
    click.echo("🔧 Generazione fix...\n", err=True)
    from geo_optimizer.core.fixer import run_all_fixes

    plan = run_all_fixes(url=safe_url, audit_result=result, only=only_set)

    if not plan.fixes:
        click.echo("✅ Nessun fix necessario — il sito è già ottimizzato!")
        return

    # Mostra piano
    click.echo(f"📋 Piano fix — {len(plan.fixes)} correzioni trovate:\n")

    for i, fix_item in enumerate(plan.fixes, 1):
        action_label = {"create": "CREA", "append": "AGGIUNGI", "snippet": "SNIPPET"}.get(fix_item.action, "FIX")
        click.echo(f"  {i}. [{action_label}] {fix_item.description}")
        click.echo(f"     → {fix_item.file_name}")

    if plan.skipped:
        click.echo(f"\n  Saltati: {len(plan.skipped)}")
        for s in plan.skipped:
            click.echo(f"    - {s}")

    click.echo(f"\n📈 Score stimato dopo i fix: {plan.score_before}/100 → {plan.score_estimated_after}/100")

    if dry_run:
        # Mostra preview del contenuto
        click.echo("\n" + "=" * 60)
        click.echo("PREVIEW (usa --apply per scrivere i file)")
        click.echo("=" * 60)

        for fix_item in plan.fixes:
            click.echo(f"\n{'─' * 40}")
            click.echo(f"📄 {fix_item.file_name} ({fix_item.action})")
            click.echo(f"{'─' * 40}")
            # Mostra prime 30 righe per file lunghi
            lines = fix_item.content.split("\n")
            if len(lines) > 30:
                click.echo("\n".join(lines[:30]))
                click.echo(f"\n  ... ({len(lines) - 30} righe rimanenti)")
            else:
                click.echo(fix_item.content)

        click.echo(f"\n💡 Esegui: geo fix --url {url} --apply")
    else:
        # Scrivi file
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        for fix_item in plan.fixes:
            file_path = output_path / fix_item.file_name
            file_path.write_text(fix_item.content, encoding="utf-8")
            click.echo(f"  ✅ {file_path}")

        click.echo(f"\n✅ {len(plan.fixes)} file scritti in {output_path}/")
        click.echo(f"📈 Score stimato: {plan.score_before}/100 → {plan.score_estimated_after}/100")
