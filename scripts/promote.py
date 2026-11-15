"""Promoción GitOps: copia los manifiestos a K3s-Cortex y fija los digests publicados.

Mismo patrón que peru-spend-tracker. No contacta el clúster: el workflow de imágenes hace commit
en K3s-Cortex y Argo CD aplica el cambio al recibir el webhook de GitHub.
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

import yaml

APP_DIR = "apps/lima-rent-mlops"
APPLICATION = "clusters/rnz-prod/lima-rent-application.yaml"
APPLICATION_NAME = "lima-rent-prod"
CORTEX_REPO = "https://github.com/RenzoAL7/K3s-Cortex.git"
REGISTRY = "ghcr.io/renzoal7/lima-rent-"
IMAGES = ("api", "dashboard", "pipeline", "mlflow")
DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
HEADER = "# Generado por scripts/promote.py de RenzoAL7/lima-rent-mlops. No editar a mano.\n"


def read_digests(folder: Path) -> dict[str, str]:
    """Lee el image.txt que deja cada imagen del workflow, con la forma nombre@digest."""
    digests = {}
    for path in sorted(folder.glob("*/image.txt")):
        name, _, digest = path.read_text().strip().partition("@")
        digests[name.removeprefix(REGISTRY)] = digest
    return digests


def check_digests(digests: dict[str, str]) -> None:
    missing = [image for image in IMAGES if not DIGEST.match(digests.get(image, ""))]
    if missing:
        raise ValueError(f"Faltan digests válidos para: {', '.join(missing)}")


def check_application(cortex: Path) -> None:
    """Se niega a tocar Cortex si la Application de Argo CD no es la de este proyecto."""
    path = cortex / APPLICATION
    if not path.exists():
        raise ValueError(
            f"No existe {APPLICATION} en K3s-Cortex. Cópialo desde "
            "deploy/argocd/lima-rent-application.yaml (ver docs/despliegue.md)."
        )
    application = yaml.safe_load(path.read_text()) or {}
    source = application.get("spec", {}).get("source", {})
    if (
        application.get("metadata", {}).get("name") != APPLICATION_NAME
        or source.get("repoURL") != CORTEX_REPO
        or not str(source.get("path", "")).startswith(f"{APP_DIR}/overlays/")
    ):
        raise ValueError("La Application de Argo CD no es la esperada; no se modifica nada")


def pin_overlay(overlay: dict, digests: dict[str, str]) -> dict:
    pinned = dict(overlay)
    pinned["images"] = [
        {"name": f"{REGISTRY}{image}", "digest": digests[image]} for image in IMAGES
    ]
    return pinned


def promote(repo: Path, cortex: Path, digests: dict[str, str]) -> list[Path]:
    check_digests(digests)
    check_application(cortex)
    source = repo / "deploy" / "k3s"
    target = cortex / APP_DIR
    # La base se reemplaza entera para que un manifiesto borrado aquí también desaparezca allá.
    shutil.rmtree(target / "base", ignore_errors=True)
    shutil.copytree(source / "base", target / "base")
    written = []
    for overlay_file in sorted((source / "overlays").glob("*/kustomization.yaml")):
        overlay = yaml.safe_load(overlay_file.read_text())
        output = target / "overlays" / overlay_file.parent.name / "kustomization.yaml"
        output.parent.mkdir(parents=True, exist_ok=True)
        pinned = pin_overlay(overlay, digests)
        output.write_text(HEADER + yaml.safe_dump(pinned, sort_keys=False, allow_unicode=True))
        written.append(output)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cortex", type=Path, help="Copia local de RenzoAL7/K3s-Cortex")
    parser.add_argument("digests", type=Path, help="Carpeta con un image.txt por imagen")
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    for path in promote(repo, args.cortex, read_digests(args.digests)):
        print(f"Fijado {path.relative_to(args.cortex)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
