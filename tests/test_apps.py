"""Smoke test skeleton tahap 2 — hanya menguji route placeholder & health."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import landing_app
import superadmin_app
import tenant_app


def test_landing_index_and_health():
    app = landing_app.create_app()
    client = app.test_client()
    assert client.get("/").status_code == 200
    assert client.get("/health").get_json() == {"status": "ok", "app": "landing"}
    assert client.get("/register").status_code == 200


def test_tenant_requires_valid_slug(tmp_path, monkeypatch):
    monkeypatch.setenv("IRIS_DATA_DIR", str(tmp_path))
    app = tenant_app.create_app()
    app.config["DATA_DIR"] = str(tmp_path)
    client = app.test_client()
    assert client.get("/health").get_json() == {"status": "ok", "app": "tenant"}
    assert client.get("/").status_code == 400
    assert client.get("/?tenant=../etc").status_code == 400
    resp = client.get("/?tenant=toko-demo")
    assert resp.status_code == 200
    assert b"toko-demo" in resp.data
    assert (tmp_path / "toko-demo" / "iris.db").exists()


def test_superadmin_index_and_health(tmp_path, monkeypatch):
    monkeypatch.setenv("IRIS_DATA_DIR", str(tmp_path))
    app = superadmin_app.create_app()
    app.config["DATA_DIR"] = str(tmp_path)
    client = app.test_client()
    assert client.get("/health").get_json() == {"status": "ok", "app": "superadmin"}
    assert client.get("/").status_code == 200
