"""
Harness de evaluación técnica (capítulo de Evaluación del TFM).

Ejecuta el pipeline completo para cada combinación (modelo x texto x K) y vuelca
las métricas objetivas a CSV, sin juicio humano. Las señales que el pipeline no
exponía a posteriori (latencia, tokens, reparaciones del Director, sesgo crudo del
quiz) las captura `pipeline/metricas.py`; el resto se deriva leyendo los JSON que
cada corrida escribe en outputs/<mundo>/.

Uso (desde worldweaver/worldweaver/):
    python scripts/evaluacion_tecnica.py --smoke          # humo: K=1, fixtures que existan
    python scripts/evaluacion_tecnica.py --k 5            # batería completa (corpus definido abajo)
    python scripts/evaluacion_tecnica.py --providers mercury --textos T1,E1 --k 3

Salidas (en outputs/_evaluacion/ por defecto):
    resultados_corridas.csv   — una fila por corrida del pipeline
    llamadas_llm.csv          — una fila por llamada al LLM (latencia + tokens + nodo)

Aviso: cada corrida genera una carpeta outputs/eval_*. Usa --limpiar para borrarlas
tras extraer las métricas. Los tokens de MiniMax/Ollama pueden salir vacíos si la
versión de langchain_ollama no rellena usage_metadata (se reporta la cobertura).
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import statistics
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.llm import provider_name, registrar_callback, limpiar_callbacks  # noqa: E402
from pipeline import metricas  # noqa: E402
from pipeline.graph import ejecutar_pipeline  # noqa: E402

FIXTURES = ROOT / "fixtures"
OUTPUTS = ROOT / "outputs"

# ── Corpus de evaluación ──────────────────────────────────────────────────────
# 6 textos: 4 narrativos (un eje de estrés cada uno) + 2 educativos de dominio HISTORIA.
# Idiomas/vocabulario NO entra en la rejilla cuantitativa: es un artefacto estructuralmente
# distinto (mecánica TPR + diálogo + quiz) que las métricas estructurales no miden bien; se
# evalúa por separado, cualitativamente, con expertos. Los textos coinciden con la galería de
# la evaluación con usuarios, salvo Romeo y el realista, creados para cubrir los ejes que
# faltaban (interiores y longitud baja). `fixture` = nombre del .txt en fixtures/;
# los textos cuyo fixture no exista todavía se saltan con un aviso.
CORPUS = [
    # Narrativos — un eje de estrés cada uno
    {"id": "T1", "fixture": "habichulas.txt",             "modo": "narrativo", "idioma": "es"},  # infantil · interior↔exterior (casa→mata→castillo)
    {"id": "T2", "fixture": "las_aventuras_de_elena.txt", "modo": "narrativo", "idioma": "es"},  # fantasía · densidad + nº localizaciones
    {"id": "T3", "fixture": "romeo_y_julieta.txt",        "modo": "narrativo", "idioma": "es"},  # clásico · interiores + muchos personajes
    {"id": "T4", "fixture": "el_ultimo_turno.txt",        "modo": "narrativo", "idioma": "es"},  # realista · longitud baja
    # Educativos — dominio historia (secuencial)
    {"id": "E1", "fixture": "llegada_a_la_luna.txt",      "modo": "educativo", "idioma": "es"},  # Apolo 11
    {"id": "E2", "fixture": "vuelta_al_mundo.txt",        "modo": "educativo", "idioma": "es"},  # Magallanes-Elcano
]


# ── Métricas estructurales leídas de los JSON de la corrida ───────────────────

def _cargar_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _metricas_estructurales(out_dir: Path) -> dict:
    """Deriva las métricas de calidad estructural y riqueza a partir de los
    scene_graph_*.json y salida_programador_*.json escritos por la corrida."""
    sgs = sorted(out_dir.glob("scene_graph_escena_*.json"))
    progs = sorted(out_dir.glob("salida_programador_escena_*.json"))

    narrativos_total = narrativos_con_gltf = 0
    for p in sgs:
        sg = _cargar_json(p) or {}
        for nodo in sg.get("nodos", []):
            if nodo.get("tipo") in ("personaje", "objeto"):
                narrativos_total += 1
                if nodo.get("gltf_url"):
                    narrativos_con_gltf += 1

    interacciones, fases, zonas, dialogos = [], [], [], []
    for p in progs:
        pr = _cargar_json(p) or {}
        objs = pr.get("objetos", []) or []
        pers = pr.get("personajes", []) or []
        interacciones.append(len(objs) + len(pers))
        fases.append(len(pr.get("fases", []) or []))
        zonas.append(len(pr.get("zonas_narrativas", []) or []))
        for pm in pers:
            dialogos.append(len(pm.get("dialogos", []) or []))

    def _media(xs):
        return round(statistics.mean(xs), 2) if xs else None

    return {
        "n_escenas": len(sgs),
        "narrativos_total": narrativos_total,
        "pct_narrativos_gltf": round(100 * narrativos_con_gltf / narrativos_total, 1)
                               if narrativos_total else None,
        "interacciones_por_escena": _media(interacciones),
        "fases_por_escena": _media(fases),
        "zonas_por_escena": _media(zonas),
        "dialogos_por_personaje": _media(dialogos),
    }


def _agregar_llamadas(corrida_id: str) -> tuple[dict, list[dict]]:
    """Resume las llamadas al LLM capturadas por el callback en esta corrida."""
    filas = []
    lat = [l["latencia_s"] for l in metricas.llamadas_llm if l["latencia_s"] is not None]
    tin = [l["tokens_entrada"] for l in metricas.llamadas_llm if l["tokens_entrada"] is not None]
    tout = [l["tokens_salida"] for l in metricas.llamadas_llm if l["tokens_salida"] is not None]
    n = len(metricas.llamadas_llm)
    for l in metricas.llamadas_llm:
        filas.append({"corrida": corrida_id, **l})
    resumen = {
        "llamadas_llm": n,
        "latencia_total_s": round(sum(lat), 2) if lat else None,
        "latencia_media_s": round(statistics.mean(lat), 3) if lat else None,
        "tokens_entrada_total": sum(tin) if tin else None,
        "tokens_salida_total": sum(tout) if tout else None,
        "cobertura_tokens_pct": round(100 * len(tin) / n, 0) if n else None,
    }
    return resumen, filas


def _resumen_reparaciones() -> dict:
    rs = metricas.reparaciones_director
    if not rs:
        return {"reparaciones_director_total": 0, "reparaciones_por_escena": None}
    total = sum(r["narrativos_reubicados"] + r["separacion_ajustes"] + r["colisiones_resueltas"]
                for r in rs)
    return {
        "reparaciones_director_total": total,
        "reparaciones_por_escena": round(total / len(rs), 2),
        "narrativos_reubicados": sum(r["narrativos_reubicados"] for r in rs),
        "separacion_ajustes": sum(r["separacion_ajustes"] for r in rs),
        "colisiones_resueltas": sum(r["colisiones_resueltas"] for r in rs),
    }


def _resumen_sesgo_quiz() -> dict:
    idx = metricas.sesgo_quiz_crudo
    if not idx:
        return {"quiz_preguntas": 0, "sesgo_quiz_crudo": None}
    # Distribución de la posición de la correcta (0=a..3=d) en la salida cruda.
    dist = {pos: idx.count(pos) for pos in range(4)}
    return {
        "quiz_preguntas": len(idx),
        "sesgo_quiz_crudo": json.dumps(dist),
    }


# ── Una corrida ───────────────────────────────────────────────────────────────

def correr_una(provider: str, item: dict, k: int, modo_dibujante: str) -> tuple[dict, list[dict]]:
    texto_path = FIXTURES / item["fixture"]
    corrida_id = f"{item['id']}_{provider}_k{k}"
    mundo = f"eval_{corrida_id}"
    fila = {
        "corrida": corrida_id, "texto": item["id"], "fixture": item["fixture"],
        "modelo": provider_name(provider), "provider": provider, "k": k,
        "modo": item["modo"], "idioma": item["idioma"],
        "fallo_terminal": False, "error": "",
    }

    metricas.reset()
    limpiar_callbacks()
    registrar_callback(metricas.MetricasCallback())

    t0 = time.perf_counter()
    estado = None
    try:
        estado = ejecutar_pipeline(
            texto=texto_path.read_text(encoding="utf-8"),
            nombre_mundo=mundo,
            provider=provider,
            modo_dibujante=modo_dibujante,
            modo=item["modo"],
            idioma=item["idioma"],
        )
    except Exception as e:  # noqa: BLE001 — una corrida fallida no aborta la batería
        fila["fallo_terminal"] = True
        fila["error"] = f"{type(e).__name__}: {e}"[:200]
        traceback.print_exc()
    fila["tiempo_total_s"] = round(time.perf_counter() - t0, 2)

    # Reintentos del estado final (si llegó a existir)
    reint = (estado or {}).get("reintentos", {}) if isinstance(estado, dict) else {}
    fila["reintentos_organizador"] = reint.get("organizador", 0)
    fila["reintentos_director"] = reint.get("director", 0)
    fila["reintentos_programador"] = reint.get("programador", 0)

    out_dir = Path((estado or {}).get("out_dir") or (OUTPUTS / mundo)) if isinstance(estado, dict) \
        else (OUTPUTS / mundo)
    if out_dir.exists():
        fila.update(_metricas_estructurales(out_dir))

    resumen_llm, filas_llm = _agregar_llamadas(corrida_id)
    fila.update(resumen_llm)
    fila.update(_resumen_reparaciones())
    fila.update(_resumen_sesgo_quiz())

    return fila, filas_llm


# ── Escritura de CSV ──────────────────────────────────────────────────────────

def _escribir_csv(path: Path, filas: list[dict]) -> None:
    if not filas:
        return
    # Unión de todas las claves para una cabecera estable.
    claves: list[str] = []
    for f in filas:
        for c in f:
            if c not in claves:
                claves.append(c)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=claves)
        w.writeheader()
        for f in filas:
            w.writerow(f)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Batería de evaluación técnica de WorldWeaver.")
    ap.add_argument("--providers", default="mercury",
                    help="Lista separada por comas: mercury,ollama")
    ap.add_argument("--textos", default="",
                    help="IDs del corpus a usar (T1,T2,...). Vacío = todos los disponibles.")
    ap.add_argument("--k", type=int, default=5, help="Repeticiones por (modelo x texto).")
    ap.add_argument("--smoke", action="store_true",
                    help="Modo humo: K=1 y solo fixtures que existan.")
    ap.add_argument("--modo-dibujante", default="mock", help="mock|auto (mock = sin fondos PNG).")
    ap.add_argument("--out", default=str(OUTPUTS / "_evaluacion"),
                    help="Carpeta destino de los CSV.")
    ap.add_argument("--limpiar", action="store_true",
                    help="Borra cada carpeta outputs/eval_* tras leer sus métricas.")
    args = ap.parse_args()

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    k_total = 1 if args.smoke else args.k

    filtro = {t.strip() for t in args.textos.split(",") if t.strip()}
    corpus = [c for c in CORPUS if (not filtro or c["id"] in filtro)]

    # Saltar textos cuyo fixture no exista (siempre en smoke; con aviso en completo).
    disponibles = []
    for c in corpus:
        if (FIXTURES / c["fixture"]).exists():
            disponibles.append(c)
        else:
            print(f"  [aviso] {c['id']}: falta fixture '{c['fixture']}' — se salta.")
    if not disponibles:
        print("No hay textos disponibles. Añade fixtures o ajusta CORPUS.")
        return

    total = len(providers) * len(disponibles) * k_total
    print(f"\n=== Evaluación técnica: {len(providers)} modelo(s) x "
          f"{len(disponibles)} texto(s) x K={k_total} = {total} corridas ===\n")

    resultados: list[dict] = []
    llamadas: list[dict] = []
    i = 0
    for provider in providers:
        for item in disponibles:
            for k in range(1, k_total + 1):
                i += 1
                print(f"[{i}/{total}] {item['id']} · {provider} · k{k} ...")
                fila, filas_llm = correr_una(provider, item, k, args.modo_dibujante)
                resultados.append(fila)
                llamadas.extend(filas_llm)
                estado = "FALLO" if fila["fallo_terminal"] else "ok"
                print(f"        {estado} · {fila.get('tiempo_total_s')}s · "
                      f"{fila.get('n_escenas')} escenas · "
                      f"{fila.get('llamadas_llm')} llamadas LLM")
                if args.limpiar:
                    shutil.rmtree(OUTPUTS / f"eval_{item['id']}_{provider}_k{k}", ignore_errors=True)

    out = Path(args.out)
    _escribir_csv(out / "resultados_corridas.csv", resultados)
    _escribir_csv(out / "llamadas_llm.csv", llamadas)
    n_fallos = sum(1 for r in resultados if r["fallo_terminal"])
    print(f"\n=== Hecho. {len(resultados)} corridas ({n_fallos} fallos terminales). ===")
    print(f"    {out / 'resultados_corridas.csv'}")
    print(f"    {out / 'llamadas_llm.csv'}")


if __name__ == "__main__":
    main()
