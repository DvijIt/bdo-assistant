"""BDO Companion в одному процесі: бекенд, зібраний фронт, агент і іконка в треї.

    .venv\\Scripts\\pythonw.exe tray.py            # звичайний запуск, без вікна консолі
    .venv\\Scripts\\python.exe tray.py --no-agent  # не вмикати агента одразу
    .venv\\Scripts\\python.exe tray.py --install-autostart / --remove-autostart

Фронт треба зібрати один раз після змін: `npm run build` у корені репозиторію (папка out/).
"""

import argparse
import os
from pathlib import Path
import sys
import threading
import time
import webbrowser

LOG_FILE = Path(__file__).resolve().parent / "tray.log"

# У pythonw немає консолі: sys.stdout і sys.stderr — None, і логер uvicorn падає на isatty()
# ще до старту, мовчки. Пишемо вивід у файл — заодно там видно помилки запуску.
if sys.stdout is None or sys.stderr is None:
    _log = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log

import pystray  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
import uvicorn  # noqa: E402

import main  # noqa: E402


HOST = "127.0.0.1"
PORT = int(os.environ.get("BDO_PORT", "8000"))
URL = f"http://{HOST}:{PORT}/"
STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
STARTUP_FILE = STARTUP_DIR / "BDO Companion.cmd"


def icon_image() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 62, 62), radius=12, fill=(18, 21, 26), outline=(216, 177, 108), width=3)
    try:
        font = ImageFont.truetype("georgiab.ttf", 40)
    except OSError:
        font = ImageFont.load_default()
    draw.text((32, 33), "B", fill=(240, 215, 161), font=font, anchor="mm")
    return image


def install_autostart() -> Path:
    """Ярлик у папці автозапуску Windows: стартує трей без вікна консолі."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    STARTUP_DIR.mkdir(parents=True, exist_ok=True)
    STARTUP_FILE.write_text(
        f'@echo off\r\ncd /d "{Path(__file__).resolve().parent}"\r\n'
        f'start "" "{pythonw}" "{Path(__file__).resolve()}"\r\n',
        encoding="utf-8",
    )
    return STARTUP_FILE


def remove_autostart() -> bool:
    if STARTUP_FILE.is_file():
        STARTUP_FILE.unlink()
        return True
    return False


def agent_running(_item=None) -> bool:
    return main.agent.status()["state"] in ("starting", "running")


def run(start_agent: bool, open_browser: bool) -> None:
    server = uvicorn.Server(uvicorn.Config(main.app, host=HOST, port=PORT, log_level="warning"))
    thread = threading.Thread(target=server.run, name="bdo-server", daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.1)
    if not server.started:
        raise SystemExit(f"Сервер не запустився на {URL} (порт зайнятий?)")

    if start_agent:
        main.agent.start()
    if open_browser:
        webbrowser.open(URL)

    def toggle_agent(icon, _item):
        if agent_running():
            main.agent.stop()
        else:
            main.agent.start()
        icon.update_menu()

    def quit_app(icon, _item):
        main.agent.stop()
        server.should_exit = True
        icon.stop()

    icon = pystray.Icon(
        "bdo-companion",
        icon_image(),
        "BDO Companion",
        menu=pystray.Menu(
            pystray.MenuItem("Відкрити", lambda *_: webbrowser.open(URL), default=True),
            pystray.MenuItem("Агент слухає гру", toggle_agent, checked=agent_running),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Вихід", quit_app),
        ),
    )
    icon.run()
    thread.join(10)


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-agent", action="store_true", help="не вмикати агента під час запуску")
    parser.add_argument("--no-browser", action="store_true", help="не відкривати браузер під час запуску")
    parser.add_argument("--install-autostart", action="store_true", help="запускати з Windows")
    parser.add_argument("--remove-autostart", action="store_true", help="прибрати автозапуск")
    args = parser.parse_args()

    if args.install_autostart:
        print(f"Автозапуск додано: {install_autostart()}")
        return
    if args.remove_autostart:
        print("Автозапуск прибрано." if remove_autostart() else "Автозапуску не було.")
        return
    if not (main.FRONTEND_DIR / "index.html").is_file():
        print(f"Фронт не зібрано ({main.FRONTEND_DIR}); виконай `npm run build`. API працює й без нього.")
    run(start_agent=not args.no_agent, open_browser=not args.no_browser)


if __name__ == "__main__":
    cli()
