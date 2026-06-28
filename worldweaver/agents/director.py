"""
Agente 2 — El Director
Entrada:  Escena + historial de mensajes (para reintentos con feedback de error)
Salida:   (SalidaDirector, mensajes_actualizados)

Arquitectura de dos pasadas en el primer intento:
  P1 — Posiciona los narrativos (personajes y objetos del Organizador)
  P2 — Genera los decorados, conociendo qué narrativos ya están y dónde

En caso de reintento (mensajes_previos presente), hace una sola pasada combinada
para que el LLM pueda corregir su salida con el contexto de error del validador.
"""

import json
import math
import re
import logging
from typing import List

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from config.prompts import get_prompts, DIRECTOR_TAMAÑOS_SYSTEM, DIRECTOR_TAMAÑOS_USER
from config.llm import get_llm, provider_name
from config.geometria import N_COLS_POR_FILA, params_escena
from pipeline.errors import AgentError
from pipeline import metricas
from schemas.escenas import Escena
from schemas.especificacion import SalidaDirector, ElementoEscena, PosicionGrid


# ── Modelos internos: formato que devuelve el LLM ─────────────────────────────

class _PosNarrativo(BaseModel):
    id:      str
    columna: int   = Field(..., ge=0, le=8)
    fila:    int   = Field(..., ge=0, le=6)
    ancho:   float = Field(..., ge=0.2, le=6.0)
    alto:    float = Field(..., ge=0.2, le=10.0)

class _DecoradoLLM(BaseModel):
    id:          str
    nombre:      str
    descripcion: str
    columna:     int   = Field(..., ge=0, le=8)
    fila:        int   = Field(..., ge=0, le=6)
    ancho:       float = Field(..., ge=0.2, le=6.0)
    alto:        float = Field(..., ge=0.2, le=10.0)

# P1 — inventa decorados sin posiciones
class _DecoradorInventado(BaseModel):
    id:          str
    nombre:      str
    descripcion: str

class _P1Salida(BaseModel):
    decorados: List[_DecoradorInventado]

# P2 — posiciona TODOS los elementos (narrativos + decorados)
class _PosElemento(BaseModel):
    id:      str
    columna: int   = Field(..., ge=0, le=8)
    fila:    int   = Field(..., ge=0, le=6)
    ancho:   float = Field(..., ge=0.2, le=6.0)
    alto:    float = Field(..., ge=0.2, le=10.0)

class _P2Salida(BaseModel):
    posicionamiento: List[_PosElemento]

# Esquema combinado — solo para el camino de reintento
class _SalidaDirectorLLM(BaseModel):
    id_escena:       str
    posicionamiento: List[_PosNarrativo]
    decorados:       List[_DecoradoLLM]

logger = logging.getLogger(__name__)

# ── Geometría del cilindro: fuente única en config/geometria.py ───────────────
_MARGEN_COLS = 0.28       # buffer mínimo en columnas (válido para filas con arco amplio)
_MARGEN_FISICO = 0.45     # gap mínimo en unidades 3D — convierte a columnas por fila
                          # (subido de 0.28→0.45 para reducir el apelotonamiento general;
                          #  si la fila desborda, el recentrado + colisiones lo reparten)
_ANCHO_MIN_PERSONAJE = 0.65  # ancho efectivo mínimo para personajes Quaternius


def _arc_len_por_col(fila: int, radio_por_fila: dict, arco_por_fila: dict) -> float:
    """Longitud de arco real (metros) por columna en una fila dada."""
    radio  = radio_por_fila.get(fila, 3.0)
    arco   = arco_por_fila.get(fila, 100)
    n_cols = N_COLS_POR_FILA.get(fila, 5)
    return radio * (arco / max(n_cols - 1, 1)) * math.pi / 180.0


def _limpiar_json(texto: str) -> str:
    texto = re.sub(r"```(?:json)?\s*", "", texto)
    return texto.replace("```", "").strip()


def _ajustar_tamaños(salida: SalidaDirector, escena: Escena, llm) -> SalidaDirector:
    """
    Pasada 2 — ajusta los tamaños de todos los elementos razonando
    su escala relativa en contexto de la escena completa.
    Si falla, devuelve la salida original sin modificar.
    """
    # Construir lista de elementos para el prompt
    lineas = []
    for e in salida.elementos:
        desc = f" — {e.descripcion}" if e.descripcion else ""
        lineas.append(f'- {e.id}: "{e.nombre}" ({e.tipo}){desc}')
    lista_elementos = "\n".join(lineas)

    user_prompt = DIRECTOR_TAMAÑOS_USER.format(
        entorno=escena.entorno,
        atmosfera=escena.atmosfera,
        lista_elementos=lista_elementos,
    )

    messages = [
        SystemMessage(content=DIRECTOR_TAMAÑOS_SYSTEM),
        HumanMessage(content=user_prompt),
    ]

    try:
        respuesta = llm.invoke(messages)
        json_limpio = _limpiar_json(respuesta.content)
        datos = json.loads(json_limpio)

        # Aplicar los tamaños a cada elemento
        actualizados = 0
        for elem in salida.elementos:
            if elem.id in datos:
                t = datos[elem.id]
                ancho = float(t.get("ancho", elem.ancho))
                alto  = float(t.get("alto",  elem.alto))
                # Validar rangos del schema
                elem.ancho = max(0.1, min(20.0, ancho))
                elem.alto  = max(0.1, min(30.0, alto))
                actualizados += 1

        logger.info(
            f"[Director/Tamaños] ✓ {actualizados}/{len(salida.elementos)} "
            "tamaños ajustados en pasada 2."
        )
    except Exception as e:
        logger.warning(
            f"[Director/Tamaños] Pasada 2 fallida ({e}). "
            "Se usan los tamaños de la pasada 1."
        )

    return salida



def _reparar_separacion(salida: SalidaDirector, cielo: str, tipo_ambiente: str = "") -> int:
    """
    Garantiza separación física entre todos los elementos de la misma fila,
    teniendo en cuenta el ancho de cada objeto y el arco real de esa fila.
    Devuelve cuántos elementos vieron su columna ajustada.

    Superset de la antigua _reparar_celdas: cubre tanto colisiones exactas
    (mismo cell) como solapamientos por tamaño de objeto. Opera sobre todos
    los elementos, sin distinción de tipo. Modifica in-place.

    Algoritmo:
      1. Por cada fila, ordenar elementos de izquierda a derecha.
      2. Sweep: empujar cada elemento a la derecha del anterior si su huella
         angular solaparía (huella = ancho / arc_len_por_col).
      3. Si tras el sweep el grupo desborda más allá de col 4, recentrar
         el grupo en [0, 4] recalculando posiciones relativas.
    """
    # Misma geometría que usará el Constructor para esta escena (interior
    # pequeño/grande o exterior) — fuente única: config/geometria.py.
    _, radio_por_fila, arco_por_fila, _, _ = params_escena(cielo, tipo_ambiente)

    n_ajustes = 0
    por_fila: dict[int, list] = {}
    for e in salida.elementos:
        por_fila.setdefault(e.posicion_grid.fila, []).append(e)

    for fila, grupo in por_fila.items():
        if len(grupo) <= 1:
            continue

        arc_col = _arc_len_por_col(fila, radio_por_fila, arco_por_fila)
        # En filas con arco estrecho (fila 4 ≈ 0.68 u/col) el margen fijo en columnas
        # equivale a solo ~14 cm. Usamos el mayor entre el margen en columnas y el
        # margen físico mínimo convertido, para garantizar siempre ≥ 28 cm de gap.
        margen = max(_MARGEN_COLS, _MARGEN_FISICO / arc_col)

        max_col = N_COLS_POR_FILA.get(fila, 5) - 1

        grupo.sort(key=lambda e: e.posicion_grid.columna)
        orig = {e.id: e.posicion_grid.columna for e in grupo}

        # ── Sweep izquierda → derecha ─────────────────────────────────────
        for i in range(1, len(grupo)):
            prev, curr = grupo[i - 1], grupo[i]
            # Personajes Quaternius escalan por altura: su ancho visual real es
            # ~0.65 u independientemente de lo que el Director haya especificado.
            prev_ancho = max(prev.ancho, _ANCHO_MIN_PERSONAJE) if prev.tipo == "personaje" else prev.ancho
            curr_ancho = max(curr.ancho, _ANCHO_MIN_PERSONAJE) if curr.tipo == "personaje" else curr.ancho
            min_col = (
                prev.posicion_grid.columna
                + (prev_ancho / 2.0 + curr_ancho / 2.0) / arc_col
                + margen
            )
            if curr.posicion_grid.columna < min_col:
                curr.posicion_grid.columna = min(max_col, math.ceil(min_col))

        # ── Recentrar si el grupo desborda más allá de la columna máxima ──
        if grupo[-1].posicion_grid.columna > max_col:
            pos = [0.0]
            for i in range(1, len(grupo)):
                p, c = grupo[i - 1], grupo[i]
                p_ancho = max(p.ancho, _ANCHO_MIN_PERSONAJE) if p.tipo == "personaje" else p.ancho
                c_ancho = max(c.ancho, _ANCHO_MIN_PERSONAJE) if c.tipo == "personaje" else c.ancho
                pos.append(
                    pos[-1]
                    + (p_ancho / 2.0 + c_ancho / 2.0) / arc_col
                    + margen
                )
            offset = max(0.0, (float(max_col) - pos[-1]) / 2.0)
            for i, e in enumerate(grupo):
                e.posicion_grid.columna = max(0, min(max_col, round(offset + pos[i])))

        # ── Log de cambios ────────────────────────────────────────────────
        for e in grupo:
            if e.posicion_grid.columna != orig[e.id]:
                n_ajustes += 1
                logger.debug(
                    f"[Director/Sep] '{e.id}': col {orig[e.id]}"
                    f"→ {e.posicion_grid.columna} (fila {fila}, ancho={e.ancho:.2f})"
                )

    return n_ajustes


def _reparar_narrativos(salida: SalidaDirector, escena: Escena) -> int:
    """
    Garantía de cobertura narrativa — dos pases:
    1. Mueve narrativos en fila < 3 a la zona jugable (filas 3-6).
    2. Inserta narrativos omitidos por el LLM en la zona jugable.

    Devuelve cuántas intervenciones aplicó (movidos + insertados).
    """
    n_reparados = 0
    pers_map = {p.id: p for p in escena.personajes}
    obj_map  = {o.id: o for o in escena.objetos}
    ids_narrativos = set(pers_map) | set(obj_map)

    def _celda_libre(filas_preferencia: tuple) -> tuple | None:
        ocupadas = {(e.posicion_grid.columna, e.posicion_grid.fila) for e in salida.elementos}
        for fila_c in filas_preferencia:
            for col in range(N_COLS_POR_FILA.get(fila_c, 5)):
                if (col, fila_c) not in ocupadas:
                    return col, fila_c
        return None

    def _asignar_celda() -> tuple:
        # Preferencia: zona jugable 6→3, luego fondo 2→0 como overflow
        celda = _celda_libre((6, 5, 4, 3, 2, 1, 0))
        if celda is None:
            celda = (0, 6)  # escena imposiblemente llena
        return celda

    # Pase 1: narrativos mal ubicados (fila < 3)
    for e in salida.elementos:
        if e.id in ids_narrativos and e.posicion_grid.fila < 3:
            old_fila = e.posicion_grid.fila
            celda = _asignar_celda()
            e.posicion_grid = PosicionGrid(columna=celda[0], fila=celda[1])
            n_reparados += 1
            logger.warning(
                f"[Director/Repair] Narrativo '{e.id}' en fila {old_fila} → movido a {celda}."
            )

    # Pase 2: narrativos omitidos
    ids_presentes = {e.id for e in salida.elementos}
    for nid in sorted(ids_narrativos - ids_presentes):
        col, fila = _asignar_celda()
        if nid in pers_map:
            p = pers_map[nid]
            salida.elementos.append(ElementoEscena(
                id=p.id, nombre=p.nombre, tipo="personaje", origen="narrativo",
                skin_id=p.skin_id, descripcion=p.fisica or p.nombre,
                posicion_grid=PosicionGrid(columna=col, fila=fila),
                ancho=1.0, alto=1.8,
            ))
        else:
            o = obj_map[nid]
            salida.elementos.append(ElementoEscena(
                id=o.id, nombre=o.nombre, tipo="objeto", origen="narrativo",
                skin_id=o.skin_id, descripcion=o.descripcion,
                posicion_grid=PosicionGrid(columna=col, fila=fila),
                ancho=0.8, alto=0.8,
            ))
        n_reparados += 1
        logger.warning(
            f"[Director/Repair] Narrativo '{nid}' omitido por LLM — insertado en ({col},{fila})."
        )

    return n_reparados


# Palabras que indican que un decorado pertenece al AGUA alrededor del barco
# (filas 0-2) y NO debe subirse a la cubierta.
_BARCO_AGUA_KW = (
    "hielo", "témpano", "tempano", "iceberg", "boya", "salvavidas", "roca",
    "ola", "oleaje", "ave", "gaviota", "pájaro", "pajaro", "tronco", "resto",
    "naufragio", "isla", "sirena", "delfín", "delfin", "ballena", "pez",
    "medusa", "alga", "horizonte", "espuma", "lejano", "lejana", "a la deriva",
)


def _reparar_cubierta_barco(salida: SalidaDirector) -> int:
    """
    Barco: sube a la CUBIERTA (filas 3-6) los decorados de cubierta que el LLM
    haya dejado en el AGUA (filas 0-2). Las cosas de agua (hielo, boyas, restos,
    aves, rocas que asoman...) se quedan en filas 0-2. Sin esto la cubierta queda
    vacía porque el LLM tiende a mandar barriles/cofres/cañones al fondo.
    """
    movidos = 0

    def _celda_libre() -> tuple | None:
        ocupadas = {(e.posicion_grid.columna, e.posicion_grid.fila) for e in salida.elementos}
        for fila_c in (6, 5, 4, 3):
            for col in range(N_COLS_POR_FILA.get(fila_c, 5)):
                if (col, fila_c) not in ocupadas:
                    return col, fila_c
        return None

    for e in salida.elementos:
        if e.tipo != "decorado" or e.posicion_grid.fila >= 3:
            continue
        texto = f"{e.nombre} {e.descripcion}".lower()
        if any(kw in texto for kw in _BARCO_AGUA_KW):
            continue  # pertenece al agua → se queda en filas 0-2
        celda = _celda_libre()
        if celda is None:
            break  # cubierta llena
        old = e.posicion_grid.fila
        e.posicion_grid = PosicionGrid(columna=celda[0], fila=celda[1])
        movidos += 1
        logger.info(f"[Director/Barco] Decorado de cubierta '{e.id}' fila {old} → {celda}.")
    return movidos


def _reparar_colisiones_exactas(salida: SalidaDirector) -> int:
    """
    Pase final: resuelve cualquier colisión exacta (columna, fila) que sobreviva
    a los pases anteriores. Caso típico: el sweep de _reparar_separacion clampea
    dos elementos a columna 4 — ambos quedan en (4, row) sin que el recentrado
    se active.

    Devuelve cuántas colisiones exactas resolvió.
    """
    n_resueltas = 0
    por_celda: dict[tuple[int, int], list] = {}
    for e in salida.elementos:
        key = (e.posicion_grid.columna, e.posicion_grid.fila)
        por_celda.setdefault(key, []).append(e)

    for (col, fila), grupo in por_celda.items():
        if len(grupo) <= 1:
            continue
        ocupadas = {e.posicion_grid.columna for e in salida.elementos if e.posicion_grid.fila == fila}
        n_cols = N_COLS_POR_FILA.get(fila, 5)
        for elem in grupo[1:]:
            libre = next((c for c in range(n_cols) if c not in ocupadas), None)
            if libre is not None:
                logger.debug(
                    f"[Director/Colisión] '{elem.id}': ({col},{fila}) → col {libre}"
                )
                elem.posicion_grid.columna = libre
                ocupadas.add(libre)
                n_resueltas += 1

    return n_resueltas


# Dressing neutro de perímetro: muebles universales que pegan en casi cualquier interior.
# (id_base, nombre, descripcion, ancho, alto). Red de seguridad — solo se usa si el LLM
# se queda corto de decorados en un interior, para que la sala nunca quede vacía.
_DRESSING_INTERIOR = [
    ("decorado_estanteria", "Estantería",       "Estantería alta de madera contra la pared, con cajas y objetos.", 1.3, 2.0),
    ("decorado_planta",     "Planta de interior", "Planta frondosa en una maceta de cerámica.",                     0.6, 1.3),
    ("decorado_banco",      "Banco",            "Banco corrido de madera apoyado en la pared.",                    1.5, 0.7),
    ("decorado_bau",        "Baúl",             "Baúl de madera con refuerzos metálicos, cerrado.",                0.9, 0.7),
    ("decorado_lampara",    "Lámpara de pie",   "Lámpara de pie alta con pantalla de tela.",                       0.5, 1.7),
    ("decorado_taburete",   "Taburete",         "Taburete de madera robusto.",                                     0.5, 0.9),
]


def _poblar_interior_seguridad(salida: SalidaDirector, escena: Escena) -> int:
    """Red de seguridad de la ambientación de interiores (Fase 2 — Blend).

    Si la escena es un interior construido y el LLM dejó pocos decorados, rellena el
    PERÍMETRO (filas 0-2, pegado a las paredes) con mobiliario neutro hasta un mínimo,
    para que la sala nunca se sienta vacía. El mobiliario temático (mesas de restaurante,
    pupitres de aula...) lo pone el LLM vía prompt; esto es solo el suelo de calidad.

    Devuelve cuántos decorados añadió.
    """
    if escena.tipo_ambiente not in ("habitacion", "interior", "interior_grande"):
        return 0
    minimo = 16 if escena.tipo_ambiente == "interior_grande" else (5 if escena.tipo_ambiente == "habitacion" else 8)
    n_dec = sum(1 for e in salida.elementos if e.tipo == "decorado")
    faltan = minimo - n_dec
    if faltan <= 0:
        return 0

    N = _GRID_INT_N
    ocupadas = {(e.posicion_grid.columna, e.posicion_grid.fila) for e in salida.elementos}
    # Celdas del BORDE (perímetro, pegado a las paredes) libres de la rejilla rectangular.
    libres = [
        (col, fila)
        for fila in range(N)
        for col in range(N)
        if (col in (0, N - 1) or fila in (0, N - 1)) and (col, fila) not in ocupadas
    ]
    añadidos = 0
    for i in range(min(faltan, len(libres))):
        col, fila = libres[i]
        base, nombre, desc, ancho, alto = _DRESSING_INTERIOR[i % len(_DRESSING_INTERIOR)]
        salida.elementos.append(ElementoEscena(
            id=f"{base}_{i:02d}", nombre=nombre, tipo="decorado", origen="añadido",
            descripcion=desc,
            posicion_grid=PosicionGrid(columna=col, fila=fila),
            ancho=ancho, alto=alto,
        ))
        añadidos += 1
    if añadidos:
        logger.info(f"[Director] Red de seguridad interior: +{añadidos} decorados de perímetro.")
    return añadidos


# Arquetipos de interior con mobiliario que se REPITE en cantidad. El LLM tiende a poner
# solo 1-2 unidades y la sala se ve pobre; aquí garantizamos un mínimo determinista, con
# keyword de poly.pizza fija para que el modelo sea el correcto (el restaurante usa
# "dining set": una mesa que ya trae las sillas integradas, queda mucho mejor).
# (detectores, base_id, nombre, descripcion, ancho, alto, objetivo, zona, keyword)
_UNIDADES_ARQUETIPO = [
    (("aula", "clase", "colegio", "escuela", "pupitre", "alumno", "pizarra"),
     "pupitre", "Pupitre de alumno",
     "Pupitre de madera con asiento, orientado al frente de la clase.", 0.9, 0.8, 6, "centro", "school desk"),
    (("biblioteca", "libreria", "librería", "archivo", "scriptorium"),
     "estanteria_libros", "Estantería de libros",
     "Estantería alta repleta de libros, contra la pared.", 1.3, 2.1, 6, "pared", "bookshelf"),
    (("restaurante", "taberna", "comedor", "cantina", "meson", "mesón", "posada", "fonda"),
     "conjunto_comedor", "Conjunto de comedor",
     "Mesa con sillas integradas para comensales.", 1.6, 0.9, 4, "centro", "dining set"),
    (("iglesia", "templo", "capilla", "catedral", "altar", "santuario"),
     "banco_iglesia", "Banco de iglesia",
     "Banco corrido de madera, en fila.", 1.9, 0.9, 6, "centro", "church pew"),
    (("bodega", "cava", "almacen", "almacén", "barrica"),
     "barril", "Barril de roble",
     "Barril de roble apilable.", 0.9, 1.1, 5, "pared", "wooden barrel"),
]


def _celdas_pared_repartidas(ocupadas: set, N: int) -> list:
    """Celdas de pared LIBRES, repartidas entre el FONDO (fila N-1) y los dos laterales
    (col 0 y col N-1), alternando los tres muros para no amontonar en uno solo (el fondo
    solía quedar vacío). Centro de cada muro primero. Excluye la pared frontal (fila 0 =
    puerta)."""
    libre = lambda c, f: (c, f) not in ocupadas
    fondo = [(c, N - 1) for c in (3, 2, 4, 1, 5) if libre(c, N - 1)]
    izq   = [(0, f)     for f in (3, 4, 2, 5, 1) if libre(0, f)]
    der   = [(N - 1, f) for f in (3, 4, 2, 5, 1) if libre(N - 1, f)]
    out = []
    for k in range(max(len(fondo), len(izq), len(der))):
        if k < len(fondo): out.append(fondo[k])
        if k < len(izq):   out.append(izq[k])
        if k < len(der):   out.append(der[k])
    return out


def _poblar_unidades_arquetipo(salida: SalidaDirector, escena: Escena) -> int:
    """Garantiza un mínimo de unidades del mobiliario que DEFINE el arquetipo (pupitres en
    un aula, estanterías en una biblioteca, mesas en un restaurante...). El LLM suele poner
    solo 1, dejando la sala irreconocible; aquí completamos hasta un objetivo en celdas
    libres. Las sillas de las mesas las añade _poblar_sillas_mesas (sobre TODAS las mesas)."""
    if escena.tipo_ambiente not in ("habitacion", "interior", "interior_grande"):
        return 0
    texto = f"{escena.titulo} {escena.entorno} {escena.atmosfera}".lower()
    arq = next((u for u in _UNIDADES_ARQUETIPO if any(k in texto for k in u[0])), None)
    if not arq:
        return 0
    _, base, nombre, desc, ancho, alto, objetivo, zona, keyword = arq
    if escena.tipo_ambiente == "habitacion":
        objetivo = max(2, objetivo - 2)
    elif escena.tipo_ambiente == "interior_grande":
        objetivo += 3

    N = _GRID_INT_N
    ocupadas = {(e.posicion_grid.columna, e.posicion_grid.fila) for e in salida.elementos}
    clave = base.split("_")[0]
    ya = sum(1 for e in salida.elementos if clave in e.id.lower() or clave in e.nombre.lower())
    faltan = objetivo - ya
    if faltan <= 0:
        return 0

    if zona == "pared":
        libres = _celdas_pared_repartidas(ocupadas, N)
    else:
        libres = [(c, f) for f in range(1, N - 1) for c in range(1, N - 1) if (c, f) not in ocupadas]
        libres.sort(key=lambda cf: abs(cf[0] - 3) + abs(cf[1] - 3))

    añadidos = 0
    for i in range(min(faltan, len(libres))):
        col, f = libres[i]
        ocupadas.add((col, f))
        idx = ya + i + 1
        salida.elementos.append(ElementoEscena(
            id=f"decorado_{base}_{idx:02d}", nombre=nombre, tipo="decorado", origen="añadido",
            descripcion=desc, posicion_grid=PosicionGrid(columna=col, fila=f), ancho=ancho, alto=alto,
            keyword_busqueda=keyword,
        ))
        añadidos += 1
    if añadidos:
        logger.info(f"[Director] Unidades de arquetipo ('{clave}'): +{añadidos}.")
    return añadidos


def _quitar_decorados_arquitectonicos(salida: SalidaDirector) -> int:
    """Elimina decorados que son elementos ARQUITECTÓNICOS que el viewer ya dibuja
    (ventanas/ventanales, puertas): un modelo 3D de estos queda flotando y feo. Captura
    también nombres compuestos ('gran ventanal', 'ventanal de cristal', 'puerta de roble')
    que el blocklist por nombre exacto no pilla. NO toca 'pared'/'techo' por substring para
    no descartar muebles legítimos (estantería de pared, lámpara de techo)."""
    _PROHIBIDAS = ("ventana", "ventanal", "puerta")
    antes = len(salida.elementos)
    salida.elementos = [
        e for e in salida.elementos
        if not (e.tipo == "decorado" and any(s in e.nombre.lower() for s in _PROHIBIDAS))
    ]
    n = antes - len(salida.elementos)
    if n:
        logger.info(f"[Director] Quitados {n} decorado(s) arquitectónico(s) (ventana/puerta).")
    return n


# Substrings que indican una mesa que NO es de comer → no debe llevar sillas alrededor
# (evita "sillas random" junto a mesas de trabajo, de noche, de centro, de billar, etc.).
_MESA_NO_COMEDOR = (
    "trabajo", "altar", "noche", "centro", "baja", "billar", "luz", "operac",
    "quirof", "disecc", "taller", "carpinter", "herramient", "sastre", "exposic",
    "mezcla", "dibujo", "planos", "noche",
)


def _poblar_sillas_mesas(salida: SalidaDirector, escena: Escena) -> int:
    """En interiores, asegura 2 sillas en celdas CONTIGUAS a cada MESA DE COMER (no mesilla
    ni mesas de trabajo/altar/centro/etc.). El LLM pone la silla suelta lejos de la mesa;
    esto las acompaña para que se lean como conjunto mesa+sillas (cocinas, tabernas)."""
    if escena.tipo_ambiente not in ("habitacion", "interior", "interior_grande"):
        return 0
    N = _GRID_INT_N
    ocupadas = {(e.posicion_grid.columna, e.posicion_grid.fila) for e in salida.elementos}
    mesas = [
        e for e in salida.elementos
        if "mesa" in e.nombre.lower()
        and "mesilla" not in e.nombre.lower()
        and not any(k in e.nombre.lower() for k in _MESA_NO_COMEDOR)
    ]
    n = 0
    for j, m in enumerate(mesas):
        col, fila = m.posicion_grid.columna, m.posicion_grid.fila
        adyacentes = sum(
            1 for e in salida.elementos
            if "silla" in e.nombre.lower()
            and abs(e.posicion_grid.columna - col) + abs(e.posicion_grid.fila - fila) == 1
        )
        faltan = max(0, 2 - adyacentes)
        puestas = 0
        for dc, df in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if puestas >= faltan:
                break
            nc, nf = col + dc, fila + df
            if 0 <= nc < N and 0 <= nf < N and (nc, nf) not in ocupadas:
                ocupadas.add((nc, nf))
                salida.elementos.append(ElementoEscena(
                    id=f"decorado_silla_m{j:02d}_{nc}{nf}", nombre="Silla",
                    tipo="decorado", origen="añadido",
                    descripcion="Silla de madera junto a la mesa.",
                    posicion_grid=PosicionGrid(columna=nc, fila=nf), ancho=0.5, alto=0.9,
                ))
                puestas += 1
                n += 1
    if n:
        logger.info(f"[Director] Sillas junto a mesas: +{n}.")
    return n


def _reconstruir_desde_p2(
    posicionamiento: List[_PosElemento],
    escena: Escena,
    decorados_p1: List[_DecoradorInventado],
) -> list[ElementoEscena]:
    """
    Reconstruye la lista de ElementoEscena desde la salida de P2 (posicionamiento de todo).
    Busca cada ID en tres mapas: personajes, objetos (Organizador) y decorados (P1).
    """
    pers_map = {p.id: p for p in escena.personajes}
    obj_map  = {o.id: o for o in escena.objetos}
    dec_map  = {d.id: d for d in decorados_p1}
    elementos = []
    for pos in posicionamiento:
        pg = PosicionGrid(columna=pos.columna, fila=pos.fila)
        if pos.id in pers_map:
            p = pers_map[pos.id]
            elementos.append(ElementoEscena(
                id=p.id, nombre=p.nombre, tipo="personaje", origen="narrativo",
                skin_id=p.skin_id, descripcion=p.fisica,
                posicion_grid=pg, ancho=pos.ancho, alto=pos.alto,
            ))
        elif pos.id in obj_map:
            o = obj_map[pos.id]
            elementos.append(ElementoEscena(
                id=o.id, nombre=o.nombre, tipo="objeto", origen="narrativo",
                skin_id=o.skin_id, descripcion=o.descripcion,
                posicion_grid=pg, ancho=pos.ancho, alto=pos.alto,
            ))
        elif pos.id in dec_map:
            d = dec_map[pos.id]
            elementos.append(ElementoEscena(
                id=d.id, nombre=d.nombre, tipo="decorado", origen="añadido",
                descripcion=d.descripcion,
                posicion_grid=pg, ancho=pos.ancho, alto=pos.alto,
            ))
        else:
            logger.warning(
                f"[Director/P2] ID '{pos.id}' no encontrado en ningún mapa. Ignorado."
            )
    return elementos


def _reconstruir_narrativos_retry(
    posicionamiento: List[_PosNarrativo], escena: Escena
) -> list[ElementoEscena]:
    """Reconstruye solo narrativos — usado en el camino de reintento."""
    pers_map = {p.id: p for p in escena.personajes}
    obj_map  = {o.id: o for o in escena.objetos}
    elementos = []
    for pos in posicionamiento:
        pg = PosicionGrid(columna=pos.columna, fila=pos.fila)
        if pos.id in pers_map:
            p = pers_map[pos.id]
            elementos.append(ElementoEscena(
                id=p.id, nombre=p.nombre, tipo="personaje", origen="narrativo",
                skin_id=p.skin_id, descripcion=p.fisica,
                posicion_grid=pg, ancho=pos.ancho, alto=pos.alto,
            ))
        elif pos.id in obj_map:
            o = obj_map[pos.id]
            elementos.append(ElementoEscena(
                id=o.id, nombre=o.nombre, tipo="objeto", origen="narrativo",
                skin_id=o.skin_id, descripcion=o.descripcion,
                posicion_grid=pg, ancho=pos.ancho, alto=pos.alto,
            ))
        else:
            logger.warning(f"[Director/Retry] ID '{pos.id}' no encontrado en Organizador. Ignorado.")
    return elementos


def _reconstruir_salida(salida_llm: _SalidaDirectorLLM, escena: Escena) -> SalidaDirector:
    """Reconstruye SalidaDirector completo desde el esquema combinado (camino de reintento)."""
    narrativos = _reconstruir_narrativos_retry(salida_llm.posicionamiento, escena)
    decorados  = [
        ElementoEscena(
            id=d.id, nombre=d.nombre, tipo="decorado", origen="añadido",
            descripcion=d.descripcion,
            posicion_grid=PosicionGrid(columna=d.columna, fila=d.fila),
            ancho=d.ancho, alto=d.alto,
        )
        for d in salida_llm.decorados
    ]
    return SalidaDirector(id_escena=escena.id, elementos=narrativos + decorados)


def _ejecutar_p1(escena: Escena, llm, P) -> tuple[_P1Salida, list]:
    """Pasada 1: el LLM inventa los decorados de la escena (sin posiciones)."""
    narrativos_presentes = "\n".join(
        [f"- {p.nombre} (personaje)" for p in escena.personajes]
        + [f"- {o.nombre} (objeto)" for o in escena.objetos]
    ) or "(ninguno)"

    user_prompt = P.DIRECTOR_P1_USER.format(
        entorno=escena.entorno,
        atmosfera=escena.atmosfera,
        tipo_ambiente=escena.tipo_ambiente,
        cielo=escena.cielo,
        narrativos_presentes=narrativos_presentes,
    )
    messages = [
        SystemMessage(content=P.DIRECTOR_P1_SYSTEM),
        HumanMessage(content=user_prompt),
    ]
    respuesta = llm.invoke(messages)
    messages = messages + [respuesta]
    datos = json.loads(_limpiar_json(respuesta.content))
    salida = _P1Salida.model_validate(datos)
    logger.debug(f"[Director/P1] {len(salida.decorados)} decorados inventados.")
    return salida, messages


def _ejecutar_p2(
    escena: Escena, decorados_p1: List[_DecoradorInventado], llm, P
) -> tuple[_P2Salida, list]:
    """Pasada 2: el LLM posiciona todos los elementos (narrativos + decorados de P1)."""
    narrativos_lista = "\n".join(
        [f"- {p.id}: {p.nombre} — {p.fisica[:80]}" for p in escena.personajes]
        + [f"- {o.id}: {o.nombre} — {o.descripcion[:80]}" for o in escena.objetos]
    ) or "(ninguno)"

    decorados_lista = "\n".join(
        f"- {d.id}: {d.nombre} — {d.descripcion[:80]}"
        for d in decorados_p1
    ) or "(ninguno)"

    user_prompt = P.DIRECTOR_P2_USER.format(
        escena_json=json.dumps(escena.model_dump(), indent=2, ensure_ascii=False),
        narrativos_lista=narrativos_lista,
        decorados_lista=decorados_lista,
    )
    messages = [
        SystemMessage(content=P.DIRECTOR_P2_SYSTEM),
        HumanMessage(content=user_prompt),
    ]
    respuesta = llm.invoke(messages)
    messages = messages + [respuesta]
    datos = json.loads(_limpiar_json(respuesta.content))
    for pos in datos.get("posicionamiento", []):
        if "ancho" in pos:
            pos["ancho"] = max(0.2, min(6.0, pos["ancho"]))
        if "alto" in pos:
            pos["alto"]  = max(0.2, min(10.0, pos["alto"]))
    salida = _P2Salida.model_validate(datos)
    logger.debug(
        f"[Director/P2] {len(salida.posicionamiento)} elementos posicionados."
    )
    return salida, messages


# ── Colocación de INTERIORES: rejilla rectangular 7×7 del suelo ───────────────
_GRID_INT_N = 7  # rejilla 7×7 (columna 0-6, fila 0-6)


def _es_interior_caja(escena: Escena) -> bool:
    """True si la escena es un interior construido (caja), no cueva ni exterior."""
    return escena.tipo_ambiente in ("habitacion", "interior", "interior_grande")


def _ejecutar_interior(
    escena: Escena, decorados_p1: List[_DecoradorInventado], llm, P
) -> tuple[_SalidaDirectorLLM, list]:
    """Pasada de interior: el LLM posiciona narrativos + decorados sobre la rejilla
    rectangular 7×7 (pared vs centro). Emite el formato combinado (_SalidaDirectorLLM)
    para reutilizar _reconstruir_salida y el camino de reintento del grafo."""
    narrativos_lista = "\n".join(
        [f"- {p.id}: {p.nombre} (personaje) — {(p.fisica or '')[:70]}" for p in escena.personajes]
        + [f"- {o.id}: {o.nombre} (objeto) — {(o.descripcion or '')[:70]}" for o in escena.objetos]
    ) or "(ninguno)"
    decorados_lista = "\n".join(
        f"- {d.id}: {d.nombre} — {d.descripcion[:70]}" for d in decorados_p1
    ) or "(ninguno)"

    user = P.DIRECTOR_USER_INTERIOR.format(
        escena_json=json.dumps(escena.model_dump(), indent=2, ensure_ascii=False),
        narrativos_lista=narrativos_lista,
        decorados_lista=decorados_lista,
    )
    messages = [
        SystemMessage(content=P.DIRECTOR_SYSTEM_INTERIOR),
        HumanMessage(content=user),
    ]
    respuesta = llm.invoke(messages)
    datos = json.loads(_limpiar_json(respuesta.content))

    def _norm(p: dict) -> None:
        p["columna"] = max(0, min(_GRID_INT_N - 1, int(p.get("columna", 3))))
        p["fila"]    = max(0, min(_GRID_INT_N - 1, int(p.get("fila", 3))))
        p["ancho"]   = max(0.2, min(6.0,  float(p.get("ancho", 1.0))))
        p["alto"]    = max(0.2, min(10.0, float(p.get("alto", 1.0))))

    for p in datos.get("posicionamiento", []):
        _norm(p)
    # Decorados: las posiciones vienen del LLM, pero nombre/descripcion se toman de P1
    dec_map = {d.id: d for d in decorados_p1}
    decos: list[dict] = []
    for d in datos.get("decorados", []):
        src = dec_map.get(d.get("id"))
        if not src:
            continue
        _norm(d)
        decos.append({
            "id": src.id, "nombre": src.nombre, "descripcion": src.descripcion,
            "columna": d["columna"], "fila": d["fila"], "ancho": d["ancho"], "alto": d["alto"],
        })

    salida_llm = _SalidaDirectorLLM.model_validate({
        "id_escena": escena.id,
        "posicionamiento": datos.get("posicionamiento", []),
        "decorados": decos,
    })
    # AIMessage canónico (formato combinado) → el retry ve exactamente lo mismo
    messages = messages + [AIMessage(content=salida_llm.model_dump_json())]
    return salida_llm, messages


def _reparar_interior(salida: SalidaDirector, escena: Escena) -> int:
    """Reparación determinista para interiores (rejilla rectangular 7×7):
    clampa celdas a 0-6, inserta narrativos omitidos (preferencia: centro) y resuelve
    colisiones exactas moviendo a la celda libre más cercana. Devuelve nº de intervenciones."""
    N = _GRID_INT_N
    n = 0

    # 1. Clamp de celdas al rango de la rejilla
    for e in salida.elementos:
        c = max(0, min(N - 1, e.posicion_grid.columna))
        f = max(0, min(N - 1, e.posicion_grid.fila))
        if (c, f) != (e.posicion_grid.columna, e.posicion_grid.fila):
            e.posicion_grid = PosicionGrid(columna=c, fila=f)
            n += 1

    ocupadas = {(e.posicion_grid.columna, e.posicion_grid.fila) for e in salida.elementos}

    def _celda_libre(preferir_centro: bool) -> tuple[int, int]:
        celdas = [(c, f) for f in range(N) for c in range(N) if (c, f) not in ocupadas]
        if not celdas:
            return (0, 0)
        if preferir_centro:
            celdas.sort(key=lambda cf: abs(cf[0] - 3) + abs(cf[1] - 3))
        return celdas[0]

    # 2. Cobertura: insertar narrativos que el LLM omitió (al centro)
    pers_map = {p.id: p for p in escena.personajes}
    obj_map  = {o.id: o for o in escena.objetos}
    presentes = {e.id for e in salida.elementos}
    for nid in sorted((set(pers_map) | set(obj_map)) - presentes):
        col, fila = _celda_libre(preferir_centro=True)
        ocupadas.add((col, fila))
        if nid in pers_map:
            p = pers_map[nid]
            salida.elementos.append(ElementoEscena(
                id=p.id, nombre=p.nombre, tipo="personaje", origen="narrativo",
                skin_id=p.skin_id, descripcion=p.fisica or p.nombre,
                posicion_grid=PosicionGrid(columna=col, fila=fila), ancho=1.0, alto=1.8,
            ))
        else:
            o = obj_map[nid]
            salida.elementos.append(ElementoEscena(
                id=o.id, nombre=o.nombre, tipo="objeto", origen="narrativo",
                skin_id=o.skin_id, descripcion=o.descripcion or o.nombre,
                posicion_grid=PosicionGrid(columna=col, fila=fila), ancho=0.8, alto=0.8,
            ))
        n += 1
        logger.warning(f"[Director/Interior] Narrativo '{nid}' omitido — insertado en ({col},{fila}).")

    # 3. Colisiones exactas: el segundo (y siguientes) en una celda se mueve a una libre
    vistas: set[tuple[int, int]] = set()
    for e in salida.elementos:
        key = (e.posicion_grid.columna, e.posicion_grid.fila)
        if key in vistas:
            col, fila = _celda_libre(preferir_centro=False)
            ocupadas.add((col, fila))
            e.posicion_grid = PosicionGrid(columna=col, fila=fila)
            vistas.add((col, fila))
            n += 1
        else:
            vistas.add(key)

    return n


def ejecutar_director(
    escena: Escena,
    provider: str = "mercury",
    mensajes_previos: list | None = None,
    idioma: str = "es",
) -> tuple[SalidaDirector, list]:
    """
    Planifica la escena en dos pasadas (primer intento) o una combinada (reintento).

    Primer intento (mensajes_previos=None):
      P1 — el LLM inventa los decorados (sin posiciones todavía).
      P2 — el LLM posiciona TODO (narrativos + decorados de P1) con foco en composición dramática.
      Devuelve mensajes sintéticos en formato combinado para que el grafo pueda
      inyectar feedback de error si el validador rechaza la salida.

    Reintento (mensajes_previos presente):
      Pasada combinada única con el historial acumulado + feedback del validador,
      para que el LLM corrija su salida previa en un solo paso.

    Returns:
        (SalidaDirector, mensajes_completos)
    Raises:
        AgentError: Si el JSON o el schema son inválidos.
        RuntimeError: En errores irrecuperables de infraestructura.
    """
    llm = get_llm(provider)
    P = get_prompts(idioma)
    messages: list = mensajes_previos or []

    try:
        if mensajes_previos:
            # ── REINTENTO: pasada combinada ───────────────────────────────────
            messages = mensajes_previos
            respuesta = llm.invoke(messages)
            messages = messages + [respuesta]
            logger.debug(
                f"[Director/Retry] JSON crudo ({escena.id}):\n{respuesta.content[:300]}"
            )
            datos = json.loads(_limpiar_json(respuesta.content))
            salida_llm = _SalidaDirectorLLM.model_validate(datos)
            salida = _reconstruir_salida(salida_llm, escena)

        elif _es_interior_caja(escena):
            # ── PRIMER INTENTO (INTERIOR): P1 + pasada rectangular ────────────
            # P1 inventa decorados; la pasada de interior los posiciona (con los
            # narrativos) sobre la rejilla 7×7. Emite formato combinado → el retry
            # del grafo lo reutiliza sin ramas extra.
            salida_p1, _ = _ejecutar_p1(escena, llm, P)
            salida_llm, messages = _ejecutar_interior(escena, salida_p1.decorados, llm, P)
            salida = _reconstruir_salida(salida_llm, escena)

        else:
            # ── PRIMER INTENTO: dos pasadas ───────────────────────────────────
            # P1: inventa decorados (sin posiciones)
            salida_p1, _ = _ejecutar_p1(escena, llm, P)

            # P2: posiciona todo (narrativos + decorados de P1)
            try:
                salida_p2, _ = _ejecutar_p2(escena, salida_p1.decorados, llm, P)
                elementos     = _reconstruir_desde_p2(
                    salida_p2.posicionamiento, escena, salida_p1.decorados
                )
            except Exception as e:
                logger.warning(
                    f"[Director/P2] Fallo ({e}). "
                    "Sin posicionamiento — el validador gestionará el reintento."
                )
                salida_p2 = _P2Salida(posicionamiento=[])
                elementos  = []

            salida = SalidaDirector(id_escena=escena.id, elementos=elementos)

            # Mensajes sintéticos en formato combinado para compatibilidad con el retry.
            # Separamos el posicionamiento de P2 en narrativos y decorados para encajar
            # en el esquema _SalidaDirectorLLM que espera el camino de reintento.
            pers_ids = {p.id for p in escena.personajes}
            obj_ids  = {o.id for o in escena.objetos}
            dec_map  = {d.id: d for d in salida_p1.decorados}

            pos_narrativos = []
            pos_decorados  = []
            for pos in salida_p2.posicionamiento:
                if pos.id in pers_ids or pos.id in obj_ids:
                    pos_narrativos.append(pos.model_dump())
                elif pos.id in dec_map:
                    d = dec_map[pos.id]
                    pos_decorados.append({
                        "id": pos.id, "nombre": d.nombre, "descripcion": d.descripcion,
                        "columna": pos.columna, "fila": pos.fila,
                        "ancho": pos.ancho, "alto": pos.alto,
                    })

            ids_personajes = [p.id for p in escena.personajes]
            ids_objetos    = [o.id for o in escena.objetos]
            narrativos_obligatorios = (
                f"  Personajes: {', '.join(ids_personajes) or '(ninguno)'}\n"
                f"  Objetos:    {', '.join(ids_objetos) or '(ninguno)'}"
            )
            user_prompt = P.DIRECTOR_USER.format(
                escena_json=json.dumps(escena.model_dump(), indent=2, ensure_ascii=False),
                id_escena=escena.id,
                entorno=escena.entorno,
                atmosfera=escena.atmosfera,
                narrativos_obligatorios=narrativos_obligatorios,
            )
            output_combinado = json.dumps({
                "id_escena": escena.id,
                "posicionamiento": pos_narrativos,
                "decorados": pos_decorados,
            }, ensure_ascii=False, indent=2)
            messages = [
                SystemMessage(content=P.DIRECTOR_SYSTEM),
                HumanMessage(content=user_prompt),
                AIMessage(content=output_combinado),
            ]

        # ── Reparación determinista de layout ─────────────────────────────────
        # Si P2 falló del todo (sin elementos), saltamos el repair — el validador
        # gestionará el reintento con el historial de error limpio.
        if salida.elementos:
            _quitar_decorados_arquitectonicos(salida)   # fuera ventanales/puertas (los pinta el viewer)
            if _es_interior_caja(escena):
                # Interior: reparación sobre la rejilla rectangular (colisiones + cobertura)
                # + red de seguridad de ambientación (rellena el perímetro si falta densidad).
                n_int = _reparar_interior(salida, escena)
                _poblar_unidades_arquetipo(salida, escena)   # pupitres/mesas/estanterías repetidos
                _poblar_sillas_mesas(salida, escena)         # sillas pegadas a cada mesa
                _poblar_interior_seguridad(salida, escena)   # relleno genérico del perímetro
                metricas.registrar_reparacion_director(escena.id, n_int, 0, 0)
            else:
                n_narr = _reparar_narrativos(salida, escena)  # primero: garantiza cobertura
                if escena.tipo_ambiente == "barco":
                    _reparar_cubierta_barco(salida)           # sube props de cubierta al barco
                n_sep  = _reparar_separacion(salida, escena.cielo, escena.tipo_ambiente)
                n_col  = _reparar_colisiones_exactas(salida)
                metricas.registrar_reparacion_director(escena.id, n_narr, n_sep, n_col)

        n_dec = sum(1 for e in salida.elementos if e.tipo == "decorado")
        logger.info(
            f"[Director] '{escena.id}': {len(salida.elementos)} elementos "
            f"({n_dec} decorados)."
        )
        return salida, messages

    except json.JSONDecodeError as e:
        raise AgentError(f"JSON inválido: {e}", messages) from e
    except AgentError:
        raise
    except Exception as e:
        error_str = str(e)
        if any(k in error_str for k in ["memory", "status code: 5", "Connection refused"]):
            raise RuntimeError(f"[Director] Error irrecuperable: {error_str}") from e
        raise AgentError(f"Schema inválido: {e}", messages) from e