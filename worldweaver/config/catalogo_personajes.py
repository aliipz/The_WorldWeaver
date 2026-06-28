"""
Catálogo de personajes del pack Quaternius — Ultimate Animated Character Pack.
Los GLBs están en sandbox/assets/characters/.

Cada entrada describe el personaje para que el LLM pueda elegir el más adecuado
según la descripción narrativa. Las entradas de accesorios (sombreros sueltos, pelucas)
NO se incluyen — son complementos del BaseCharacter, no personajes autónomos.

Campos:
  id                  — nombre del fichero sin extensión (= glb_id)
  label               — nombre legible
  descripcion         — descripción para el LLM (edad, aspecto, rol típico)
  categoria           — agrupación (civil, formal, profesional, combate, fantasy, monstruo, animal)
  tiene_hair          — True si el GLB contiene material "Hair" (color personalizable)
  permite_skin_humana — True si el personaje acepta tonos de piel humana
                        False para goblins, zombies, animales (usan skin_defecto_hex)
  skin_defecto_hex    — hex de piel por defecto para personajes no-humanos
  animacion_talk      — animación más cercana a "hablar" para este personaje
"""

PERSONAJES: list[dict] = [

    # ── Civiles casuales ───────────────────────────────────────────────────────
    {
        "id": "Casual_Male",
        "label": "Chico casual",
        "descripcion": "Joven adulto con camiseta y pantalones informales. Apto para cualquier civil, aldeano, ciudadano, joven de pueblo o ciudad.",
        "categoria": "civil",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Casual_Female",
        "label": "Chica casual",
        "descripcion": "Joven adulta con ropa informal moderna. Apta para civiles, aldeanas, viajeras, amigas o protagonistas cotidianas.",
        "categoria": "civil",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Casual_Bald",
        "label": "Hombre calvo casual",
        "descripcion": "Adulto calvo con ropa informal. Personaje de aspecto neutro, puede ser comerciante, lugareño o ciudadano anónimo.",
        "categoria": "civil",
        "tiene_hair": False,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Idle",
    },
    {
        "id": "Casual2_Male",
        "label": "Chico casual 2",
        "descripcion": "Joven adulto con atuendo informal variante. Similar al casual estándar pero con ropa diferente (camisa con detalle, cinturón).",
        "categoria": "civil",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Casual2_Female",
        "label": "Chica casual 2",
        "descripcion": "Joven adulta con outfit informal variante. Alternativa visual a la chica casual estándar.",
        "categoria": "civil",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Casual3_Male",
        "label": "Chico casual 3",
        "descripcion": "Joven adulto con tercera variante de ropa informal. Pantalón y camisa de estilo diferente al Casual o Casual2.",
        "categoria": "civil",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Casual3_Female",
        "label": "Chica casual 3",
        "descripcion": "Joven adulta con tercera variante de ropa informal. Alternativa visual diferente a las otras casuales.",
        "categoria": "civil",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },

    # ── Elegantes / formales ───────────────────────────────────────────────────
    {
        "id": "Suit_Male",
        "label": "Caballero de traje",
        "descripcion": "Adulto con traje de negocios moderno. Para ejecutivos, nobles, diplomáticos, empresarios o personajes de autoridad.",
        "categoria": "formal",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Idle",
    },
    {
        "id": "Suit_Female",
        "label": "Dama de traje",
        "descripcion": "Adulta con traje de negocios elegante. Para ejecutivas, nobles, investigadoras, funcionarias o personajes de autoridad femeninos.",
        "categoria": "formal",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "OldClassy_Male",
        "label": "Caballero mayor elegante",
        "descripcion": "Hombre mayor con sombrero de copa y traje oscuro de época. Ideal para nobles, mecenas, alquimistas, comerciantes adinerados o personajes de estilo victoriano.",
        "categoria": "formal",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "OldClassy_Female",
        "label": "Dama mayor elegante",
        "descripcion": "Mujer mayor con vestido largo y sombrero de época. Para damas de alcurnia, hechiceras de alta sociedad, aristócratas o ancianas sabias y elegantes.",
        "categoria": "formal",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },

    # ── Profesionales ──────────────────────────────────────────────────────────
    {
        "id": "Doctor_Male_Young",
        "label": "Médico joven",
        "descripcion": "Joven adulto con bata de médico o científico. Para doctores, investigadores, científicos, alquimistas o curanderos.",
        "categoria": "profesional",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Doctor_Female_Young",
        "label": "Médica joven",
        "descripcion": "Joven adulta con bata de médico. Para doctoras, científicas, investigadoras o curanderas.",
        "categoria": "profesional",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Doctor_Male_Old",
        "label": "Médico mayor",
        "descripcion": "Hombre mayor con bata de médico. Para doctores veteranos, maestros, sabios científicos o alquimistas experimentados.",
        "categoria": "profesional",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Doctor_Female_Old",
        "label": "Médica mayor",
        "descripcion": "Mujer mayor con bata de médico o científica. Para doctoras veteranas, curanderas sabias o magas estudiosas.",
        "categoria": "profesional",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Chef_Male",
        "label": "Chef masculino",
        "descripcion": "Adulto con uniforme de cocinero (delantal, gorro de chef). Para cocineros, posaderos, taberneros o cualquier personaje relacionado con comida.",
        "categoria": "profesional",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Chef_Female",
        "label": "Chef femenina",
        "descripcion": "Adulta con uniforme de cocinera. Para cocineras, posaderas, taberneras o personajes relacionados con gastronomía.",
        "categoria": "profesional",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Worker_Male",
        "label": "Obrero masculino",
        "descripcion": "Adulto con ropa de trabajo (chaleco, pantalón resistente). Para obreros, herreros, carpinteros, mineros, constructores o artesanos.",
        "categoria": "profesional",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Worker_Female",
        "label": "Obrera femenina",
        "descripcion": "Adulta con ropa de trabajo resistente. Para obreras, artesanas, campesinas trabajadoras o personajes de clase trabajadora.",
        "categoria": "profesional",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },

    # ── Combate / militar ──────────────────────────────────────────────────────
    {
        "id": "Soldier_Male",
        "label": "Soldado masculino",
        "descripcion": "Adulto con uniforme militar o armadura ligera. Para soldados rasos, guardias, mercenarios o aventureros combatientes.",
        "categoria": "combate",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Soldier_Female",
        "label": "Soldada femenina",
        "descripcion": "Adulta con uniforme militar o armadura ligera. Para soldadas, guardias, mercenarias o aventureras combatientes.",
        "categoria": "combate",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "BlueSoldier_Male",
        "label": "Soldado élite masculino",
        "descripcion": "Soldado adulto con armadura más completa en tonos azules y grises. Para guardias reales, soldados de élite o combatientes veteranos.",
        "categoria": "combate",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "BlueSoldier_Female",
        "label": "Soldada élite femenina",
        "descripcion": "Soldada adulta con armadura élite en azul/gris. Para guardias de élite o guerreras veteranas.",
        "categoria": "combate",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Knight_Male",
        "label": "Caballero con armadura",
        "descripcion": "Guerrero adulto con armadura completa de caballero medieval. Para caballeros, paladines, guerreros de orden o héroes épicos masculinos.",
        "categoria": "combate",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Knight_Golden_Male",
        "label": "Caballero dorado",
        "descripcion": "Guerrero adulto con armadura dorada ceremonial. Para caballeros de alto rango, campeones, generales o figuras heroicas de élite.",
        "categoria": "combate",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Knight_Golden_Female",
        "label": "Caballera dorada",
        "descripcion": "Guerrera adulta con armadura dorada. Para paladinas, caballeras de élite o heroínas épicas.",
        "categoria": "combate",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },

    # ── Vaqueros / piratas ─────────────────────────────────────────────────────
    {
        "id": "Cowboy_Male",
        "label": "Vaquero",
        "descripcion": "Adulto con sombrero de cowboy, chaleco y pistolera. Para vaqueros, forajidos del Oeste, aventureros del desierto o exploradores.",
        "categoria": "western",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Cowboy_Female",
        "label": "Vaquera",
        "descripcion": "Adulta con atuendo de cowgirl. Para vaqueras, exploradoras del Oeste o aventureras de ambientes áridos.",
        "categoria": "western",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Pirate_Male",
        "label": "Pirata masculino",
        "descripcion": "Adulto con atuendo de pirata (pañuelo, chaleco, espada). Para piratas, corsarios, marineros o aventureros del mar.",
        "categoria": "western",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Pirate_Female",
        "label": "Pirata femenina",
        "descripcion": "Adulta con atuendo de pirata. Para piratas, corsarias, capitanas de barco o aventureras marítimas.",
        "categoria": "western",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },

    # ── Fantasy humano ─────────────────────────────────────────────────────────
    {
        "id": "Viking_Male",
        "label": "Vikingo",
        "descripcion": "Guerrero nórdico adulto con armadura de piel y metal, barba y aspecto robusto. Para vikingos, bárbaros nórdicos, guerreros tribales o exploradores del norte.",
        "categoria": "fantasy",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Viking_Female",
        "label": "Vikinga",
        "descripcion": "Guerrera nórdica adulta con armadura de piel. Para escuderas vikingas, guerreras bárbaras o mujeres del norte.",
        "categoria": "fantasy",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Ninja_Male",
        "label": "Ninja masculino",
        "descripcion": "Adulto con traje oscuro de ninja/asesino. Para ninjas, asesinos, espías o guerreros de las sombras masculinos.",
        "categoria": "fantasy",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Ninja_Female",
        "label": "Ninja femenina",
        "descripcion": "Adulta con traje de ninja. Para ninjás, asesinas o guerreras de las sombras femeninas.",
        "categoria": "fantasy",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Ninja_Sand",
        "label": "Ninja del desierto",
        "descripcion": "Adulto con traje de ninja en tonos arena/beige. Para guerreros del desierto, asesinos de climas áridos o espías de culturas orientales.",
        "categoria": "fantasy",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Ninja_Sand_Female",
        "label": "Ninja del desierto femenina",
        "descripcion": "Adulta con traje de ninja en tonos arena. Variante femenina del ninja del desierto.",
        "categoria": "fantasy",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Kimono_Male",
        "label": "Guerrero con kimono",
        "descripcion": "Adulto con kimono japonés y atuendo oriental. Para samuráis, maestros de artes marciales, eruditos orientales o personajes de ambientación japonesa.",
        "categoria": "fantasy",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Kimono_Female",
        "label": "Mujer con kimono",
        "descripcion": "Adulta con kimono japonés elegante. Para geishas, sacerdotisas, nobles orientales o mujeres de ambientación japonesa.",
        "categoria": "fantasy",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Elf",
        "label": "Elfo",
        "descripcion": "Personaje élfico con orejas puntiagudas, ropa de exploradorforest y aspecto esbelto. Sin pelo visible (lleva capucha o lo tiene recogido). Para elfos, hadas mayores, guardianes del bosque o seres del mundo feérico.",
        "categoria": "fantasy",
        "tiene_hair": False,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Wizard",
        "label": "Mago con túnica y sombrero",
        "descripcion": "Personaje mágico con túnica larga y sombrero puntiagudo. Icono del mago clásico de fantasía. Para hechiceros, brujos ancianos, magos de torre o asesores mágicos.",
        "categoria": "fantasy",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },
    {
        "id": "Witch",
        "label": "Bruja con sombrero",
        "descripcion": "Mujer con sombrero de bruja, vestido oscuro y aspecto misterioso. Para brujas, hechiceras, herbolarias o mujeres con poderes mágicos.",
        "categoria": "fantasy",
        "tiene_hair": True,
        "permite_skin_humana": True,
        "skin_defecto_hex": None,
        "animacion_talk": "Victory",
    },

    # ── Monstruos / criaturas fantásticas ──────────────────────────────────────
    {
        "id": "Goblin_Male",
        "label": "Goblin macho",
        "descripcion": "Criatura goblin masculina con piel verdosa, orejas puntiagudas y aspecto amenazante. Para goblins, duendes maliciosos, criaturas de mazmorra o enemigos menores.",
        "categoria": "monstruo",
        "tiene_hair": False,
        "permite_skin_humana": False,
        "skin_defecto_hex": "#5C8A3A",
        "animacion_talk": "Victory",
    },
    {
        "id": "Goblin_Female",
        "label": "Goblin hembra",
        "descripcion": "Criatura goblin femenina con piel verdosa. Variante femenina del goblin, igualmente astuta y peligrosa.",
        "categoria": "monstruo",
        "tiene_hair": True,
        "permite_skin_humana": False,
        "skin_defecto_hex": "#5C8A3A",
        "animacion_talk": "Victory",
    },
    {
        "id": "Zombie_Male",
        "label": "Zombi masculino",
        "descripcion": "No-muerto masculino con aspecto descompuesto, ropa harapienta y piel putrefacta gris-verdosa. Para zombis, muertos vivientes, siervos necróticos o amenazas del más allá.",
        "categoria": "monstruo",
        "tiene_hair": False,
        "permite_skin_humana": False,
        "skin_defecto_hex": "#8A9A7A",
        "animacion_talk": "Victory",
    },
    {
        "id": "Zombie_Female",
        "label": "Zombi femenina",
        "descripcion": "No-muerta femenina con aspecto descompuesto. Para zombis femeninas, brujas muertas resucitadas o sirvientas necróticas.",
        "categoria": "monstruo",
        "tiene_hair": True,
        "permite_skin_humana": False,
        "skin_defecto_hex": "#8A9A7A",
        "animacion_talk": "Victory",
    },

    # ── Animales / criaturas ───────────────────────────────────────────────────
    {
        "id": "Cow",
        "label": "Vaca",
        "descripcion": "Animal bovino con manchas. Para granjas, aldeas rurales, escenas campestres o como personaje cómico/mágico.",
        "categoria": "animal",
        "tiene_hair": False,
        "permite_skin_humana": False,
        "skin_defecto_hex": "#C8A06A",
        "animacion_talk": "Victory",
    },
    {
        "id": "Pug",
        "label": "Pug (perrito)",
        "descripcion": "Perro de raza pug (carlino) de aspecto gracioso. Para mascotas, compañeros o animales cómicos en escenas cotidianas.",
        "categoria": "animal",
        "tiene_hair": False,
        "permite_skin_humana": False,
        "skin_defecto_hex": "#B8956A",
        "animacion_talk": "Victory",
    },
]

# ── Índice por id para lookup rápido ──────────────────────────────────────────
CATALOGO: dict[str, dict] = {p["id"]: p for p in PERSONAJES}

# ── Opciones de tono de piel para el LLM ────────────────────────────────────
SKIN_TONES: list[str] = ["muy_claro", "medio", "oscuro", "muy_oscuro"]

SKIN_TONE_HEX: dict[str, str] = {
    "muy_claro": "#FFCBA4",
    "medio":     "#D4956A",
    "oscuro":    "#7B4B2A",
    "muy_oscuro":"#2D1001",
}

# ── Opciones de color de pelo para el LLM ────────────────────────────────────
HAIR_COLORS: list[str] = [
    "negro", "castano_oscuro", "castano_claro", "rubio",
    "pelirrojo", "gris", "blanco",
    "rojo", "azul", "verde",
]

# ── Tallas disponibles ────────────────────────────────────────────────────────
# Altura final en unidades 3D (el jugador mide 1.8u).
# Los GLBs de Quaternius miden ~3.15u en crudo; estas alturas anulan lo del Director.
TALLAS: list[str] = ["adulto_alto", "adulto_medio", "adulto_bajo", "nino_enano"]

TALLA_ALTURA: dict[str, float] = {
    "adulto_alto":  2.05,   # guerreros con armadura, magos con sombrero alto
    "adulto_medio": 1.80,   # adulto estándar (ligeramente por debajo del jugador)
    "adulto_bajo":  1.55,   # ancianos, personajes más bajos
    "nino_enano":   0.95,   # goblins, niños, mascotas, criaturas pequeñas
}

# Talla por defecto para cada personaje del catálogo.
# El LLM puede sobrescribir esto si la descripción narrativa lo justifica
# (e.g., "un goblin gigante" → adulto_medio).
TALLA_DEFECTO: dict[str, str] = {
    # Adulto alto: armadura, sombrero de copa, sombrero de bruja
    "Viking_Male":          "adulto_alto",
    "Viking_Female":        "adulto_alto",
    "Knight_Male":          "adulto_alto",
    "Knight_Golden_Male":   "adulto_alto",
    "Knight_Golden_Female": "adulto_alto",
    "Wizard":               "adulto_alto",
    "Witch":                "adulto_alto",
    "OldClassy_Male":       "adulto_alto",
    "OldClassy_Female":     "adulto_alto",
    "BlueSoldier_Male":     "adulto_alto",
    "BlueSoldier_Female":   "adulto_alto",
    # Adulto bajo: ancianos, cuadrúpedos
    "Doctor_Male_Old":      "adulto_bajo",
    "Doctor_Female_Old":    "adulto_bajo",
    "Cow":                  "adulto_bajo",
    # Niño/Enano: criaturas pequeñas y mascotas
    "Goblin_Male":          "nino_enano",
    "Goblin_Female":        "nino_enano",
    "Pug":                  "nino_enano",
    # Todo lo demás → adulto_medio (por defecto si no está en este dict)
}
