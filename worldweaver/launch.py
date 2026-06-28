"""
WorldWeaver — lanzador de escritorio.

Arranca el servidor FastAPI en localhost (puerto libre) y abre el navegador
en modo aplicación a pantalla completa (sin barra del navegador), dando
sensación de programa nativo.

Uso en desarrollo:
    python launch.py

También es el punto de entrada del ejecutable empaquetado con PyInstaller:
detecta si corre "congelado" (sys.frozen) y resuelve las rutas en consecuencia.
"""

import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

# ── Resolución de rutas (dev vs ejecutable congelado) ────────────────────────
# En el .exe de PyInstaller los módulos viven dentro de la carpeta del paquete,
# así que añadimos el directorio de este archivo al sys.path para poder importar
# `server` tanto en dev como congelado.
_AQUI = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
sys.path.insert(0, str(_AQUI))

HOST = "127.0.0.1"


def _puerto_libre(preferido: int = 8000) -> int:
    """Devuelve el puerto preferido si está libre; si no, uno cualquiera del SO."""
    for puerto in (preferido, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((HOST, puerto))
                return s.getsockname()[1]
            except OSError:
                continue
    return preferido


def _navegadores_app():
    """Rutas candidatas a Chrome/Edge para abrir en modo --app (sin chrome del navegador)."""
    candidatos = []
    pf   = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    candidatos += [
        Path(pf)   / "Google/Chrome/Application/chrome.exe",
        Path(pf86) / "Google/Chrome/Application/chrome.exe",
        Path(local)/ "Google/Chrome/Application/chrome.exe",
        Path(pf86) / "Microsoft/Edge/Application/msedge.exe",
        Path(pf)   / "Microsoft/Edge/Application/msedge.exe",
    ]
    return [c for c in candidatos if c.is_file()]


def _abrir_navegador(url: str) -> None:
    """Abre la URL en modo app a pantalla completa; cae a navegador normal si no hay Chrome/Edge."""
    import subprocess

    # Perfil temporal aislado → ventana en modo app limpia, sin tocar el perfil del usuario.
    perfil = Path(os.environ.get("TEMP", ".")) / "worldweaver_app_profile"

    for navegador in _navegadores_app():
        try:
            subprocess.Popen([
                str(navegador),
                f"--app={url}",
                # Pantalla completa SALIBLE (con Esc, como la de F11). Arranca en fullscreen y,
                # como al cruzar un portal se cambia de página y se pierde, el propio viewer
                # vuelve a entrar en fullscreen con el PRIMER gesto de cada escena (ver
                # _wwAutoFullscreen en sandbox/index.html). NO usamos --kiosk porque bloquea
                # el Esc y no deja salir de pantalla completa / de la app.
                "--start-fullscreen",
                "--new-window",
                f"--user-data-dir={perfil}",
                "--no-first-run",
                "--no-default-browser-check",
                "--autoplay-policy=no-user-gesture-required",
            ])
            return
        except Exception:
            continue

    # Sin Chrome/Edge: navegador por defecto en ventana normal.
    import webbrowser
    webbrowser.open(url)


def _esperar_servidor(url: str, timeout: float = 30.0) -> bool:
    """Sondea la URL hasta que responda o se agote el tiempo."""
    fin = time.time() + timeout
    while time.time() < fin:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except Exception:
            time.sleep(0.25)
    return False


def main() -> None:
    import uvicorn

    # Los mundos viven como carpeta outputs/ junto al .exe (no horneados en el
    # binario): lo que haya ahí es exactamente lo que ve el usuario. server.py
    # crea la carpeta vacía si no existe.
    from server import app

    puerto = _puerto_libre(8000)
    url = f"http://{HOST}:{puerto}/"

    # Hilo que espera a que el servidor levante y abre el navegador.
    def _abrir():
        if _esperar_servidor(url):
            print(f"\n  WorldWeaver abierto en {url}")
            print("  (cierra esta ventana para detener la aplicación)\n")
            _abrir_navegador(url)
        else:
            print(f"\n  No se pudo confirmar el arranque del servidor. Abre manualmente: {url}\n")

    threading.Thread(target=_abrir, daemon=True).start()

    # uvicorn en el hilo principal (bloqueante). El objeto app evita el modo reload/multiproceso.
    uvicorn.run(app, host=HOST, port=puerto, log_level="warning")


if __name__ == "__main__":
    main()
