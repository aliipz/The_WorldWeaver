"""
Re-ensambla los preview HTML de un mundo ya generado, a partir de su JSON en
outputs/<mundo>/. Reinyecta el template actual (sandbox/index.html + JS inline)
sin volver a llamar a ningún LLM ni API — útil tras tocar el viewer.

Uso (desde worldweaver/worldweaver/):
    python scripts/reensamblar.py aldo_reliquias [otro_mundo ...]

Reconstruye los mismos inputs que nodo_ensamblador: scene_graph, manifest, músico,
escena, portal/quiz, fin (última escena narrativa). El idioma se lee del preview
existente; el modo se deduce de la presencia de salida_examinador.json.
"""
import sys
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.ensamblador import ensamblar, generar_quiz_html  # noqa: E402
from schemas.scene_graph import SceneGraph           # noqa: E402
from schemas.interacciones import SalidaProgramador  # noqa: E402
from schemas.audio import SalidaMusico               # noqa: E402
from schemas.escenas import SalidaOrganizador        # noqa: E402
from schemas.quiz import SalidaExaminador            # noqa: E402

OUTPUTS = ROOT / "outputs"


def _load(model, path: Path):
    if not path.exists():
        return None
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"    [!] no se pudo leer {path.name}: {e}")
        return None


def _idioma_de_preview(wdir: Path) -> str:
    for p in sorted(wdir.glob("preview_escena_*.html")):
        m = re.search(r'const IDIOMA\s*=\s*"(\w+)"', p.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return "es"


def reensamblar(world: str) -> None:
    wdir = OUTPUTS / world
    org = _load(SalidaOrganizador, wdir / "salida_organizador.json")
    if not org:
        print(f"  [!] {world}: sin salida_organizador.json — omitido")
        return

    idioma = _idioma_de_preview(wdir)
    modo = "educativo" if (wdir / "salida_examinador.json").exists() else "narrativo"
    escenas = org.escenas

    # Cargar todos los scene_graphs (para el slideshow de fin)
    sgs = {}
    for esc in escenas:
        sg = _load(SceneGraph, wdir / f"scene_graph_{esc.id}.json")
        if sg:
            sgs[esc.id] = sg

    print(f"  {world}: idioma={idioma} modo={modo} escenas={len(escenas)}")

    for idx, esc in enumerate(escenas):
        sg = sgs.get(esc.id)
        if not sg:
            print(f"    [!] {esc.id}: sin scene_graph — omitido")
            continue

        manifest = _load(SalidaProgramador, wdir / f"salida_programador_{esc.id}.json")
        musico   = _load(SalidaMusico,      wdir / f"salida_musico_{esc.id}.json")

        es_ultima = idx + 1 >= len(escenas)

        next_scene_url = None
        portal_label = None
        if idx + 1 < len(escenas):
            next_scene_url = f"preview_{escenas[idx + 1].id}.html"
        elif es_ultima and modo == "educativo":
            next_scene_url = "quiz.html"
            portal_label = "final quiz" if idioma == "en" else "cuestionario final"

        texto_fin = None
        escenas_cielo = None
        if es_ultima and modo != "educativo" and esc.texto_fin:
            texto_fin = esc.texto_fin
            titulo_por_id = {e.id: e.titulo for e in escenas}
            escenas_cielo = []
            for eid_prev, sg_prev in sgs.items():
                escenas_cielo.append({
                    "titulo":         titulo_por_id.get(eid_prev, eid_prev),
                    "color_fondo":    sg_prev.cielo.color_fondo,
                    "color_sol":      sg_prev.cielo.color_sol,
                    "color_ambiente": sg_prev.cielo.color_ambiente,
                })

        out_path = wdir / f"preview_{esc.id}.html"
        ensamblar(
            sg,
            manifest=manifest,
            musico=musico,
            escena=esc,
            next_scene_url=next_scene_url,
            portal_label=portal_label,
            texto_fin=texto_fin,
            escenas_cielo=escenas_cielo,
            output_path=out_path,
            idioma=idioma,
            modo=modo,
        )
        print(f"    [ok] {out_path.name}")

    # Quiz educativo: regenerar quiz.html si existe la salida del Examinador
    if modo == "educativo":
        examen = _load(SalidaExaminador, wdir / "salida_examinador.json")
        if examen:
            generar_quiz_html(examen, wdir / "quiz.html", idioma)
            print("    [ok] quiz.html")


if __name__ == "__main__":
    worlds = sys.argv[1:]
    if not worlds:
        print("Uso: python scripts/reensamblar.py mundo1 [mundo2 ...]")
        sys.exit(1)
    for w in worlds:
        reensamblar(w)
