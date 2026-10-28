from fastapi import FastAPI
from fastapi.testclient import TestClient

import main
import tray


def test_frontend_is_served_next_to_the_api(tmp_path):
    (tmp_path / "workers").mkdir()
    (tmp_path / "index.html").write_text("<h1>home</h1>", encoding="utf-8")
    (tmp_path / "workers" / "index.html").write_text("<h1>workers</h1>", encoding="utf-8")
    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    assert main.mount_frontend(app, tmp_path)
    client = TestClient(app)

    assert client.get("/").text == "<h1>home</h1>"
    assert client.get("/workers/").text == "<h1>workers</h1>"
    assert client.get("/api/health").json() == {"status": "ok"}


def test_next_segment_prefetch_files_are_found(tmp_path):
    (tmp_path / "workers" / "__next.workers").mkdir(parents=True)
    (tmp_path / "index.html").write_text("home", encoding="utf-8")
    (tmp_path / "404.html").write_text("not found page", encoding="utf-8")  # як у справжньому експорті
    (tmp_path / "workers" / "__next.workers" / "__PAGE__.txt").write_text("segment", encoding="utf-8")
    app = FastAPI()
    main.mount_frontend(app, tmp_path)
    client = TestClient(app)

    assert client.get("/workers/__next.workers.__PAGE__.txt").text == "segment"
    assert client.get("/workers/missing.txt").status_code == 404


def test_missing_build_is_not_mounted(tmp_path):
    assert main.mount_frontend(FastAPI(), tmp_path) is False


def test_autostart_shortcut_is_written_and_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(tray, "STARTUP_DIR", tmp_path)
    monkeypatch.setattr(tray, "STARTUP_FILE", tmp_path / "BDO Companion.cmd")

    path = tray.install_autostart()

    script = path.read_text(encoding="utf-8")
    assert "pythonw.exe" in script and "tray.py" in script
    assert tray.remove_autostart() is True
    assert not path.exists()
    assert tray.remove_autostart() is False


def test_tray_icon_image():
    assert tray.icon_image().size == (64, 64)
