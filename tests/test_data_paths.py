import os

from webui import app as ui


def test_resolve_data_path_accepts_files_inside_data_dir():
    inside = os.path.join(ui.DATA_DIR, "HK_ali_09988_kline_5min_all.csv")
    assert ui.resolve_data_path(inside) == os.path.abspath(inside)
    assert ui.resolve_data_path("SPY/spy_1h.csv") == os.path.abspath(os.path.join(ui.DATA_DIR, "SPY", "spy_1h.csv"))


def test_resolve_data_path_rejects_escapes():
    assert ui.resolve_data_path("../.env") is None
    assert ui.resolve_data_path(os.path.join(ui.DATA_DIR, "..", "webui", "app.py")) is None
    assert ui.resolve_data_path(os.path.abspath(__file__)) is None


def test_routes_reject_paths_outside_data_dir():
    client = ui.app.test_client()
    for route in ("/api/load-data", "/api/predict"):
        response = client.post(route, json={"file_path": "../README.md"})
        assert response.status_code == 400
        assert "data directory" in response.get_json()["error"]
