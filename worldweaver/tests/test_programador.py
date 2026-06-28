"""
Test del Agente 5 — Programador.
Carga SceneGraphs y Escenas ya generadas y produce el manifest de interacciones.

Uso:
    python tests/test_programador.py                       # usa mercury, carga JSONs existentes
    python tests/test_programador.py --provider ollama
    python tests/test_programador.py --escena escena_01    # solo una escena
"""

import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.llm import provider_name
from agents.programador import ejecutar_programador
from agents.musico import ejecutar_musico
from schemas.escenas import SalidaOrganizador
from schemas.especificacion import SalidaDirector
from schemas.scene_graph import SceneGraph
from schemas.interacciones import SalidaProgramador
from pipeline.ensamblador import ensamblar

OUTPUTS = Path(__file__).parent.parent / "outputs"


def _cargar_organizador() -> SalidaOrganizador:
    candidatos = sorted(OUTPUTS.glob("salida_organizador_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidatos:
        raise FileNotFoundError(
            "No se encontró ningún salida_organizador_*.json en outputs/. "
            "Ejecuta primero test_organizador.py."
        )
    ruta = candidatos[0]
    print(f"[Organizador] Cargado: {ruta.name}")
    return SalidaOrganizador.model_validate(json.loads(ruta.read_text(encoding="utf-8")))


def _cargar_director(id_escena: str) -> SalidaDirector:
    candidatos = sorted(OUTPUTS.glob(f"salida_director_{id_escena}_*.json"))
    if not candidatos:
        raise FileNotFoundError(f"No se encontró salida_director_{id_escena}_*.json")
    return SalidaDirector.model_validate(
        json.loads(candidatos[-1].read_text(encoding="utf-8"))
    )


def _cargar_scenegraph(id_escena: str) -> SceneGraph:
    ruta = OUTPUTS / f"scene_graph_{id_escena}.json"
    if not ruta.exists():
        raise FileNotFoundError(
            f"No se encontró {ruta}. "
            "Ejecuta primero test_constructor.py."
        )
    return SceneGraph.model_validate(json.loads(ruta.read_text(encoding="utf-8")))


def test_programador_produce_manifest():
    """El Programador debe generar un manifest válido con fases y personajes."""
    salida_org = _cargar_organizador()
    escena = salida_org.escenas[0]
    sg = _cargar_scenegraph(escena.id)

    salida, _ = ejecutar_programador(sg, escena)

    assert salida.id_escena == escena.id
    assert len(salida.fases) > 0, "Debe haber al menos una fase"
    assert len(salida.personajes) > 0, "Debe haber al menos un personaje"

    ids_sg = {n.id for n in sg.nodos}
    for pm in salida.personajes:
        assert pm.id_nodo in ids_sg, f"id_nodo '{pm.id_nodo}' no existe en el SceneGraph"
    for om in salida.objetos:
        assert om.id_nodo in ids_sg, f"id_nodo '{om.id_nodo}' no existe en el SceneGraph"


def test_programador_personajes_tienen_dialogos():
    """Todos los personajes en el manifest deben tener al menos un DialogoFase."""
    salida_org = _cargar_organizador()
    escena = salida_org.escenas[0]
    sg = _cargar_scenegraph(escena.id)

    salida, _ = ejecutar_programador(sg, escena)

    for pm in salida.personajes:
        assert len(pm.dialogos) >= 1, (
            f"Personaje '{pm.id_nodo}' no tiene dialogos."
        )
        for df in pm.dialogos:
            assert len(df.frases) >= 1, (
                f"Personaje '{pm.id_nodo}', fase {df.fase}: debe tener al menos 1 frase."
            )


# ── Ejecución directa ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="mercury", choices=["mercury", "ollama"])
    parser.add_argument("--escena", default=None, help="ID de escena concreto, ej: escena_01")
    args = parser.parse_args()

    salida_org = _cargar_organizador()
    escenas = salida_org.escenas

    if args.escena:
        escenas = [e for e in escenas if e.id == args.escena]
        if not escenas:
            print(f"❌ No se encontró la escena '{args.escena}'")
            sys.exit(1)

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    modelo = provider_name(args.provider)

    for escena in escenas:
        print(f"\n[Programador] Generando interacciones para: '{escena.titulo}' ({escena.id})...")

        try:
            sg = _cargar_scenegraph(escena.id)
        except FileNotFoundError as e:
            print(f"   [AVISO] {e}")
            continue

        salida, _ = ejecutar_programador(sg, escena, provider=args.provider)

        print(json.dumps(salida.model_dump(), indent=2, ensure_ascii=False))

        n_examinar = sum(1 for om in salida.objetos if om.interaccion.tipo == "examinar")
        n_activar  = sum(1 for om in salida.objetos if om.interaccion.tipo == "activar")
        n_lore     = sum(1 for om in salida.objetos if om.interaccion.tipo == "lore")
        print(
            f"\n[Resumen] '{escena.id}': "
            f"fases={len(salida.fases)} personajes={len(salida.personajes)} "
            f"examinar={n_examinar} activar={n_activar} lore={n_lore} "
            f"zonas={len(salida.zonas_narrativas)}"
        )

        json_path = OUTPUTS / f"salida_programador_{escena.id}_{modelo}.json"
        json_path.write_text(
            json.dumps(salida.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"   [OK] Manifest: {json_path}")

        # Musico
        try:
            director = _cargar_director(escena.id)
            salida_musico = ejecutar_musico(escena.id, director.musica_ambiente)
            print(f"   [Musico] {salida_musico.pista_principal.titulo} ({salida_musico.pista_principal.duracion_segundos}s)")
        except Exception as e:
            print(f"   [Musico] No disponible: {e}")
            salida_musico = None

        # HTML final
        html_path = OUTPUTS / f"preview_{escena.id}.html"
        ensamblar(sg, manifest=salida, musico=salida_musico, output_path=html_path)
        print(f"   [OK] HTML final: {html_path}")
        print("-" * 60)
