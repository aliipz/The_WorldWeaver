"""
WorldWeaver — servidor web local.

Arranca con:
    cd worldweaver
    uvicorn server:app --reload --port 8000

Luego abre http://localhost:8000 en el navegador.
"""

import asyncio
import json
import queue as _queue
import shutil
import sys
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Paths ──────────────────────────────────────────────────────────────────────
# RECURSOS (solo lectura: sandbox, assets) vs DATOS (escribible: outputs).
# En dev ambos coinciden con la carpeta del paquete; en el .exe se separan.
from runtime_paths import RECURSOS as BASE, dato

OUTPUTS = dato("outputs")
OUTPUTS.mkdir(parents=True, exist_ok=True)

# Aseguramos que los módulos del paquete sean importables
sys.path.insert(0, str(BASE))

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI()


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles que desactiva la caché del navegador. Los mundos generados (HTML) y el
    sandbox (JS) cambian al regenerar; sin esto el navegador sirve la versión vieja y hay
    que hacer Ctrl+Shift+R en cada iteración."""
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


# Archivos estáticos (outputs y sandbox sin caché; assets —música— pueden cachearse)
app.mount("/sandbox", NoCacheStaticFiles(directory=str(BASE / "sandbox")), name="sandbox")
app.mount("/outputs", NoCacheStaticFiles(directory=str(OUTPUTS), html=True), name="outputs")
app.mount("/assets", StaticFiles(directory=str(BASE / "assets")), name="assets")

# ── Job store ──────────────────────────────────────────────────────────────────
# job_id → {"queue": Queue, "world": str, "status": "running"|"done"|"error"}
_jobs: dict = {}


# ── Rutas ──────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse(str(BASE / "landing.html"))


class TextoRequest(BaseModel):
    texto: str
    nombre: str
    modo: str = "narrativo"
    idioma: str = "es"


@app.post("/crear-texto")
async def crear_texto(req: TextoRequest):
    world  = req.nombre.lower().replace(" ", "_").replace("-", "_")
    job_id = str(uuid.uuid4())[:8]

    out_dir = OUTPUTS / world
    out_dir.mkdir(parents=True, exist_ok=True)
    # El texto fuente lo guarda el pipeline nombrado con el título de la historia
    # (nodo_validar_organizador), una vez el Organizador lo ha extraído.

    q = _queue.Queue()
    _jobs[job_id] = {"queue": q, "world": world, "status": "running"}
    threading.Thread(
        target=_run_pipeline,
        args=(job_id, req.texto, world, q, req.modo, req.idioma),
        daemon=True,
    ).start()
    return {"job_id": job_id, "world": world}


def _leer_archivo(content: bytes, filename: str) -> str:
    if filename.lower().endswith(".pdf"):
        import io
        from pypdf import PdfReader
        pages = PdfReader(io.BytesIO(content)).pages
        texto = "\n".join(p.extract_text() or "" for p in pages)
        print(f"\n[PDF] {filename} — {len(pages)} páginas, {len(texto)} caracteres")
        print(f"[PDF] Inicio:\n{texto[:500]}\n{'─'*60}")
        return texto
    return content.decode("utf-8", errors="replace")


@app.post("/crear")
async def crear(file: UploadFile = File(...), modo: str = Form("narrativo"), idioma: str = Form("es")):
    content  = await file.read()
    texto    = _leer_archivo(content, file.filename)
    raw_stem = Path(file.filename).stem
    world    = raw_stem.lower().replace(" ", "_").replace("-", "_")
    job_id   = str(uuid.uuid4())[:8]

    ext = Path(file.filename).suffix.lower() or ".txt"
    out_dir = OUTPUTS / world
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"fuente{ext}").write_bytes(content)

    q = _queue.Queue()
    _jobs[job_id] = {"queue": q, "world": world, "status": "running"}

    threading.Thread(
        target=_run_pipeline,
        args=(job_id, texto, world, q, modo, idioma),
        daemon=True,
    ).start()

    return {"job_id": job_id, "world": world}


@app.get("/progreso/{job_id}")
async def progreso(job_id: str):
    if job_id not in _jobs:
        return JSONResponse({"error": "job no encontrado"}, status_code=404)

    q = _jobs[job_id]["queue"]

    async def generate():
        loop = asyncio.get_event_loop()
        while True:
            try:
                msg = await loop.run_in_executor(None, _get, q, 30)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg["type"] in ("done", "error"):
                    break
            except TimeoutError:
                yield "data: {\"type\":\"ping\"}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Galería de mundos ─────────────────────────────────────────────────────────

@app.get("/api/mundos")
def listar_mundos():
    mundos = []
    for world_dir in sorted(OUTPUTS.iterdir(), key=lambda p: -p.stat().st_mtime):
        if not world_dir.is_dir():
            continue
        if not (world_dir / "preview_escena_01.html").exists():
            continue
        sg_files = sorted(world_dir.glob("scene_graph_escena_*.json"))
        if not sg_files:
            continue
        try:
            sg = json.loads(sg_files[0].read_text(encoding="utf-8"))
            cielo = sg.get("cielo", {})
            mundos.append({
                "nombre":         world_dir.name,
                "color_fondo":    cielo.get("color_fondo",    "#1a1a2e"),
                "color_ambiente": cielo.get("color_ambiente", "#0a0a1a"),
                "color_sol":      cielo.get("color_sol",      "#4060aa"),
                # Modo educativo: detectado por el cuestionario final que solo
                # genera el nodo examinador en ese modo. Sirve para distinguirlos
                # de los narrativos en la galería.
                "educativo":      (world_dir / "salida_examinador.json").exists(),
                "url": f"/outputs/{world_dir.name}/preview_escena_01.html",
            })
        except Exception:
            continue
    return mundos


@app.delete("/api/mundos/{nombre}")
def eliminar_mundo(nombre: str):
    world_dir = OUTPUTS / nombre
    # Evitar path traversal
    if not world_dir.resolve().is_relative_to(OUTPUTS.resolve()) or not world_dir.is_dir():
        raise HTTPException(status_code=404, detail="Mundo no encontrado")
    shutil.rmtree(world_dir)
    return {"ok": True}


# ── Tutorial de bienvenida (precinto de primera vez) ────────────────────────────
# Un archivo "sello" viaja junto al ejecutable al descomprimir el zip. Mientras
# existe, la landing muestra el tutorial guiado la primera vez que se entra. Al
# terminarlo (o saltarlo) el front llama a /api/tutorial-visto, que lo borra; en
# adelante el sello ya no está y el tutorial no vuelve a salir. Es por copia de la
# distribución (no por navegador), que es justo lo que queremos para los evaluadores.
SELLO_PRIMERA_VEZ = dato("primera_vez.txt")


@app.get("/api/primera-vez")
def primera_vez():
    return {"primera_vez": SELLO_PRIMERA_VEZ.exists()}


@app.post("/api/tutorial-visto")
def tutorial_visto():
    try:
        SELLO_PRIMERA_VEZ.unlink(missing_ok=True)
    except Exception:
        pass
    return {"ok": True}


# ── Pipeline en hilo aparte ────────────────────────────────────────────────────

# Mapa nodo LangGraph → etiqueta visible (por idioma)
_LABELS = {
    "es": {
        "organizador":  "Organizador organizando...",
        "director":     "Director dirigiendo...",
        "constructor":  "Constructor construyendo...",
        "programador":  "Programador programando...",
        "musico":       "Músico componiendo...",
        "ensamblador":  "Ensamblador ensamblando...",
        "examinador":   "Examinador preparando cuestionario...",
    },
    "en": {
        "organizador":  "Organizer organizing...",
        "director":     "Director directing...",
        "constructor":  "Constructor building...",
        "programador":  "Programmer coding...",
        "musico":       "Musician composing...",
        "ensamblador":  "Assembler compiling...",
        "examinador":   "Examiner preparing quiz...",
    },
}


def _run_pipeline(job_id: str, texto: str, world: str, q: _queue.Queue, modo: str = "narrativo", idioma: str = "es"):
    try:
        from pipeline.graph import compilar_grafo

        out_dir = OUTPUTS / world
        out_dir.mkdir(parents=True, exist_ok=True)

        estado = {
            "nombre_mundo":         world,
            "provider":             "mercury",
            "modo":                 modo,
            "idioma":               idioma,
            "modo_dibujante":       "mock",
            "out_dir":              str(out_dir),
            "max_retries":          3,
            "texto_original":       texto,
            "escena_activa":        0,
            "escena_filtro":        None,
            "scene_graphs_previos": {},
            "salida_organizador":   None,
            "salida_director":      None,
            "scene_graph":          None,
            "salida_dibujante":     None,
            "salida_programador":   None,
            "salida_musico":        None,
            "mensajes_organizador": [],
            "mensajes_director":    [],
            "mensajes_programador": [],
            "errores_organizador":  [],
            "errores_director":     [],
            "errores_constructor":  [],
            "errores_programador":  [],
            "reintentos":           {},
        }

        grafo = compilar_grafo()
        ultimo_label = None

        labels = _LABELS.get(idioma, _LABELS["es"])
        for event in grafo.stream(estado):
            node = next(iter(event))
            label = labels.get(node)
            if label and label != ultimo_label:
                q.put({"type": "step", "label": label})
                ultimo_label = label

        q.put({"type": "done", "world": world})
        _jobs[job_id]["status"] = "done"

    except Exception as exc:
        import traceback
        from pipeline.errors import ServicioModelosCaido
        print(f"[Server] Error en pipeline:\n{traceback.format_exc()}")
        out_dir = OUTPUTS / world
        if out_dir.exists():
            shutil.rmtree(out_dir, ignore_errors=True)
            print(f"[Server] Carpeta eliminada tras error: {out_dir}")
        # Servicio externo de modelos 3D caído → código especial para que la landing
        # muestre la pantalla dedicada (deja claro que no es problema de WorldWeaver).
        if isinstance(exc, ServicioModelosCaido):
            q.put({"type": "error", "code": "servicio_modelos_caido", "message": str(exc)})
        else:
            q.put({"type": "error", "message": str(exc)})
        _jobs[job_id]["status"] = "error"


def _get(q: _queue.Queue, timeout: int):
    """Wrapper bloqueante que lanza TimeoutError si se agota el tiempo."""
    try:
        return q.get(timeout=timeout)
    except _queue.Empty:
        raise TimeoutError()
