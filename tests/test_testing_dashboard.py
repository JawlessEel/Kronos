"""
Automated tests for the Kronos Multi-Model Testing Dashboard,
Polygon Options Chain & Underlying Intelligence, and PostgreSQL (`kronos_research`) persistence.
"""
from types import SimpleNamespace
import pandas as pd
import pytest
from flask import Flask

from webui import app as ui
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


def test_postgres_research_db_and_testing_suite_routes(monkeypatch):
    db = KronosResearchDB()
    assert db.ensure_schema() is True

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
