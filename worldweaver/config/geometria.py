"""
Geometría del escenario cilíndrico — fuente única de verdad.

Grid pirámide: 7 filas (0=horizonte, 6=primer plano) × columnas variables.
La columna se proyecta a ángulo dentro del arco de la fila; la fila, a radio
desde el centro.

Consumidores:
  - agents/constructor.py  → proyección grid → coordenadas 3D
  - agents/director.py     → reparación determinista de separación física
  - pipeline/validators.py → rangos de columna válidos por fila

Cualquier cambio aquí afecta a los tres a la vez — esa es la idea.
"""

# Tipos de cielo que corresponden a escenas de interior
INTERIOR_TIPOS = {"interior_calido", "interior_frio", "interior_luminoso"}

# Ambientes que usan parámetros de interior grande aunque su cielo sea interior
INTERIOR_GRANDES = {"cueva", "interior_grande"}

# Radio de la cubierta (deck) por variante de barco. DEBE coincidir con el campo R de
# _VARIANTES_BARCO en sandbox/js/scene_loader.js (el viewer dibuja el casco con estos
# radios). El Constructor usa esto para colocar la rejilla de cubierta dentro de la borda.
RADIO_CUBIERTA_BARCO = {"balsa": 5.6, "barco": 6.2, "galeon": 6.8}

# Columnas válidas por fila (pirámide): menos columnas cuanto más cerca del jugador
N_COLS_POR_FILA = {0: 9, 1: 7, 2: 5, 3: 8, 4: 7, 5: 5, 6: 3}

# ── Interior pequeño (cabaña, taberna, habitación, bodega) ─────────────────
# Sala cuadrada de 2·radio de lado (rejilla rectangular). 8.0 → 16×16, acogedor
# para una habitación normal sin quedar demasiado amplio.
RADIO_CILINDRO_INTERIOR = 8.0
RADIO_POR_FILA_INTERIOR = {0: 9.0, 1: 7.0, 2: 5.5, 3: 3.5, 4: 2.5, 5: 1.5, 6: 0.8}
ARCO_POR_FILA_INTERIOR  = {0: 300, 1: 240, 2: 180, 3: 300, 4: 240, 5: 180, 6: 120}
PLAYER_LIMIT_INT        = 5.0

# ── Habitación / cuarto (dormitorio, estudio, celda, baño, camarote) ───────
# El interior MÁS reducido: sala cuadrada de 2·radio. 5.5 → 11×11, íntimo, para
# que un dormitorio de una persona no se vea como un salón. Reusa las rampas de
# radio/arco del interior pequeño (en interiores la rejilla es rectangular y solo
# importa el radio).
RADIO_CILINDRO_HABITACION = 5.5
PLAYER_LIMIT_HABITACION   = 3.3

# ── Interior grande (cueva, cripta, catedral, estadio, discoteca) ──────────
# Sala cuadrada de 2·radio de lado. 13.0 → 26×26: grande/solemne pero sin verse
# vacío (16.0 = 32×32 dejaba los objetos perdidos).
RADIO_CILINDRO_INTERIOR_GRANDE = 13.0
RADIO_POR_FILA_INTERIOR_GRANDE = {0: 14.0, 1: 10.0, 2: 7.5, 3: 5.5, 4: 3.5, 5: 2.0, 6: 1.0}
ARCO_POR_FILA_INTERIOR_GRANDE  = {0: 300, 1: 260, 2: 220, 3: 300, 4: 240, 5: 180, 6: 120}
PLAYER_LIMIT_INT_GRANDE        = 7.0

# ── Exterior (espacio abierto) ────────────────────────────────────────────
# Jugable hasta radio 6.5. Fila 3 a 5.5 → alcanzable. Fila 2 a 9.0 → no.
RADIO_CILINDRO_EXTERIOR = 22.0
RADIO_POR_FILA_EXTERIOR = {0: 20.0, 1: 14.0, 2: 9.0, 3: 5.5, 4: 3.5, 5: 2.0, 6: 1.0}
ARCO_POR_FILA_EXTERIOR  = {0: 340,  1: 300,  2: 240, 3: 300, 4: 240, 5: 180, 6: 120}
PLAYER_LIMIT_EXT        = 6.5

# El fondo marino usa un cilindro más amplio para mayor sensación de profundidad oceánica.
RADIO_CILINDRO_BAJO_AGUA = 28.0

# ── Barco (cubierta jugable + agua caminable alrededor) ────────────────────
# Usa la geometría exterior (radio_cilindro 22) pero con un límite de jugador algo
# mayor que el exterior normal: al desembarcar (tecla B) hay que poder alcanzar los
# narrativos que flotan en el agua junto al casco (anillo cercano ≈ radio_cubierta+2.5,
# como mucho 6.8+2.5=9.3 en galeón). 9.0 cubre ese anillo sin dejar caminar hasta el
# horizonte. _planificar_barco clampa los narrativos de agua a < este límite.
PLAYER_LIMIT_BARCO = 9.0


def posiciones_ventanas_interior(radio: float, tipo_cielo: str) -> list[tuple[float, float]]:
    """
    (x, z) aproximados de los centros de ventana que el viewer dibuja en un interior en
    caja. DEBE coincidir con sandbox/js/scene_loader.js::crearHabitacion: mismo offset
    0.4·radio en las paredes derecha (+X), izquierda (−X) y fondo (+Z); la pared frontal
    (−Z) lleva la puerta, no ventanas; interior_frio no lleva ninguna.

    Lo usa el pase de coherencia del Constructor para no plantar muebles altos delante de
    una ventana. (Único punto donde el Constructor conoce las ventanas; si cambia el
    layout en el viewer, actualizar aquí también.)
    """
    if tipo_cielo == "interior_frio":
        return []
    o = radio * 0.4
    return [
        ( radio, -o), ( radio, o),   # pared derecha (+X)
        (-radio, -o), (-radio, o),   # pared izquierda (−X)
        (-o, radio), ( o, radio),    # pared fondo (+Z)
    ]


def params_escena(tipo_cielo: str, tipo_ambiente: str = "") -> tuple[float, dict, dict, str, float]:
    """Devuelve (radio_cilindro, radio_por_fila, arco_por_fila, tipo_escena, player_limit)."""
    if tipo_cielo in INTERIOR_TIPOS or tipo_ambiente in {"interior", "interior_grande", "cueva", "habitacion"}:
        if tipo_ambiente in INTERIOR_GRANDES:
            return (
                RADIO_CILINDRO_INTERIOR_GRANDE,
                RADIO_POR_FILA_INTERIOR_GRANDE,
                ARCO_POR_FILA_INTERIOR_GRANDE,
                "interior",
                PLAYER_LIMIT_INT_GRANDE,
            )
        if tipo_ambiente == "habitacion":
            return (
                RADIO_CILINDRO_HABITACION,
                RADIO_POR_FILA_INTERIOR,
                ARCO_POR_FILA_INTERIOR,
                "interior",
                PLAYER_LIMIT_HABITACION,
            )
        return (
            RADIO_CILINDRO_INTERIOR,
            RADIO_POR_FILA_INTERIOR,
            ARCO_POR_FILA_INTERIOR,
            "interior",
            PLAYER_LIMIT_INT,
        )
    if tipo_ambiente == "barco":
        # Geometría exterior, pero límite de jugador algo mayor para alcanzar los
        # narrativos que flotan en el agua junto al casco al desembarcar.
        return (
            RADIO_CILINDRO_EXTERIOR,
            RADIO_POR_FILA_EXTERIOR,
            ARCO_POR_FILA_EXTERIOR,
            "exterior",
            PLAYER_LIMIT_BARCO,
        )
    return (
        RADIO_CILINDRO_EXTERIOR,
        RADIO_POR_FILA_EXTERIOR,
        ARCO_POR_FILA_EXTERIOR,
        "exterior",
        PLAYER_LIMIT_EXT,
    )
