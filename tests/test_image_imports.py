"""Cada imagen instala solo su extra: la API no trae MLflow ni Optuna, el dashboard no trae
LightGBM. Localmente están todos los extras, así que se bloquean a mano para detectar
importaciones que fallarían recién dentro del contenedor."""

import subprocess
import sys

import pytest

CASES = {
    "api": (["mlflow", "optuna", "pandera", "selectolax", "streamlit"],
            "import lima_rent_mlops.serving.api"),
    "dashboard": (["lightgbm", "mlflow", "optuna", "pandera", "scipy", "fastapi"],
                  "import lima_rent_mlops.dashboard.data, lima_rent_mlops.districts"),
}


@pytest.mark.parametrize("image", CASES)
def test_image_imports_only_its_extra(image):
    blocked, statement = CASES[image]
    code = "import sys\n" + "".join(f"sys.modules[{m!r}] = None\n" for m in blocked) + statement
    run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
