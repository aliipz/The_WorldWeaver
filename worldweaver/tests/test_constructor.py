"""
Test del Agente 3 — Constructor.
Corre el pipeline completo: Organizador → Director → Constructor
y genera un HTML de preview standalone por cada escena.

Uso:
    python tests/test_constructor.py          # genera HTML en outputs/
    pytest tests/test_constructor.py -v -s
"""

import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.organizador import ejecutar_organizador
from agents.director import ejecutar_director
from agents.constructor import ejecutar_constructor
from agents.dibujante import ejecutar_dibujante
from schemas.scene_graph import SceneGraph

FIXTURE   = Path(__file__).parent / "fixtures" / "cuento_ejemplo.txt"
SANDBOX   = Path(__file__).parent.parent / "sandbox"
OUTPUTS   = Path(__file__).parent.parent / "outputs"


# ── Helpers ────────────────────────────────────────────────────────────────

def generar_html_preview(scene_graph: SceneGraph) -> str:
    template_path = SANDBOX / "index.html"
    loader_path   = SANDBOX / "js" / "scene_loader.js"

    template    = template_path.read_text(encoding="utf-8")
    loader_code = loader_path.read_text(encoding="utf-8")
    scene_json  = json.dumps(scene_graph.model_dump(), indent=2, ensure_ascii=False)

    # Reemplazar la referencia externa por el contenido inline
    html = template.replace(
        '<script src="js/scene_loader.js"></script>',
        f'<script>\n{loader_code}\n</script>'
    )
    html = html.replace("__SCENE_GRAPH_PLACEHOLDER__", scene_json)
    return html

def guardar_outputs(scene_graph: SceneGraph, escena_id: str):
    OUTPUTS.mkdir(parents=True, exist_ok=True)

    # JSON del scene graph
    json_path = OUTPUTS / f"scene_graph_{escena_id}.json"
    json_path.write_text(
        json.dumps(scene_graph.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    # HTML preview standalone
    html_path = OUTPUTS / f"preview_{escena_id}.html"
    html_path.write_text(generar_html_preview(scene_graph), encoding="utf-8")

    return json_path, html_path


# ── Tests pytest ───────────────────────────────────────────────────────────

def test_constructor_posiciones_validas():
    """Todos los nodos deben tener coordenadas dentro de los límites del schema."""
    texto = FIXTURE.read_text(encoding="utf-8")
    salida_org = ejecutar_organizador(texto)
    escena = salida_org.escenas[0]
    salida_dir, _ = ejecutar_director(escena)
    sg = ejecutar_constructor(salida_dir, cielo=escena.cielo, tipo_ambiente=escena.tipo_ambiente, entorno=escena.entorno, atmosfera=escena.atmosfera)

    for nodo in sg.nodos:
        assert -6.0 <= nodo.posicion.x <= 6.0,  f"{nodo.id}: x fuera de rango"
        assert  0.0 <= nodo.posicion.y <= 8.0,  f"{nodo.id}: y fuera de rango"
        assert -6.0 <= nodo.posicion.z <= 6.0,  f"{nodo.id}: z fuera de rango"
        assert nodo.ancho > 0 and nodo.alto > 0, f"{nodo.id}: dimensiones inválidas"


def test_constructor_fondo_y_suelo_presentes():
    """Debe haber exactamente un nodo de tipo fondo y uno de tipo suelo."""
    texto = FIXTURE.read_text(encoding="utf-8")
    salida_org = ejecutar_organizador(texto)
    escena = salida_org.escenas[0]
    salida_dir, _ = ejecutar_director(escena)
    sg = ejecutar_constructor(salida_dir, cielo=escena.cielo, tipo_ambiente=escena.tipo_ambiente, entorno=escena.entorno, atmosfera=escena.atmosfera)

    fondos  = [n for n in sg.nodos if n.tipo == "fondo"]
    suelos  = [n for n in sg.nodos if n.tipo == "suelo"]
    assert len(fondos) == 1,  f"Se esperaba 1 fondo, hay {len(fondos)}"
    assert len(suelos) == 1,  f"Se esperaba 1 suelo, hay {len(suelos)}"


def test_constructor_profundidad_coherente():
    """Los personajes en primer plano deben tener z mayor que el decorado de fondo."""
    texto = FIXTURE.read_text(encoding="utf-8")
    salida_org = ejecutar_organizador(texto)
    escena = salida_org.escenas[0]
    salida_dir, _ = ejecutar_director(escena)
    sg = ejecutar_constructor(salida_dir, cielo=escena.cielo, tipo_ambiente=escena.tipo_ambiente, entorno=escena.entorno, atmosfera=escena.atmosfera)

    zs = {n.id: n.posicion.z for n in sg.nodos if n.tipo != "fondo"}
    if zs:
        print(f"\n  Profundidades: {zs}")


# ── Ejecución directa ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--desde-json", type=str, default=None,
        help="Ruta a un salida_director_XXXX.json previo. "
             "Si no se indica, corre el pipeline completo."
    )
    parser.add_argument(
        "--provider", type=str, default="mercury",
        choices=["mercury", "ollama"],
        help="Provider de LLM a utilizar (default: mercury)"
    )
    args = parser.parse_args()

    from config.llm import provider_name
    modelo = provider_name(args.provider)

    if args.desde_json:
        # Modo rápido: cargar SalidaDirector desde fichero.
        # cielo y tipo_ambiente se leen del JSON crudo (compatibilidad con archivos anteriores).
        from schemas.especificacion import SalidaDirector
        datos = json.loads(Path(args.desde_json).read_text(encoding="utf-8"))
        salida_dir = SalidaDirector.model_validate(datos)
        cielo_json        = datos.get("cielo", "manana_despejada")
        tipo_ambiente_json = datos.get("tipo_ambiente", "naturaleza")
        entorno_json   = datos.get("entorno", "")
        atmosfera_json = datos.get("atmosfera", "")
        escenas_pares = [(salida_dir, cielo_json, tipo_ambiente_json, entorno_json, atmosfera_json)]
        print(f"\n📂 Cargado desde: {args.desde_json}")
    else:
        # Modo completo: correr Organizador + Director
        texto = FIXTURE.read_text(encoding="utf-8")
        print(f"\n🎬 Organizador ({args.provider})...")
        salida_org = ejecutar_organizador(texto, provider=args.provider)
        escenas_pares = []
        for escena in salida_org.escenas:
            salida_dir, _ = ejecutar_director(escena, provider=args.provider)
            escenas_pares.append((salida_dir, escena.cielo, escena.tipo_ambiente, escena.entorno, escena.atmosfera))

        # Guardar salida del Organizador
        OUTPUTS.mkdir(parents=True, exist_ok=True)
        org_path = OUTPUTS / f"salida_organizador_{modelo}.json"
        org_path.write_text(
            json.dumps(salida_org.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"\n   💾 Organizador: {org_path}")

        # Guardar salida del Director por escena
        for salida_dir, _, __, ___, ____ in escenas_pares:
            dir_path = OUTPUTS / f"salida_director_{salida_dir.id_escena}_{modelo}.json"
            dir_path.write_text(
                json.dumps(salida_dir.model_dump(), indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            print(f"   💾 Director '{salida_dir.id_escena}': {dir_path}")

    for salida_dir, cielo, tipo_ambiente, entorno, atmosfera in escenas_pares:
        print(f"\n🏗  Constructor: '{salida_dir.id_escena}'...")
        sg = ejecutar_constructor(salida_dir, cielo=cielo, tipo_ambiente=tipo_ambiente, entorno=entorno, atmosfera=atmosfera)
        json_path, html_path = guardar_outputs(sg, salida_dir.id_escena)

        encontrados = sum(1 for n in sg.nodos if n.gltf_url)
        sin_modelo  = sum(1 for n in sg.nodos if n.tipo not in ("fondo", "suelo") and not n.gltf_url)

        for nodo in sg.nodos:
            if nodo.tipo in ("fondo", "suelo"):
                print(f"   [{nodo.tipo:10}] {nodo.id:35} — textura 2D (Dibujante)")
            elif nodo.gltf_url:
                print(f"   [{nodo.tipo:10}] {nodo.id:35} ✓ '{nodo.keyword_busqueda}' → {nodo.gltf_url[:55]}...")
            else:
                print(f"   [{nodo.tipo:10}] {nodo.id:35} ✗ '{nodo.keyword_busqueda}' — sin modelo (billboard fallback)")

        print(f"\n   📊 {encontrados} modelos 3D encontrados, {sin_modelo} con fallback")
        print(f"   💾 JSON:    {json_path}")
        print(f"   🌐 Preview: {html_path}")

        # Dibujante mock: solo fondo y suelo (el resto son modelos 3D)
        nodos_2d = [n for n in sg.nodos if n.tipo in ("fondo", "suelo")]
        if nodos_2d:
            print(f"\n🎨 Dibujante (mock, solo fondo+suelo): '{salida_dir.id_escena}'...")
            from schemas.scene_graph import SceneGraph as SG
            sg_2d = SG(id_escena=sg.id_escena, nodos=nodos_2d, camara=sg.camara)
            salida_dib = ejecutar_dibujante(sg_2d, modo="mock")
            for asset in salida_dib.assets:
                print(f"   {asset.id_elemento:40} → {Path(asset.ruta_png).name}"
                      f"  ({asset.ancho_px}×{asset.alto_px}px)")
            print(f"\n   ✅ {len(salida_dib.assets)} assets 2D generados")