from datetime import timedelta

import pandas as pd
import pytest
from pandera.errors import SchemaErrors

from lima_rent_mlops.fixture import make_raw
from lima_rent_mlops.processing import schemas
from lima_rent_mlops.processing.clean import clean_snapshot, update_history


def test_clean_converts_usd_and_filters(raw, fx):
    clean, report = clean_snapshot(raw, fx)
    assert report["fuera_de_lima"] > 0 and report["fuera_de_rango_area_m2"] > 0
    assert clean["distrito"].notna().all()
    usd = clean[clean["moneda"] == "USD"].iloc[0]
    assert usd["precio_pen"] == pytest.approx(usd["precio"] * 3.4)
    assert clean["precio_m2_pen"].between(5, 250).all()


def test_history_marks_only_new_listings(raw, fx, scraped_at):
    first, _ = clean_snapshot(raw, fx)
    history, new = update_history(pd.DataFrame(), first)
    assert len(new) == len(history) == len(first)

    later = scraped_at + timedelta(days=7)
    again = make_raw(500, seed=0, scraped_at=later)  # mismos ids
    extra = make_raw(50, seed=1, scraped_at=later, id_offset=10_000)
    second, _ = clean_snapshot(pd.concat([again, extra]), fx)
    history2, new2 = update_history(history, second)
    assert set(new2["id"]) <= set(extra["id"])
    assert len(history2) == len(history) + len(new2)
    # La primera observación no se pisa; la última vez visto sí avanza.
    kept = history2.set_index("id").loc[history["id"]]
    assert (kept["primera_vez_visto"] < kept["ultima_vez_visto"]).all()


def test_silver_schema_rejects_bad_rows(raw, fx):
    clean, _ = clean_snapshot(raw, fx)
    history, _ = update_history(pd.DataFrame(), clean)
    broken = history.copy()
    broken.loc[broken.index[0], "distrito"] = "Arequipa"
    with pytest.raises(SchemaErrors):
        schemas.SILVER.validate(broken, lazy=True)
