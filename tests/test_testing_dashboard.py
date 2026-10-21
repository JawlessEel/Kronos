"""
Automated tests for the Kronos Multi-Model Testing Dashboard,
Polygon Options Chain & Underlying Intelligence, and PostgreSQL (`kronos_research`) persistence.
"""
from types import SimpleNamespace
import pandas as pd
import pytest
from flask import Flask

from webui import app as ui
from webui import db_store
from webui.db_store import KronosResearchDB
from webui.options_service import _calculate_max_pain, validate_equity_ticker
from webui.polygon_feed import FeedError
from webui.testing_suite import discover_and_register_models, register_testing_suite


def test_validate_equity_ticker():
    assert validate_equity_ticker("spy") == "SPY"
    assert validate_equity_ticker("I:VIX") == "VIX"
    with pytest.raises(FeedError):
        validate_equity_ticker("../.env")


def test_max_pain_calculation():
    df = pd.DataFrame([
        {"contract_type": "call", "strike_price": 100.0, "open_interest": 500},
        {"contract_type": "call", "strike_price": 105.0, "open_interest": 500},
        {"contract_type": "put", "strike_price": 100.0, "open_interest": 500},
        {"contract_type": "put", "strike_price": 95.0, "open_interest": 500},
    ])
    mp = _calculate_max_pain(df)
    assert mp == 100.0


def test_overview_reports_installed_models_and_datasets(monkeypatch, tmp_path):
    from webui import testing_suite as ts
    from webui import polygon_feed

    monkeypatch.setattr(ts, "FINETUNED_DIR", tmp_path / "finetuned")
    monkeypatch.setattr(ts, "DATA_DIR", tmp_path / "data")
    spy_dir = tmp_path / "data" / ts.TICKER_TO_MODEL_MAP["SPY"]["data_subdir"]
    spy_dir.mkdir(parents=True)
    spec = ts.TICKER_TO_MODEL_MAP["SPY"]
    (spy_dir / f"{spec['file_prefix']}_1day_{spec['span_years']}.csv").write_text("timestamps,close\n", encoding="utf-8")
    custom_dir = tmp_path / "data" / "custom"
    custom_dir.mkdir()
    custom_csv = custom_dir / "AMD_1hour_sample.csv"
    custom_csv.write_text("timestamps,close\n", encoding="utf-8")
    (custom_dir / "AMD_1hour_sample_1day.csv").write_text("timestamps,close\n", encoding="utf-8")
    assert ts.resolve_local_dataset_csv("AMD", "1hour") == custom_csv
    monkeypatch.setattr(polygon_feed, "settings", lambda: (None, "https://api.polygon.io"))

    app = Flask(__name__)
    register_testing_suite(app, ui, live_feed=polygon_feed.PolygonFeed())
    data = app.test_client().get("/api/testing/overview").get_json()

    assert data["tuned_models"] == []
    assert "SPY_23yr_multi_tf" not in data["registered_model_keys"]
    assert set(data["registered_model_keys"]) == set(ui.AVAILABLE_MODELS)
    assert data["datasets"] == {"AMD": ["1hour"], "SPY": ["1day"]}
    assert data["live_feed"] is False


def test_polygon_feed_configuration_requires_a_key(monkeypatch):
    from webui import polygon_feed

    feed = polygon_feed.PolygonFeed()
    monkeypatch.setattr(polygon_feed, "settings", lambda: ("configured-key", "https://api.polygon.io"))
    assert feed.is_configured() is True

    monkeypatch.setattr(polygon_feed, "settings", lambda: (None, "https://api.polygon.io"))
    assert feed.is_configured() is False

    def invalid_settings():
        raise FeedError("invalid provider configuration", 503)

    monkeypatch.setattr(polygon_feed, "settings", invalid_settings)
    assert feed.is_configured() is False


@pytest.mark.postgres
def test_postgres_research_db_and_testing_suite_routes(monkeypatch):
    db = KronosResearchDB()
    # Skip only when Postgres itself is unavailable; schema errors must still fail.
    if not db_store.PSYCOPG_AVAILABLE:
        pytest.skip("kronos_research Postgres unavailable: psycopg not installed")
    try:
        db.connect().close()
    except db_store.psycopg.OperationalError as error:
        pytest.skip(f"kronos_research Postgres unavailable: {error}")
    assert db.ensure_schema() is True, db.last_error

    app = Flask(__name__)
    discovered = discover_and_register_models(ui, db)
    assert len(discovered) >= 7
    assert "SPY_23yr_multi_tf" in ui.AVAILABLE_MODELS
    assert "VIX_companion_multi_tf" in ui.AVAILABLE_MODELS

    register_testing_suite(app, ui, live_feed=None)
    client = app.test_client()

    ov_resp = client.get("/api/testing/overview")
    assert ov_resp.status_code == 200
    ov_data = ov_resp.get_json()
    assert ov_data["success"] is True
    assert ov_data["database"]["connected"] is True
    assert ov_data["database"]["counts"]["tuned_models_registry"] >= 7

    hist_resp = client.get("/api/testing/db-history?ticker=SPY&limit=10")
    assert hist_resp.status_code == 200
    hist_data = hist_resp.get_json()
    assert hist_data["success"] is True
    assert hist_data["database"]["connected"] is True
