# -*- mode: python ; coding: utf-8 -*-
"""
Spec de PyInstaller para WorldWeaver — app de escritorio.

Construye:  pyinstaller worldweaver.spec --noconfirm
Salida:     dist/WorldWeaver/  (carpeta con WorldWeaver.exe + _internal)

Punto de entrada: launch.py (arranca uvicorn + abre el navegador a pantalla completa).
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = []

# ── Ecosistema langchain/langgraph + servidor: importan submódulos dinámicamente,
#    así que los recogemos enteros para evitar fallos de import en runtime. ──────
# Solo los paquetes que el código realmente importa. Se evita langchain_community
# (cajón de sastre que arrastra torch/pygame y otras integraciones que no usamos).
for _pkg in [
    "langchain_core", "langchain_openai", "langchain_ollama",
    "langgraph", "langgraph_checkpoint", "langgraph_prebuilt", "langsmith",
    "uvicorn", "fastapi", "starlette",
    "pydantic", "pydantic_settings", "pydantic_core",
    "rich", "tiktoken",
]:
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception:
        pass

# Imports que PyInstaller no detecta por estar tras Form/File, dotenv, etc.
hiddenimports += [
    "multipart", "python_multipart",
    "dotenv",
    "pypdf",
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
]

# ── Datos de la app (solo lectura, viajan dentro del bundle) ──────────────────
#    NB: assets/references (42 MB) NO se incluye — solo lo usaba el Dibujante.
#    NB: los mundos NO se hornean en el .exe — viven como carpeta outputs/ junto
#        al ejecutable (editable a mano: lo que haya ahí es lo que ve el usuario).
datas += [
    ("sandbox", "sandbox"),
    ("assets/music", "assets/music"),
    ("landing.html", "."),
    (".env", "."),
    ("runtime_paths.py", "."),
]

# ── Librerías pesadas del agente de imágenes (eliminado) — fuera del bundle ────
excludes = [
    "rembg", "onnxruntime", "fal_client", "PIL", "Pillow",
    "google.generativeai", "google.genai", "google_genai",
    "torch", "torchaudio", "torchvision", "tensorflow", "cv2", "pygame",
    "transformers", "sentence_transformers", "datasets",
    "langchain_community", "langchain_text_splitters",
    "matplotlib", "scipy", "pandas", "sklearn", "scikit-learn",
    "IPython", "notebook", "jupyter", "pytest", "agents.dibujante",
]


a = Analysis(
    ["launch.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WorldWeaver",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # ventana de consola = control para cerrar + log de generación
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="WorldWeaver",
)
