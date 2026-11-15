import importlib.util
import shutil
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("promote_script", ROOT / "scripts" / "promote.py")
promote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(promote)


def _digests(tmp_path: Path) -> Path:
    folder = tmp_path / "digests"
    for i, image in enumerate(promote.IMAGES):
        (folder / f"digest-{image}").mkdir(parents=True)
        digest = "sha256:" + f"{i}" * 64
        (folder / f"digest-{image}" / "image.txt").write_text(
            f"{promote.REGISTRY}{image}@{digest}\n")
    return folder


def test_promote_pins_all_images(tmp_path):
    cortex = tmp_path / "cortex"
    app = cortex / promote.APPLICATION
    app.parent.mkdir(parents=True)
    shutil.copy(ROOT / "deploy" / "argocd" / "lima-rent-application.yaml", app)
    written = promote.promote(ROOT, cortex, promote.read_digests(_digests(tmp_path)))
    overlay = yaml.safe_load(written[0].read_text())
    assert {i["name"].removeprefix(promote.REGISTRY) for i in overlay["images"]} == set(
        promote.IMAGES)
    assert (cortex / promote.APP_DIR / "base" / "pipeline.yaml").exists()


def test_promote_refuses_without_application(tmp_path):
    with pytest.raises(ValueError, match="No existe"):
        promote.promote(ROOT, tmp_path / "cortex", promote.read_digests(_digests(tmp_path)))
