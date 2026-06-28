"""
Agente 4 — El Dibujante
Entrada:  SceneGraph (output del Constructor)
Salida:   SalidaDibujante con rutas a los PNGs generados

────────────────────────────────────────────────────────────
FASE 0 — Pre-generación de personajes globales  [PENDIENTE]
  Una sola vez por historia, antes de procesar escenas:
    → genera imagen canónica base con fal-ai/flux/dev + LoRA de estilo
    → guarda en outputs/assets/personajes/<id>_base.png
  Activar pasando `bases_personajes` a ejecutar_dibujante().

  [PENDIENTE — LoRA]
  Una vez entrenado el LoRA con las imágenes de assets/references/,
  reemplazar el endpoint "fal-ai/flux/dev" por "fal-ai/flux-lora"
  y añadir en los argumentos:
      "loras": [{"path": settings.lora_url, "scale": 0.9}]
  El trigger word del LoRA debe incluirse en el prompt:
      prompt = f"{nodo.prompt_imagen}, nanobanana_style. Style: {estilo}"
  Añadir en settings.py:
      lora_url: str = ""

FASE 1 — Generación por escena  [ACTIVA]
  Para cada nodo del SceneGraph:
    · personaje global  → [PENDIENTE] fal-ai/flux-pulid (imagen_base + variación)
                          Por ahora usa el flujo estándar.
    · personaje puntual → fal-ai/flux/dev + imagen de referencia de estilo
    · objeto / decorado → fal-ai/flux/dev + imagen de referencia de estilo
    · fondo             → fal-ai/flux/dev + imagen de referencia panorámica
    · suelo             → fal-ai/flux/dev + imagen de referencia de suelo
  Resolución dinámica: proporcional a nodo.ancho / nodo.alto (SceneGraph).
  Fondo y suelo: resolución fija (cilindro panorámico + círculo).
  Personaje / objeto / decorado: rembg elimina el fondo.
  Fondo y suelo: se conserva la imagen completa (son texturas).

Providers disponibles (parámetro `modo`):
  "fal"    → fal.ai FLUX.1-dev  (requiere FAL_KEY en .env)
  "gemini" → Gemini 2.0 Flash   (requiere GEMINI_API_KEY en .env)
  "mock"   → placeholders de color, sin API  (para testear el pipeline)
  "auto"   → fal si FAL_KEY presente, gemini si GEMINI_API_KEY, sino mock

Convención de rutas de salida:
  outputs/assets/<id_escena>/<id_nodo>.png
  El HTML preview del Constructor referencia estas rutas directamente.
────────────────────────────────────────────────────────────
"""

import io
import os
import logging
import random
from pathlib import Path
from typing import Literal, Optional

from PIL import Image, ImageDraw

from schemas.scene_graph import SceneGraph, NodoEscena
from schemas.assets import SalidaDibujante, AssetGenerado
from schemas.escenas import Personaje
from config.settings import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Rutas
# ─────────────────────────────────────────────────────────────────────────────

_BASE_DIR           = Path(__file__).resolve().parent.parent
REFERENCIAS_DIR     = _BASE_DIR / "assets" / "references"
PERSONAJES_BASE_DIR = _BASE_DIR / "outputs" / "assets" / "personajes"

REFERENCIAS_POR_TIPO: dict[str, Path] = {
    "personaje": REFERENCIAS_DIR / "characters",
    "objeto":    REFERENCIAS_DIR / "objects",
    "decorado":  REFERENCIAS_DIR / "decorado",
    "fondo":     REFERENCIAS_DIR / "backgrounds",
    "suelo":     REFERENCIAS_DIR / "grounds",
}


# ─────────────────────────────────────────────────────────────────────────────
# Resolución dinámica
# ─────────────────────────────────────────────────────────────────────────────

# Píxeles por unidad de mundo 3D (para billboards)
RESOLUCION_BASE = 512

# Límites en píxeles para billboards (múltiplos de 64 requeridos por FLUX)
_MIN_PX = 256
_MAX_PX = 1024

# Resoluciones fijas para geometrías especiales
_RES_FONDO = (2048, 512)   # panorámica para el cilindro
_RES_SUELO = (1024, 1024)  # cuadrada para el círculo


def _calcular_resolucion(nodo: NodoEscena) -> tuple[int, int]:
    """
    Devuelve (ancho_px, alto_px) proporcional a las dimensiones 3D del nodo.
    Fondo y suelo tienen resolución fija independiente del SceneGraph.
    Billboards: se redondea al múltiplo de 64 más cercano, acotado entre
    _MIN_PX y _MAX_PX para no generar imágenes demasiado pequeñas o grandes.
    """
    if nodo.tipo == "fondo":
        return _RES_FONDO
    if nodo.tipo == "suelo":
        return _RES_SUELO

    def _redondear(valor: float) -> int:
        px = round(valor * RESOLUCION_BASE / 64) * 64
        return max(_MIN_PX, min(_MAX_PX, px))

    return (_redondear(nodo.ancho), _redondear(nodo.alto))


# ─────────────────────────────────────────────────────────────────────────────
# Strings de estilo paper-craft
# ─────────────────────────────────────────────────────────────────────────────

_ESTILO_ELEMENTO = (
    "paper-cut pop-up book illustration style, flat 2D layered paper craft, "
    "pure white background, crisp clean edges, no gradients, no drop shadows, "
    "colorful and playful, children's storybook aesthetic, "
    "single subject centered in frame, full body visible"
)
_ESTILO_FONDO = (
    "paper-cut layered diorama panoramic background, wide panoramic format, "
    "multiple depth layers of cut paper, no characters, flat 2D layers, "
    "children's storybook style, seamless horizontal tiling"
)
_ESTILO_SUELO = (
    "paper-cut illustration, circular top-down view, flat 2D texture, "
    "no shadows, no perspective distortion, pure white background outside circle, "
    "children's storybook style, centered"
)

_ESTILOS: dict[str, str] = {
    "personaje": _ESTILO_ELEMENTO,
    "objeto":    _ESTILO_ELEMENTO,
    "decorado":  _ESTILO_ELEMENTO,
    "fondo":     _ESTILO_FONDO,
    "suelo":     _ESTILO_SUELO,
}

_NEGATIVO = (
    "photorealistic, 3D render, shadows, gradients, blurry, "
    "multiple subjects, text, watermark, signature, background noise"
)


# ─────────────────────────────────────────────────────────────────────────────
# Colores placeholder (modo mock)
# ─────────────────────────────────────────────────────────────────────────────

_COLORES_MOCK: dict[str, tuple[int, int, int, int]] = {
    "fondo":     (135, 180, 210, 200),
    "suelo":     (100, 140,  80, 200),
    "personaje": (255, 160, 120, 220),
    "objeto":    (255, 210,  80, 220),
    "decorado":  (140, 200, 100, 220),
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def _prompt_con_estilo(nodo: NodoEscena) -> str:
    estilo = _ESTILOS.get(nodo.tipo, _ESTILO_ELEMENTO)
    return f"{nodo.prompt_imagen}. Style: {estilo}"


def _obtener_referencia(tipo: str) -> Optional[Path]:
    """
    Devuelve una imagen de referencia aleatoria de assets/references/<tipo>/.
    Devuelve None si la carpeta no existe o está vacía.
    """
    carpeta = REFERENCIAS_POR_TIPO.get(tipo)
    if not carpeta or not carpeta.exists():
        logger.debug(f"[Dibujante] Sin carpeta de referencias para tipo '{tipo}'")
        return None
    imagenes = list(carpeta.glob("*.png")) + list(carpeta.glob("*.jpg"))
    if not imagenes:
        logger.debug(f"[Dibujante] Carpeta de referencias vacía: {carpeta}")
        return None
    elegida = random.choice(imagenes)
    logger.debug(f"[Dibujante] Referencia de estilo: {elegida.name}")
    return elegida


def _eliminar_fondo(img: Image.Image) -> Image.Image:
    """
    Elimina el fondo con rembg.
    Si rembg no está disponible o falla, devuelve la imagen original con aviso.
    """
    try:
        from rembg import remove
        buf = io.BytesIO()
        img.save(buf, "PNG")
        resultado = remove(buf.getvalue())
        return Image.open(io.BytesIO(resultado)).convert("RGBA")
    except ImportError:
        logger.warning("[Dibujante] rembg no instalado — imagen sin recortar.")
        return img.convert("RGBA")
    except Exception as exc:
        logger.warning(f"[Dibujante] rembg falló ({exc}) — imagen sin recortar.")
        return img.convert("RGBA")


def _guardar_png(img: Image.Image, ruta: Path) -> tuple[int, int]:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    img.save(ruta, "PNG")
    return img.width, img.height


# ─────────────────────────────────────────────────────────────────────────────
# Modo MOCK
# ─────────────────────────────────────────────────────────────────────────────

def _generar_mock(nodo: NodoEscena, ruta_salida: Path) -> tuple[int, int]:
    """Genera un placeholder de color con nombre y tipo. Sin API."""
    ancho, alto = _calcular_resolucion(nodo)
    color = _COLORES_MOCK.get(nodo.tipo, (200, 200, 200, 200))

    img  = Image.new("RGBA", (ancho, alto), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    p    = 20
    draw.rounded_rectangle(
        [p, p, ancho - p, alto - p],
        radius=30, fill=color, outline=(255, 255, 255, 180), width=3,
    )
    nombre = nodo.nombre if len(nodo.nombre) <= 20 else nodo.nombre[:18] + "…"
    draw.text((ancho // 2, alto // 2),      nombre,           fill=(50, 50, 50, 255), anchor="mm")
    draw.text((ancho // 2, alto // 2 + 35), f"[{nodo.tipo}]", fill=(80, 80, 80, 180), anchor="mm")
    return _guardar_png(img, ruta_salida)


# ─────────────────────────────────────────────────────────────────────────────
# Modo FAL (fal.ai FLUX.1-dev)
# ─────────────────────────────────────────────────────────────────────────────

def _fal_disponible() -> bool:
    return bool(os.environ.get("FAL_KEY") or getattr(settings, "fal_api_key", ""))


def _generar_fal(nodo: NodoEscena, ruta_salida: Path) -> tuple[int, int]:
    """
    Genera imagen con fal-ai/flux/dev.

    Si hay imagen de referencia en assets/references/<tipo>/ se sube a fal.ai
    y se usa como guía de estilo vía img2img (strength=0.65).
    Si no hay referencia, se usa txt2img puro.

    [PENDIENTE — LoRA]
    Cuando el LoRA de estilo esté entrenado, cambiar:
      endpoint  → "fal-ai/flux-lora"
      argumentos → añadir "loras": [{"path": settings.lora_url, "scale": 0.9}]
      prompt    → añadir el trigger word del LoRA (ej: "nanobanana_style")
    """
    import fal_client  # pip install fal-client
    import requests

    fal_key = os.environ.get("FAL_KEY") or getattr(settings, "fal_api_key", "")
    os.environ["FAL_KEY"] = fal_key

    ancho, alto = _calcular_resolucion(nodo)
    prompt      = _prompt_con_estilo(nodo)
    referencia  = _obtener_referencia(nodo.tipo)

    if referencia:
        logger.debug(f"[Dibujante/fal] img2img con referencia: {referencia.name}")
        ref_url  = fal_client.upload_file(str(referencia))
        endpoint = "fal-ai/flux/dev/image-to-image"
        args = {
            "prompt":               prompt,
            "image_url":            ref_url,
            "strength":             0.65,
            "image_size":           {"width": ancho, "height": alto},
            "num_inference_steps":  28,
            "guidance_scale":       3.5,
            "num_images":           1,
            "enable_safety_checker": False,
        }
    else:
        logger.debug(f"[Dibujante/fal] txt2img (sin referencia)")
        endpoint = "fal-ai/flux/dev"
        args = {
            "prompt":               prompt,
            "negative_prompt":      _NEGATIVO,
            "image_size":           {"width": ancho, "height": alto},
            "num_inference_steps":  28,
            "guidance_scale":       3.5,
            "num_images":           1,
            "enable_safety_checker": False,
        }

    logger.debug(f"[Dibujante/fal] {endpoint} | {prompt[:80]}…")
    result    = fal_client.subscribe(endpoint, arguments=args)
    image_url = result["images"][0]["url"]

    resp = requests.get(image_url, timeout=60)
    resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content)).convert("RGBA")

    if nodo.tipo not in ("fondo", "suelo"):
        logger.debug(f"[Dibujante/fal] Eliminando fondo de '{nodo.id}'…")
        img = _eliminar_fondo(img)

    return _guardar_png(img, ruta_salida)


# ─────────────────────────────────────────────────────────────────────────────
# Modo GEMINI (Gemini 2.0 Flash image generation)
# ─────────────────────────────────────────────────────────────────────────────

def _gemini_disponible() -> bool:
    return bool(settings.gemini_api_key)


def _generar_gemini(nodo: NodoEscena, ruta_salida: Path) -> tuple[int, int]:
    """
    Genera imagen con Gemini 2.0 Flash.
    Si hay imagen de referencia la pasa como Part.from_bytes para imitar el estilo.
    La resolución se obtiene de _calcular_resolucion() pero Gemini no acepta
    tamaño explícito, así que redimensionamos el resultado tras recibirlo.
    """
    from google import genai
    from google.genai import types

    client     = genai.Client(api_key=settings.gemini_api_key)
    prompt     = _prompt_con_estilo(nodo)
    referencia = _obtener_referencia(nodo.tipo)

    if referencia:
        logger.debug(f"[Dibujante/gemini] Referencia de estilo: {referencia.name}")
        ref_bytes = referencia.read_bytes()
        mime      = "image/png" if referencia.suffix.lower() == ".png" else "image/jpeg"
        contents  = [
            types.Part.from_bytes(data=ref_bytes, mime_type=mime),
            types.Part.from_text(
                text=f"Use the visual style of this reference image exactly. Now generate: {prompt}"
            ),
        ]
    else:
        contents = [types.Part.from_text(text=prompt)]

    response = client.models.generate_content(
        model="gemini-2.0-flash-preview-image-generation",
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        ),
    )

    img_raw = None
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            img_raw = Image.open(io.BytesIO(part.inline_data.data)).convert("RGBA")
            break

    if img_raw is None:
        raise ValueError(f"[Dibujante/gemini] No se recibió imagen para '{nodo.id}'")

    # Redimensionar al tamaño objetivo manteniendo proporciones del SceneGraph
    ancho, alto = _calcular_resolucion(nodo)
    img = img_raw.resize((ancho, alto), Image.LANCZOS)

    if nodo.tipo not in ("fondo", "suelo"):
        logger.debug(f"[Dibujante/gemini] Eliminando fondo de '{nodo.id}'…")
        img = _eliminar_fondo(img)

    return _guardar_png(img, ruta_salida)


# ─────────────────────────────────────────────────────────────────────────────
# FASE 0 — Pre-generación de personajes globales  [PENDIENTE]
# ─────────────────────────────────────────────────────────────────────────────

def ejecutar_fase0_personajes_globales(
    personajes_globales: list[Personaje],
    modo: str,
) -> dict[str, Path]:
    """
    FASE 0 — Genera la imagen canónica base de cada personaje global.
    Se llama UNA SOLA VEZ por historia antes de procesar las escenas.

    Devuelve dict {personaje_id: Path(imagen_base)} que se pasa a
    ejecutar_dibujante() para activar la consistencia de personajes en Fase 1.

    Estado: NOT IMPLEMENTED — devuelve {} con aviso en el log.
    Implementación pendiente:
      1. Generar con fal-ai/flux/dev (+ LoRA cuando esté entrenado) usando
         un prompt exhaustivo del personaje: ropa, colores, rasgos, pose neutral.
      2. Guardar en PERSONAJES_BASE_DIR / f"{personaje.id}_base.png".
      3. Esas rutas alimentarán _generar_variacion_personaje() en Fase 1.
    """
    # TODO (Fase 0): implementar generación de imagen base por personaje global
    logger.warning(
        "[Dibujante/Fase0] No implementado. "
        "Se usará generación estándar para todos los personajes."
    )
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# FASE 1 — Variación de personaje global vía PuLID  [PENDIENTE]
# ─────────────────────────────────────────────────────────────────────────────

def _generar_variacion_personaje(
    nodo: NodoEscena,
    imagen_base: Path,
    ruta_salida: Path,
) -> tuple[int, int]:
    """
    FASE 1 (personaje global) — Variación del personaje preservando identidad.
    Usa fal-ai/flux-pulid: imagen_base (quién es) + prompt (cómo está ahora).

    Implementación pendiente:
        import fal_client
        ref_url = fal_client.upload_file(str(imagen_base))
        result  = fal_client.subscribe(
            "fal-ai/flux-pulid",
            arguments={
                "prompt":              f"{nodo.prompt_imagen}. {_ESTILO_ELEMENTO}",
                "reference_image_url": ref_url,
                "num_steps":           20,
                "guidance_scale":      4.0,
                "num_images":          1,
            }
        )
        image_url = result["images"][0]["url"]
        ...eliminar fondo con rembg y guardar...
    """
    # TODO (Fase 1): implementar fal-ai/flux-pulid
    raise NotImplementedError(
        f"[Dibujante/Fase1] _generar_variacion_personaje no implementado "
        f"para '{nodo.id}'. Ver docstring para implementación PuLID."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Función principal
# ─────────────────────────────────────────────────────────────────────────────

def ejecutar_dibujante(
    scene_graph: SceneGraph,
    modo: Literal["mock", "fal", "gemini", "auto"] = "auto",
    directorio_salida: Optional[Path] = None,
    max_retries: Optional[int] = None,
    personajes_globales_ids: Optional[set[str]] = None,
    bases_personajes: Optional[dict[str, Path]] = None,
) -> SalidaDibujante:
    """
    Genera los assets visuales para todos los nodos del SceneGraph.

    Args:
        scene_graph:              Output del Constructor.
        modo:                     "mock" | "fal" | "gemini" | "auto"
        directorio_salida:        Carpeta de salida.
                                  Default: outputs/assets/<id_escena>/
        max_retries:              Reintentos ante fallo de API.
                                  Default: settings.max_retries.
        personajes_globales_ids:  IDs de personajes que aparecen en más de
                                  una escena (del SalidaOrganizador).
                                  Necesario para activar el flujo PuLID.
        bases_personajes:         {personaje_id: Path(imagen_base)}.
                                  Output de ejecutar_fase0_personajes_globales().
                                  Si está vacío, todos usan el flujo estándar.

    Returns:
        SalidaDibujante con la lista de AssetGenerado por nodo.
        Los PNGs se guardan en outputs/assets/<id_escena>/<id_nodo>.png,
        siguiendo la convención que usa el HTML preview del Constructor.
    """
    if max_retries is None:
        max_retries = settings.max_retries
    if personajes_globales_ids is None:
        personajes_globales_ids = set()
    if bases_personajes is None:
        bases_personajes = {}
    if directorio_salida is None:
        directorio_salida = _BASE_DIR / "outputs" / "assets" / scene_graph.id_escena

    # ── Resolver modo auto ──────────────────────────────────────────────────
    if modo == "auto":
        if _fal_disponible():
            modo_resuelto = "fal"
        elif _gemini_disponible():
            modo_resuelto = "gemini"
        else:
            modo_resuelto = "mock"
        logger.info(f"[Dibujante] Modo auto → '{modo_resuelto}'")
    else:
        modo_resuelto = modo

    generadores = {
        "mock":   _generar_mock,
        "fal":    _generar_fal,
        "gemini": _generar_gemini,
    }
    if modo_resuelto not in generadores:
        raise ValueError(f"[Dibujante] Modo desconocido: '{modo_resuelto}'")

    generar_estandar = generadores[modo_resuelto]
    assets: list[AssetGenerado] = []
    total = len(scene_graph.nodos)

    # En el paradigma 3D, el Dibujante solo procesa fondo y suelo.
    # Personajes, objetos y decorados son modelos 3D de poly.pizza — no necesitan PNG.
    nodos_a_procesar = [n for n in scene_graph.nodos if n.tipo in ("fondo", "suelo") and n.prompt_imagen is not None]
    nodos_omitidos   = [n for n in scene_graph.nodos if n.tipo not in ("fondo", "suelo")]

    if nodos_omitidos:
        logger.info(
            f"[Dibujante] Omitiendo {len(nodos_omitidos)} nodos 3D "
            f"({', '.join(n.tipo for n in nodos_omitidos[:3])}{'...' if len(nodos_omitidos) > 3 else ''}) "
            "— son modelos glTF de poly.pizza, no necesitan PNG."
        )

    total_procesar = len(nodos_a_procesar)
    if total_procesar == 0:
        logger.warning("[Dibujante] No hay nodos de tipo fondo o suelo que procesar.")
        return SalidaDibujante(id_escena=scene_graph.id_escena, assets=[])

    for i, nodo in enumerate(nodos_a_procesar, 1):
        ruta_salida = directorio_salida / f"{nodo.id}.png"
        logger.info(
            f"[Dibujante] [{i}/{total_procesar}] '{nodo.id}' ({nodo.tipo})"
        )

        # ── Bucle de reintentos ─────────────────────────────────────────────
        ultimo_error: Optional[str] = None
        exito = False

        for intento in range(1, max_retries + 1):
            if intento > 1:
                logger.warning(
                    f"[Dibujante] '{nodo.id}' — reintento {intento}/{max_retries} "
                    f"(error anterior: {ultimo_error})"
                )
            try:
                ancho_px, alto_px = generar_estandar(nodo, ruta_salida)
                assets.append(AssetGenerado(
                    id_elemento=nodo.id,
                    ruta_png=str(ruta_salida),
                    ancho_px=ancho_px,
                    alto_px=alto_px,
                    prompt_usado=nodo.prompt_imagen or "",
                    intentos=intento,
                ))
                logger.info(
                    f"[Dibujante] ✓ '{nodo.id}' — {ancho_px}×{alto_px}px "
                    f"(intento {intento})"
                )
                exito = True
                break

            except Exception as exc:
                error_str = str(exc)
                if any(k in error_str for k in [
                    "FAL_KEY", "API key", "Unauthorized", "401", "403",
                    "NotImplementedError",
                ]):
                    raise RuntimeError(
                        f"[Dibujante] Error irrecuperable en '{nodo.id}': {error_str}"
                    ) from exc
                ultimo_error = error_str
                logger.warning(
                    f"[Dibujante] Intento {intento} fallido para '{nodo.id}': "
                    f"{error_str[:120]}"
                )

        if not exito:
            raise ValueError(
                f"[Dibujante] No se pudo generar '{nodo.id}' "
                f"tras {max_retries} intentos. Último error: {ultimo_error}"
            )

    logger.info(
        f"[Dibujante] ✓ Escena '{scene_graph.id_escena}': "
        f"{len(assets)} texturas 2D (fondo+suelo) → {directorio_salida}"
    )
    return SalidaDibujante(id_escena=scene_graph.id_escena, assets=assets)