"""Línea de comandos: `lima-rent <comando>`."""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import UTC, datetime, timedelta

from .config import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lima-rent", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    weekly = sub.add_parser("weekly", help="Corrida semanal completa (scraping → modelo)")
    weekly.add_argument("--max-pages", type=int, help="Límite de páginas (pruebas)")
    # También por variable de entorno: en el clúster es más fácil agregar una variable a un Job
    # que cambiar sus argumentos (ver docs/despliegue.md).
    weekly.add_argument("--retrain", metavar="RAZON", default=os.environ.get("FORCE_RETRAIN"),
                        help="Fuerza un reentrenamiento (o FORCE_RETRAIN=razón)")
    weekly.add_argument("--fixture", type=int, metavar="N",
                        help="Usa N avisos sintéticos en vez de scrapear (sin internet)")
    weekly.add_argument("--fixture-shift", type=float, default=0.0,
                        help="Desplazamiento de los datos sintéticos para simular drift")
    weekly.add_argument("--fixture-seed", type=int, default=0)
    weekly.add_argument("--fixture-days-ago", type=int, default=0,
                        help="Fecha simulada del scraping (días atrás)")

    scrape = sub.add_parser("scrape", help="Solo scraping, guarda en bronze/")
    scrape.add_argument("--max-pages", type=int)

    sub.add_parser("context", help="Actualiza las series del BCRP y la ENAHO")
    sub.add_parser("status", help="Muestra el resumen de la última corrida")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()

    if args.command == "weekly":
        raw = fx = None
        if args.fixture:
            from .fixture import make_fx, make_raw

            when = datetime.now(UTC) - timedelta(days=args.fixture_days_ago)
            raw = make_raw(args.fixture, seed=args.fixture_seed, scraped_at=when,
                           shift=args.fixture_shift, id_offset=args.fixture_seed * 100_000)
            fx = make_fx(when.date() - timedelta(days=30), when.date())
        from .pipeline import run_weekly

        summary = run_weekly(settings, raw=raw, fx=fx, max_pages=args.max_pages,
                             force_retrain=args.retrain)
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    elif args.command == "scrape":
        from .sources import infocasas
        from .storage import Storage

        df = infocasas.scrape(settings, args.max_pages)
        day = df["fecha_scraping"].iloc[0][:10]
        Storage(settings).write_parquet(df, f"bronze/infocasas/fecha={day}/listings.parquet")
        print(f"{len(df)} avisos guardados")
    elif args.command == "context":
        from .pipeline import refresh_context
        from .storage import Storage

        refresh_context(Storage(settings))
    elif args.command == "status":
        from .storage import Storage

        print(json.dumps(Storage(settings).read_json("monitoring/last_run.json", {}),
                         ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
