# WorldWeaver

**Un sistema multiagente para la generación automática de mundos virtuales 3D interactivos a partir de texto.**

WorldWeaver transforma un relato en lenguaje natural en un entorno tridimensional navegable y reactivo, ejecutable directamente en el navegador. A partir de un texto, un *pipeline* de agentes basados en modelos de lenguaje (orquestado con LangGraph) segmenta la narrativa en escenas, las puebla con modelos 3D, les da lógica de interacción y ambientación sonora, y lo compila todo en un documento HTML autocontenido.

Este repositorio acompaña al Trabajo Fin de Máster homónimo (Máster Universitario en Inteligencia Artificial Aplicada, Universidad Carlos III de Madrid, 2025-2026).

## Características

- **Pipeline multiagente** de seis agentes: Organizador → Director → Constructor → Programador → Músico → Ensamblador (más un **Examinador** en modo educativo), con validación semántica y reparación determinista entre etapas.
- **Dos modos de operación**: *narrativo* (exploración e inmersión) y *educativo* (contenido didáctico + cuestionario final de evaluación).
- **Bilingüe**: generación de mundos en español o inglés.
- **Visor 3D autocontenido**: cada mundo es un único archivo HTML que se abre en cualquier navegador moderno (Three.js / WebGL), sin instalación.

## Requisitos

- Python 3.11 o superior.
- Tres claves de API para generar mundos nuevos: un proveedor LLM, [Poly Pizza](https://poly.pizza/) (modelos 3D) y [Freesound](https://freesound.org/) (audio). Poly Pizza y Freesound son gratuitas; el LLM puede sustituirse por un modelo local gratuito ([Ollama](https://ollama.com/)). **Para solo explorar los mundos de ejemplo ya incluidos no hace falta ninguna clave.**

## Puesta en marcha

**1. Clona el repositorio e instala las dependencias:**

```bash
git clone https://github.com/aliipz/The_WorldWeaver.git
cd WorldWeaver
pip install -r worldweaver/requirements.txt
```

**2. Configura las claves de API.** Copia la plantilla y rellena tus claves:

```bash
cp worldweaver/.env.example worldweaver/.env
# edita worldweaver/.env
```

| Variable (`worldweaver/.env`) | Servicio | Cómo obtenerla |
|---|---|---|
| `MERCURY_API_KEY` | Proveedor LLM — [Mercury 2 (Inception Labs)](https://www.inceptionlabs.ai/) | Crea una cuenta en la plataforma y genera una clave de API. *(Alternativa sin clave: ejecuta un modelo local con [Ollama](https://ollama.com/) y rellena `OLLAMA_*` en su lugar.)* |
| `POLYPIZZA_API_KEY` | [Poly Pizza](https://poly.pizza/) — modelos 3D | Regístrate gratis y copia tu clave desde los ajustes de la cuenta (apartado API). |
| `FREESOUND_API_KEY` | [Freesound](https://freesound.org/) — audio ambiental | Regístrate gratis y solicita una credencial en [freesound.org/apiv2/apply](https://freesound.org/apiv2/apply/). |

> Sin claves el sistema sigue arrancando: podrás navegar los mundos de ejemplo, pero no generar nuevos (las llamadas a los servicios externos fallarán). El audio de respaldo y los personajes vienen incluidos, así que un mundo generado siempre tiene sonido y figuras aunque Freesound o Poly Pizza no respondan.

## Ejecución

El sistema admite tres formas de uso sobre el mismo núcleo:

**1. Servidor web (recomendado).** Arranca la interfaz local:

```bash
cd worldweaver
uvicorn server:app --port 8000
# abre http://localhost:8000
```

**2. Por consola** (generación desatendida):

```bash
python worldweaver/tests/test_total.py texto.txt mi_mundo
```

**3. Aplicación de escritorio.** `python launch.py` arranca el servidor y abre el navegador en modo app. Para distribuir como ejecutable autónomo:

```bash
cd worldweaver
python -m PyInstaller worldweaver.spec --noconfirm
```

Los mundos generados se escriben en `worldweaver/outputs/<nombre>/` como HTML autocontenido.

## Estructura del proyecto

```
worldweaver/
  agents/      Los seis agentes especializados del pipeline
  config/      Configuración, prompts (ES/EN) y geometría del escenario
  schemas/     Esquemas Pydantic (contrato entre agentes)
  pipeline/    Grafo LangGraph, estado compartido, validadores, ensamblador
  sandbox/     Plantilla del visor 3D (Three.js) + assets (Quaternius, música)
  server.py    Servidor FastAPI + landing
  fixtures/    Textos de entrada de ejemplo
  outputs/     Mundos de ejemplo generados (de la evaluación)
metricas/      Datos brutos de la evaluación técnica
```

## Mundos de ejemplo y evaluación

La carpeta `worldweaver/outputs/` incluye los mundos utilizados en la evaluación del TFM (sus textos fuente están en `worldweaver/fixtures/`). Los datos brutos de la evaluación técnica se encuentran en `metricas/`.

## Licencia

El **código** se publica bajo licencia **MIT** (ver [`LICENSE`](LICENSE)).

Los **recursos de terceros** conservan sus propias licencias: los personajes Quaternius y los paisajes sonoros de respaldo son CC0; los modelos de Poly Pizza y el audio de Freesound recuperados en tiempo de ejecución se rigen por la licencia de cada recurso.

## Autoría

Alicia Pina Zapata — Trabajo Fin de Máster, Universidad Carlos III de Madrid (2025-2026). Tutor: Andrea Bellucci.
