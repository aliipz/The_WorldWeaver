"""
Validadores semánticos del pipeline WorldWeaver.

Cada función recibe los outputs de un agente y devuelve una lista de errores.
Lista vacía = todo correcto. Lista con strings = hay que reintentar.

Estas funciones son llamadas por los nodos validadores del grafo LangGraph.
También pueden usarse directamente en tests unitarios sin ejecutar LLMs.
"""
from __future__ import annotations

import math

from config.geometria import N_COLS_POR_FILA, INTERIOR_TIPOS
from schemas.escenas import SalidaOrganizador, Escena
from schemas.especificacion import SalidaDirector
from schemas.scene_graph import SceneGraph
from schemas.interacciones import SalidaProgramador


# ─── Agente 1 — Organizador ────────────────────────────────────────────────────

def validar_organizador(salida: SalidaOrganizador, modo: str = "narrativo") -> list[str]:
    """Comprueba la estructura mínima de la salida del Organizador."""
    errores = []

    if not salida.escenas:
        errores.append("El Organizador no extrajo ninguna escena.")
        return errores

    # Primera escena: intro narrativa obligatoria
    primera = salida.escenas[0]
    if not primera.tiene_intro:
        errores.append(
            f"La primera escena ('{primera.id}') debe tener 'tiene_intro=true' "
            "y 'texto_intro' con 2-4 frases de narrador que introduzcan la historia."
        )
    elif not (primera.texto_intro or "").strip():
        errores.append(
            f"La primera escena ('{primera.id}') tiene tiene_intro=true "
            "pero 'texto_intro' está vacío."
        )

    # Última escena (narrativo): texto_fin obligatorio — incluye el caso de historia de una sola escena
    if modo == "narrativo":
        ultima = salida.escenas[-1]
        if not (ultima.texto_fin or "").strip():
            errores.append(
                f"La última escena ('{ultima.id}') debe tener 'texto_fin' con 2-4 frases "
                "de narrador que cierren la historia. Obligatorio incluso si la historia "
                "tiene una sola escena."
            )

    # ── Mundo de vocabulario (subtipo educativo 'vocabulario') ────────────────
    # Autodetectado: si alguna escena lleva 'rol_escena', es un mundo de vocabulario.
    escenas_rol = [e for e in salida.escenas if getattr(e, "rol_escena", None)]
    if escenas_rol:
        errores.extend(_validar_vocabulario(salida))

    for escena in salida.escenas:
        if not escena.id.startswith("escena_"):
            errores.append(
                f"ID de escena mal formado: '{escena.id}'. "
                "Debe seguir el patrón 'escena_01', 'escena_02', etc."
            )
        if not escena.entorno.strip():
            errores.append(f"Escena '{escena.id}': campo 'entorno' vacío.")
        if not escena.atmosfera.strip():
            errores.append(f"Escena '{escena.id}': campo 'atmosfera' vacío.")
        if not escena.personajes:
            errores.append(f"Escena '{escena.id}': debe tener al menos 1 personaje.")

        # Coherencia cielo ↔ tipo_ambiente: una escena interior con bóveda exterior
        # produce fenómenos imposibles (nieve o estrellas dentro de una cabaña),
        # y un cielo de interior en un ambiente exterior rompe la iluminación.
        es_ambiente_interior = escena.tipo_ambiente in ("habitacion", "interior", "interior_grande", "cueva")
        es_cielo_interior    = escena.cielo in INTERIOR_TIPOS
        if es_ambiente_interior and not es_cielo_interior:
            errores.append(
                f"Escena '{escena.id}': tipo_ambiente='{escena.tipo_ambiente}' (interior) "
                f"pero cielo='{escena.cielo}' (exterior). El cielo debe ser interior_calido, "
                "interior_frio o interior_luminoso. Si el clima exterior es narrativamente "
                "relevante (nieve, tormenta...), descríbelo en 'atmosfera', no en 'cielo'."
            )
        elif es_cielo_interior and not es_ambiente_interior:
            errores.append(
                f"Escena '{escena.id}': cielo='{escena.cielo}' (interior) pero "
                f"tipo_ambiente='{escena.tipo_ambiente}' (exterior). Si la escena transcurre "
                "en un interior usa tipo_ambiente='habitacion', 'interior', 'interior_grande' o 'cueva'; "
                "si es exterior, elige un cielo de exterior."
            )

        # Coherencia cielo ↔ tipo_ambiente: espacio y superficie_planeta no tienen
        # atmósfera — un amanecer, atardecer o lluvia sobre un planeta es imposible.
        _CIELOS_ESPACIO = {"noche_estrellada", "noche_cerrada", "cielo_magico"}
        if escena.tipo_ambiente in ("espacio", "superficie_planeta") and escena.cielo not in _CIELOS_ESPACIO:
            errores.append(
                f"Escena '{escena.id}': tipo_ambiente='{escena.tipo_ambiente}' no tiene "
                f"atmósfera, pero cielo='{escena.cielo}'. Debe ser 'noche_estrellada', "
                "'noche_cerrada' o 'cielo_magico' (son los únicos visualmente coherentes "
                "en el espacio o sobre la superficie de un planeta)."
            )

        ROLES_VALIDOS = {"protagonista", "antagonista", "secundario"}
        for p in escena.personajes:
            if p.rol not in ROLES_VALIDOS:
                errores.append(
                    f"Personaje '{p.id}' en '{escena.id}': "
                    f"rol inválido '{p.rol}'. Debe ser uno de {ROLES_VALIDOS}."
                )
            if "_" not in p.id:
                errores.append(
                    f"Personaje '{p.id}' en '{escena.id}': "
                    "el ID debe contener guion bajo (ej: personaje_caperucita)."
                )

    return errores


def _validar_vocabulario(salida: SalidaOrganizador) -> list[str]:
    """Reglas específicas de un mundo de vocabulario (subtipo educativo 'vocabulario').
    Se detecta por la presencia de 'rol_escena' en las escenas."""
    errores: list[str] = []
    exposiciones = [e for e in salida.escenas if e.rol_escena == "exposicion"]
    examenes     = [e for e in salida.escenas if e.rol_escena == "examen"]

    if not exposiciones:
        errores.append("Mundo de vocabulario: falta al menos una escena con rol_escena='exposicion'.")
    if not examenes:
        errores.append("Mundo de vocabulario: falta al menos una escena con rol_escena='examen'.")

    # Conversacional (Tipo B): no hay objetos de vocabulario → el vocabulario va en
    # salida.vocabulario (pares concepto↔traducción), que alimenta Programador y Examinador.
    hay_objetos_vocab = any((o.nombre_objetivo or "").strip()
                            for e in salida.escenas for o in e.objetos)
    if not hay_objetos_vocab and not salida.vocabulario:
        errores.append(
            "Mundo de vocabulario conversacional: falta el campo 'vocabulario' (lista de pares "
            "concepto↔traducción). Es imprescindible: lleva el vocabulario que no son objetos."
        )

    # En exposición, los objetos del vocabulario deben llevar 'nombre_objetivo' (la palabra
    # en el idioma objetivo). Sin él no se puede mostrar el par bilingüe ni montar el reto.
    for e in exposiciones:
        sin_objetivo = [o.id for o in e.objetos if not (o.nombre_objetivo or "").strip()]
        if e.objetos and len(sin_objetivo) == len(e.objetos):
            errores.append(
                f"Escena de exposición '{e.id}': ningún objeto tiene 'nombre_objetivo'. "
                "Cada palabra del vocabulario debe llevar su nombre en el idioma objetivo."
            )

    # Coherencia del personaje guía entre exposición y examen: debe haber un personaje
    # con el MISMO id presente en ambas, con skin_id apuntando a su escena de origen
    # (reutilización visual del mismo guía).
    if exposiciones and examenes:
        ids_expo = {p.id for e in exposiciones for p in e.personajes}
        ids_exam = {p.id for e in examenes for p in e.personajes}
        comunes = ids_expo & ids_exam
        if not comunes:
            errores.append(
                "Mundo de vocabulario: el personaje guía debe aparecer (mismo id) en la "
                "escena de exposición y en la de examen para reutilizar su skin."
            )
        else:
            for e in examenes:
                for p in e.personajes:
                    if p.id in comunes and not (p.skin_id or "").strip():
                        errores.append(
                            f"Guía '{p.id}' en '{e.id}': debe tener 'skin_id' (la escena donde se "
                            "estableció su aspecto) para reutilizar el mismo personaje en el examen."
                        )

    return errores


# ─── Agente 2 — Director ──────────────────────────────────────────────────────

_NOMBRES_DECORADO_INVALIDOS = {
    "cocina", "bosque", "habitación", "habitacion", "sala", "jardín",
    "jardin", "exterior", "interior", "escena", "ambiente", "entorno",
    "decoración", "decoracion", "fondo",
    "ventana", "puerta", "pared", "columna", "techo", "escalera",
    "chimenea", "suelo", "camino", "sendero", "umbral",
    "rayo de sol", "haz de luz", "luz solar", "niebla", "humo",
    "sombra", "reflejo", "lluvia", "nieve", "cielo", "horizonte",
    "brisa", "viento",
}


def validar_director(salida: SalidaDirector, escena: Escena) -> list[str]:
    """
    Comprueba la salida del Director contra la escena del Organizador.
    Incluye: cobertura narrativa, decorados concretos con descripcion, grid sin colisiones.
    """
    errores = []

    # ── Cobertura narrativa: todos los personajes y objetos deben estar ───────
    ids_esperados = (
        {p.id for p in escena.personajes} |
        {o.id for o in escena.objetos}
    )
    ids_narrativos = {e.id for e in salida.elementos if e.origen == "narrativo"}
    faltantes = ids_esperados - ids_narrativos
    if faltantes:
        errores.append(
            f"Faltan elementos narrativos del Organizador: {sorted(faltantes)}. "
            "Deben aparecer en 'elementos' con su ID original y origen='narrativo'."
        )

    # ── Passthrough: skin_id ──────────────────────────────────────────────────
    elementos_por_id = {e.id: e for e in salida.elementos}
    for elem_org in [*escena.personajes, *escena.objetos]:
        if elem_org.skin_id is None:
            continue
        elem = elementos_por_id.get(elem_org.id)
        if elem is None:
            continue  # ya cubierto por faltantes
        if elem.skin_id != elem_org.skin_id:
            errores.append(
                f"skin_id de '{elem_org.id}': esperado '{elem_org.skin_id}' "
                f"pero el Director devolvió '{elem.skin_id}'. "
                "Debe copiarse literalmente del Organizador."
            )

    # ── Decorados: objetos físicos concretos ──────────────────────────────────
    for elem in salida.elementos:
        if elem.tipo != "decorado":
            continue
        nombre_lower = elem.nombre.lower().strip()
        if nombre_lower in _NOMBRES_DECORADO_INVALIDOS:
            errores.append(
                f"Decorado '{elem.id}' tiene nombre inválido ('{elem.nombre}'). "
                "Debe ser un objeto físico concreto e independiente."
            )
        if not elem.descripcion.strip():
            errores.append(f"Decorado '{elem.id}': campo 'descripcion' vacío.")

    _es_interior = escena.tipo_ambiente in ("habitacion", "interior", "interior_grande")

    if _es_interior:
        # ── Interiores: rejilla RECTANGULAR 7×7 (columna 0-6, fila 0-6) ────────
        for elem in salida.elementos:
            fila = elem.posicion_grid.fila
            col  = elem.posicion_grid.columna
            if not (0 <= col <= 6) or not (0 <= fila <= 6):
                errores.append(
                    f"'{elem.id}': celda ({col},{fila}) fuera de la rejilla rectangular 7×7 (0-6 × 0-6)."
                )
    else:
        # ── Exterior: columnas válidas por fila (grid pirámide) ───────────────
        for elem in salida.elementos:
            fila = elem.posicion_grid.fila
            col  = elem.posicion_grid.columna
            if fila < 0 or fila > 6:
                errores.append(
                    f"'{elem.id}': fila {fila} fuera de rango (0-6)."
                )
            else:
                max_col = N_COLS_POR_FILA.get(fila, 5) - 1
                if col < 0 or col > max_col:
                    errores.append(
                        f"'{elem.id}': columna {col} inválida para fila {fila} "
                        f"(rango permitido: 0-{max_col})."
                    )

    # ── Grid sin colisiones exactas ───────────────────────────────────────────
    celdas = [(e.posicion_grid.columna, e.posicion_grid.fila) for e in salida.elementos]
    if len(celdas) != len(set(celdas)):
        duplicados = sorted({c for c in celdas if celdas.count(c) > 1})
        errores.append(
            f"Colisiones en el grid: {duplicados}. "
            "Cada elemento debe ocupar una celda única (columna, fila)."
        )

    # ── Composición mínima ────────────────────────────────────────────────────
    tipos = {e.tipo for e in salida.elementos}
    if "personaje" not in tipos:
        errores.append("Debe existir al menos un elemento de tipo 'personaje'.")
    if "decorado" not in tipos:
        errores.append("Debe existir al menos un elemento de tipo 'decorado'.")

    # ── Zona jugable: narrativos en filas 3-6 (solo grid pirámide/exterior) ───
    # En interiores la rejilla es rectangular y el jugador camina por toda la sala,
    # así que los narrativos pueden ir en cualquier celda (no se aplica este check).
    if not _es_interior:
        for elem in salida.elementos:
            fila = elem.posicion_grid.fila
            if elem.origen == "narrativo" and fila < 3:
                errores.append(
                    f"'{elem.id}' (origen='narrativo') está en fila {fila}. "
                    "Los personajes y objetos narrativos deben estar en fila 3-6 "
                    "para que el jugador pueda alcanzarlos."
                )
    # Decorados: filas 0-2 para fondo ambiental, 3-6 para decorados jugables.

    return errores


# ─── Agente 3 — Constructor ───────────────────────────────────────────────────

def validar_constructor(scene_graph: SceneGraph) -> list[str]:
    """
    Comprueba el SceneGraph producido por el Constructor.
    El Constructor es determinístico — los errores aquí son bugs del código,
    no del LLM. Por eso no hay retry; se lanza excepción si falla.
    """
    errores = []

    fondos  = [n for n in scene_graph.nodos if n.tipo == "fondo"]
    suelos  = [n for n in scene_graph.nodos if n.tipo == "suelo"]

    if len(fondos) != 1:
        errores.append(
            f"Se esperaba exactamente 1 nodo 'fondo', hay {len(fondos)}."
        )

    # El suelo es opcional en escenas espacio (tipo_ambiente='espacio')
    if scene_graph.tipo_ambiente != "espacio" and len(suelos) != 1:
        errores.append(
            f"Se esperaba exactamente 1 nodo 'suelo', hay {len(suelos)}."
        )

    for nodo in scene_graph.nodos:
        if nodo.ancho <= 0 or nodo.alto <= 0:
            errores.append(
                f"Nodo '{nodo.id}': dimensiones inválidas "
                f"(ancho={nodo.ancho}, alto={nodo.alto})."
            )

    # Invariante de alcance: todo narrativo (personaje/objeto del Organizador) debe quedar
    # dentro del límite del jugador. En exteriores/barco el límite es radial; en interiores
    # en caja es por caja (lo cubre el grid rectangular dentro de los muros) → no se chequea.
    # El Constructor lo garantiza con _clamp_narrativos_alcance; aquí solo se verifica.
    if scene_graph.tipo_escena == "exterior" and scene_graph.limite_jugador:
        lim = scene_graph.limite_jugador
        for nodo in scene_graph.nodos:
            if getattr(nodo, "origen", None) != "narrativo":
                continue
            r = math.hypot(nodo.posicion.x, nodo.posicion.z)
            if r > lim + 0.5:
                errores.append(
                    f"Narrativo '{nodo.id}' fuera del alcance del jugador "
                    f"(r={r:.2f} > límite {lim})."
                )

    return errores


# ─── Agente 5 — Programador ───────────────────────────────────────────────────

def _participantes_por_fase(escena, ids_sg: set) -> dict:
    """
    Reconstruye determinísticamente qué nodos participan en cada fase,
    a partir de los eventos del Organizador (misma lógica que _construir_backbone).
    Retorna {fase_idx: set_of_ids}.
    """
    result: dict[int, set] = {}
    fase = 0
    for evento in escena.eventos:
        todos = [x for x in (evento.objetos_involucrados + evento.personajes_involucrados)
                 if x in ids_sg]
        if not todos:
            continue
        result[fase] = set(todos)
        fase += 1
    if not result:
        todos = sorted(ids_sg)[:3]
        if todos:
            result[0] = set(todos)
    return result


def validar_programador(
    salida: SalidaProgramador,
    scene_graph: SceneGraph,
    escena=None,
) -> list[str]:
    """
    Comprueba el manifest de interacciones del Programador contra el SceneGraph.
    guías y condicion_avance son deterministas (backbone del Organizador) — solo
    se verifica que los IDs referenciados existen en el manifest y el SceneGraph.
    """
    errores = []

    ids_validos     = {n.id for n in scene_graph.nodos}
    tipos_nodo      = {n.id: n.tipo for n in scene_graph.nodos}
    TIPOS_EXCLUIDOS = {"fondo", "suelo", "ambiente"}

    ids_personajes_manifest = {p.id_nodo for p in salida.personajes}
    ids_objetos_manifest    = {o.id_nodo for o in salida.objetos}
    ids_zonas               = {z.id for z in salida.zonas_narrativas}
    num_fases               = len(salida.fases)
    fase_aparicion_por_id   = {p.id_nodo: p.fase_aparicion for p in salida.personajes}
    fase_aparicion_por_id.update({o.id_nodo: o.fase_aparicion for o in salida.objetos})

    # ── Fases ─────────────────────────────────────────────────────────────────
    if not salida.fases:
        errores.append("El manifest no contiene ninguna fase.")
        return errores

    fase_indices = [f.fase for f in salida.fases]
    if sorted(fase_indices) != list(range(num_fases)):
        errores.append(
            f"Los índices de fase deben ser consecutivos desde 0. "
            f"Encontrados: {fase_indices}"
        )

    # Mapa id_nodo → tipo de interacción (para detectar lore en condicion_avance)
    interaccion_tipo = {o.id_nodo: (o.interaccion.tipo if o.interaccion else None)
                        for o in salida.objetos if o.interaccion}

    for fm in salida.fases:

        # guias = condicion_avance (derivadas determinísticamente en programador.py)
        # Solo verificamos que existen en el SceneGraph y no son excluidos
        for g in fm.guias:
            if g not in ids_validos:
                errores.append(f"Fase {fm.fase}: guía '{g}' no existe en el SceneGraph.")
            elif tipos_nodo.get(g) in TIPOS_EXCLUIDOS:
                errores.append(
                    f"Fase {fm.fase}: guía '{g}' es de tipo '{tipos_nodo[g]}' (excluido)."
                )

        # condicion_avance: los IDs deben existir en el manifest
        # (son deterministas desde el backbone — solo verificamos coherencia)
        ca = fm.condicion_avance
        for nid in ca.nodos:
            if nid not in ids_objetos_manifest and nid not in ids_personajes_manifest:
                errores.append(
                    f"Fase {fm.fase}: condicion_avance.nodos contiene '{nid}' "
                    "que no está en el manifest. Asegúrate de que el objeto tiene interacción definida."
                )
            elif interaccion_tipo.get(nid) == 'lore':
                errores.append(
                    f"Fase {fm.fase}: condicion_avance.nodos contiene '{nid}' con interacción 'lore'. "
                    "Los objetos 'lore' se activan por hover y no pueden ser condición de avance — "
                    "usa 'examinar', 'activar' u otro tipo que admita completado explícito."
                )
        for pid in ca.personajes:
            if pid not in ids_personajes_manifest:
                errores.append(
                    f"Fase {fm.fase}: condicion_avance.personajes contiene '{pid}' "
                    "que no está en personajes del manifest."
                )
        for zid in ca.zonas:
            if zid not in ids_zonas:
                errores.append(
                    f"Fase {fm.fase}: condicion_avance.zonas contiene '{zid}' "
                    "que no está en zonas_narrativas del manifest."
                )

        # Deadlock: un participante requerido por esta fase debe ser interactuable
        # en ella (el runtime bloquea nodos con fase_aparicion > faseActual).
        for nid in [*ca.nodos, *ca.personajes]:
            fa = fase_aparicion_por_id.get(nid)
            if fa is not None and fa > fm.fase:
                errores.append(
                    f"Fase {fm.fase}: '{nid}' es requerido en condicion_avance pero su "
                    f"fase_aparicion={fa} es posterior — sería ininteractuable (deadlock). "
                    f"Debe ser ≤ {fm.fase}."
                )

    # ── Personajes ────────────────────────────────────────────────────────────
    personajes_sg = {n.id for n in scene_graph.nodos if n.tipo == "personaje"}
    faltantes = personajes_sg - ids_personajes_manifest
    if faltantes:
        errores.append(
            f"Personajes del SceneGraph sin entrada en el manifest: {sorted(faltantes)}."
        )

    for pm in salida.personajes:
        if pm.id_nodo not in ids_validos:
            errores.append(
                f"Personaje manifest '{pm.id_nodo}' no existe en el SceneGraph."
            )
        elif tipos_nodo.get(pm.id_nodo) != "personaje":
            errores.append(
                f"'{pm.id_nodo}' aparece en personajes pero su tipo en el "
                f"SceneGraph es '{tipos_nodo.get(pm.id_nodo)}', no 'personaje'."
            )
        if not pm.dialogos:
            errores.append(f"Personaje '{pm.id_nodo}': debe tener al menos un DialogoFase.")
        if pm.fase_aparicion < 0 or pm.fase_aparicion >= num_fases:
            errores.append(
                f"Personaje '{pm.id_nodo}': fase_aparicion={pm.fase_aparicion} "
                f"fuera de rango (0–{num_fases - 1})."
            )

    # ── Objetos ───────────────────────────────────────────────────────────────
    for om in salida.objetos:
        if om.id_nodo in ids_personajes_manifest:
            errores.append(
                f"'{om.id_nodo}' aparece en 'objetos' pero ya está en 'personajes'. "
                "Los personajes van SOLO en 'personajes', no en 'objetos'."
            )
            continue
        if om.id_nodo not in ids_validos:
            errores.append(
                f"Objeto manifest '{om.id_nodo}' no existe en el SceneGraph."
            )
            continue
        # 'ambiente' SÍ se admite en objetos: la pasada P3 puede animar nodos de
        # relleno de ambiente cercanos al jugador (vegetación, animales, etc.).
        # Solo fondo/suelo siguen excluidos de interacciones.
        if tipos_nodo.get(om.id_nodo) in {"fondo", "suelo"}:
            errores.append(
                f"Objeto '{om.id_nodo}' es de tipo '{tipos_nodo[om.id_nodo]}' "
                "(excluido de interacciones)."
            )
        if om.fase_aparicion < 0 or om.fase_aparicion >= num_fases:
            errores.append(
                f"Objeto '{om.id_nodo}': fase_aparicion={om.fase_aparicion} "
                f"fuera de rango (0–{num_fases - 1})."
            )
        if om.dispara:
            if om.dispara.id_nodo not in ids_validos:
                errores.append(
                    f"Objeto '{om.id_nodo}'.dispara.id_nodo '{om.dispara.id_nodo}' "
                    "no existe en el SceneGraph."
                )
            elif om.dispara.id_nodo == om.id_nodo:
                errores.append(
                    f"Objeto '{om.id_nodo}'.dispara.id_nodo apunta al mismo nodo."
                )

    # ── Zonas narrativas ──────────────────────────────────────────────────────
    for zona in salida.zonas_narrativas:
        invalidas = [c for c in zona.columnas if c < 0 or c > 4]
        if invalidas:
            errores.append(
                f"Zona '{zona.id}': columnas fuera de rango (0-4): {invalidas}."
            )

    return errores


# ─── Agente 4 — Dibujante ─────────────────────────────────────────────────────

def validar_dibujante(salida, scene_graph: SceneGraph) -> list[str]:
    """
    Comprueba los assets generados por el Dibujante.
    Solo valida fondo y suelo (los únicos que el Dibujante procesa).
    """
    from pathlib import Path
    errores = []

    asset_por_id = {a.id_elemento: a for a in salida.assets}

    fondos = [n for n in scene_graph.nodos if n.tipo == "fondo"]
    for nodo in fondos:
        asset = asset_por_id.get(nodo.id)
        if not asset:
            errores.append(f"No se generó asset para el nodo fondo '{nodo.id}'.")
            continue
        if not Path(asset.ruta_png).exists():
            errores.append(f"PNG no encontrado en disco: {asset.ruta_png}")
        if asset.ancho_px <= asset.alto_px:
            errores.append(
                f"Fondo '{nodo.id}' no es panorámico: "
                f"{asset.ancho_px}×{asset.alto_px}px (se espera ancho > alto)."
            )
        if asset.ruta_png and Path(asset.ruta_png).parent.name != scene_graph.id_escena:
            errores.append(
                f"Ruta del fondo '{nodo.id}' no sigue la convención "
                f"assets/<id_escena>/<id_nodo>.png: {asset.ruta_png}"
            )

    return errores
