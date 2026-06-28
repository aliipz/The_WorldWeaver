/**
 * WorldWeaver — personajes.js
 *
 * Gestiona la apariencia visual y las animaciones de los personajes del
 * catálogo Quaternius cargados desde /sandbox/assets/characters/.
 *
 * API pública (window.PersonajesManager):
 *   registrar(nodoId, model, gltf, skin)  — humanos Quaternius con esqueleto (AnimationMixer)
 *   registrarProcedural(nodoId, grupo, altura) — no-humanos sin esqueleto (animación por transform)
 *   hablar(nodoId)                        — Idle → Talk  (llamado por interactions al abrir diálogo)
 *   callar(nodoId)                        — Talk → Idle  (llamado por interactions al cerrar diálogo)
 *   playOnce(nodoId, clip)                — reacción puntual (skeletal o gesto procedural)
 *   update(delta)                         — avanza mixers + animaciones procedurales (loop de render)
 *
 * Dos clases de personaje conviven:
 *   · Humanos (catálogo Quaternius): GLB con clips, animados con THREE.AnimationMixer.
 *   · No-humanos (animales/criaturas de poly.pizza, modelo rígido): animados de forma
 *     procedural moviendo el objeto entero (respiración idle + bob/tilt al hablar +
 *     gestos one-shot 'alegria'/'susto'). hablar/callar/playOnce despachan a uno u otro.
 */

window.PersonajesManager = (function () {

    // ── Paleta de colores de pelo (rangos HSL) ────────────────────────────────
    const HAIR_PRESETS = {
        negro:          { hue: 0.05, sat: [0.05, 0.15], light: [0.04, 0.11] },
        castano_oscuro: { hue: 0.07, sat: [0.45, 0.65], light: [0.13, 0.25] },
        castano_claro:  { hue: 0.08, sat: [0.40, 0.60], light: [0.28, 0.42] },
        rubio:          { hue: 0.12, sat: [0.55, 0.85], light: [0.58, 0.78] },
        pelirrojo:      { hue: 0.04, sat: [0.75, 0.95], light: [0.35, 0.50] },
        gris:           { hue: 0.60, sat: [0.00, 0.08], light: [0.45, 0.65] },
        blanco:         { hue: 0.10, sat: [0.00, 0.05], light: [0.82, 0.95] },
        rojo:           { hue: 0.00, sat: [0.80, 1.00], light: [0.35, 0.52] },
        azul:           { hue: 0.62, sat: [0.75, 1.00], light: [0.35, 0.58] },
        verde:          { hue: 0.35, sat: [0.60, 0.90], light: [0.28, 0.50] },
    };

    // Materiales excluidos de la variación de ropa
    const MATS_EXCLUIDOS = new Set(['Skin', 'Face', 'Hair']);

    // ── Utilidades de color ───────────────────────────────────────────────────

    function _seededRng(seed) {
        let s = seed >>> 0;
        return function () {
            s = (s + 0x6D2B79F5) | 0;
            let t = Math.imul(s ^ (s >>> 15), 1 | s);
            t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
            return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
        };
    }

    function _hashStr(str) {
        let h = 0x811c9dc5;
        for (let i = 0; i < str.length; i++) {
            h ^= str.charCodeAt(i);
            h = (Math.imul(h, 0x01000193)) >>> 0;
        }
        return h;
    }

    function _hexToColor(hex) {
        if (!hex || hex.length < 7) return new THREE.Color(0xD4956A);
        const r = parseInt(hex.slice(1, 3), 16) / 255;
        const g = parseInt(hex.slice(3, 5), 16) / 255;
        const b = parseInt(hex.slice(5, 7), 16) / 255;
        return new THREE.Color(r, g, b);
    }

    function _colorPelo(hairId, seed) {
        const preset = HAIR_PRESETS[hairId];
        if (!preset) return null;
        const rng = _seededRng(seed + 999);
        const jitter = (rng() - 0.5) * 0.025;
        const sat    = preset.sat[0]   + rng() * (preset.sat[1]   - preset.sat[0]);
        const light  = preset.light[0] + rng() * (preset.light[1] - preset.light[0]);
        return new THREE.Color().setHSL((preset.hue + jitter + 1) % 1, sat, light);
    }

    // ── Aplicar apariencia al modelo ──────────────────────────────────────────

    function _aplicarApariencia(model, skin) {
        if (!skin) {
            // Sin skin definida: al menos convertir linear→sRGB
            model.traverse(function (node) {
                if (!node.isMesh) return;
                const mats = Array.isArray(node.material) ? node.material : [node.material];
                mats.forEach(function (mat) {
                    if (mat && mat.color) { mat.color.convertLinearToSRGB(); mat.needsUpdate = true; }
                });
            });
            return;
        }

        const skinColor   = skin.skin_hex  ? _hexToColor(skin.skin_hex)  : null;
        const hairSeed    = ((skin.clothing_seed || 1) * 13 + 1) >>> 0;
        const hairColor   = skin.hair_color ? _colorPelo(skin.hair_color, hairSeed) : null;
        const variantSeed = skin.clothing_seed || 0;
        const processed   = new Set();

        model.traverse(function (node) {
            if (!node.isMesh) return;
            const mats = Array.isArray(node.material) ? node.material : [node.material];
            mats.forEach(function (mat) {
                if (!mat || !mat.color || processed.has(mat.uuid)) return;
                processed.add(mat.uuid);

                // Los GLTFs de Quaternius almacenan colores en espacio lineal;
                // convertimos a sRGB para que se vean correctamente sin outputEncoding.
                mat.color.convertLinearToSRGB();

                if (mat.name === 'Skin' && skinColor) {
                    mat.color.set(skinColor);

                } else if (mat.name === 'Hair' && hairColor) {
                    mat.color.set(hairColor);

                } else if (!MATS_EXCLUIDOS.has(mat.name) && variantSeed > 0) {
                    // Variación determinista de ropa: hue/sat/brillo según seed + nombre del material
                    const matSeed = (variantSeed * 7919 + _hashStr(mat.name)) >>> 0;
                    const rng     = _seededRng(matSeed);
                    const hsl     = { h: 0, s: 0, l: 0 };
                    mat.color.getHSL(hsl);
                    const hueShift  = (rng() - 0.5) * 0.45;
                    const satMult   = 0.50 + rng() * 1.10;
                    const lightMult = 0.70 + rng() * 0.60;
                    mat.color.setHSL(
                        (hsl.h + hueShift + 1) % 1,
                        Math.min(1,    hsl.s * satMult),
                        Math.min(0.92, Math.max(0.04, hsl.l * lightMult))
                    );
                }
                mat.needsUpdate = true;
            });
        });
    }

    // ── Registro de mixers ────────────────────────────────────────────────────
    // nodo_id → { mixer, actions, currentClip, idleClip, talkClip }
    const _mixers = {};

    // ── Registro procedural (no-humanos sin esqueleto) ────────────────────────
    // nodo_id → { grupo, baseY, baseRotX, baseRotZ, altura, hablando, gesto, gestoT0, fase }
    const _procedurales = {};
    let _t = 0;  // reloj acumulado (segundos) para las oscilaciones procedurales

    // Parámetros (amplitudes relativas a la altura del modelo → escala-independientes)
    const _IDLE_AMP = 0.015, _IDLE_FREQ = 1.1;   // respiración constante
    const _TALK_AMP = 0.045, _TALK_FREQ = 7.5;   // bob al hablar
    const _TALK_TILT = 0.07;                      // inclinación (rad) al hablar
    const _HOP_DUR = 1100, _HOP_AMP = 0.28;       // saltitos de alegría (ms, fracción de altura)
    const _TREMOR_DUR = 600;                      // susto/temblor (ms)

    // Mapa tolerante nombre → gesto procedural. Acepta también los nombres del
    // catálogo Quaternius como red de seguridad por si el Programador asigna uno
    // a un no-humano: así el gesto sigue teniendo sentido en vez de perderse.
    function _gestoDe(nombre) {
        if (nombre === 'alegria' || nombre === 'Victory' || nombre === 'Jump') return 'hops';
        if (nombre === 'susto' || nombre === 'RecieveHit' ||
            nombre === 'Defeat' || nombre === 'Death' || nombre === 'Punch') return 'tremor';
        return null;
    }

    function _iniciarGesto(p, nombre) {
        const g = _gestoDe(nombre);
        if (!g) return;  // desconocido → no-op (sin romper nada)
        p.gesto   = g;
        p.gestoT0 = performance.now();
    }

    // ── API pública ───────────────────────────────────────────────────────────

    function registrar(nodoId, model, gltf, skin) {
        _aplicarApariencia(model, skin);

        const clips = gltf.animations || [];
        if (!clips.length) return;

        const mixer  = new THREE.AnimationMixer(model);
        const actions = {};
        clips.forEach(function (clip) {
            actions[clip.name] = mixer.clipAction(clip);
        });

        const idleClip = (skin && skin.animacion_idle) || 'Idle';
        const talkClip = (skin && skin.animacion_talk) || 'Victory';

        // Elegir animación de talk con fallback a Idle si el clip no existe
        const resolvedTalk = actions[talkClip] ? talkClip : idleClip;

        // Arrancar idle
        if (actions[idleClip]) actions[idleClip].reset().play();

        _mixers[nodoId] = { mixer, actions, currentClip: idleClip, idleClip, talkClip: resolvedTalk };
        console.log(
            `[Personajes] '${nodoId}' registrado — ` +
            `skin=${skin ? skin.skin_hex : 'N/A'} ` +
            `hair=${skin ? skin.hair_color : 'N/A'} ` +
            `seed=${skin ? skin.clothing_seed : 0} ` +
            `idle=${idleClip} talk=${resolvedTalk}`
        );
    }

    // Registra un personaje no-humano (modelo rígido) para animación procedural.
    // grupo = THREE.Object3D cuyo transform animamos; altura = alto real ya escalado.
    function registrarProcedural(nodoId, grupo, altura) {
        if (!grupo) return;
        _procedurales[nodoId] = {
            grupo,
            baseY:    grupo.position.y,
            baseRotX: grupo.rotation.x,
            baseRotZ: grupo.rotation.z,
            altura:   Math.max(altura || 1.0, 0.05),
            hablando: false,
            gesto:    null,
            gestoT0:  0,
            fase:     Math.random() * Math.PI * 2,  // desfase para que no respiren al unísono
        };
        console.log(`[Personajes] '${nodoId}' registrado (procedural, altura=${(altura||0).toFixed(2)})`);
    }

    function hablar(nodoId) {
        const entry = _mixers[nodoId];
        if (entry) { _cambiar(entry, entry.talkClip, 0.25); return; }
        const p = _procedurales[nodoId];
        if (p) p.hablando = true;
    }

    function callar(nodoId) {
        const entry = _mixers[nodoId];
        if (entry) { _cambiar(entry, entry.idleClip, 0.35); return; }
        const p = _procedurales[nodoId];
        if (p) p.hablando = false;
    }

    // Reproduce un clip una sola vez y vuelve a Idle al terminar.
    // Usado para reacciones narrativas: Defeat, Victory, Death, RecieveHit...
    function playOnce(nodoId, clipName) {
        const entry = _mixers[nodoId];
        if (!entry) {
            const p = _procedurales[nodoId];
            if (p) _iniciarGesto(p, clipName);
            return;
        }
        const action = entry.actions[clipName];
        if (!action) {
            console.warn(`[Personajes] '${nodoId}': clip '${clipName}' no existe — ignorando.`);
            return;
        }
        action.reset();
        action.setLoop(THREE.LoopOnce, 1);
        action.clampWhenFinished = true;

        const from = entry.actions[entry.currentClip];
        if (from) from.crossFadeTo(action, 0.2, false);
        action.play();
        entry.currentClip = clipName;

        // Volver a Idle al terminar
        const onFinished = (e) => {
            if (e.action !== action) return;
            entry.mixer.removeEventListener('finished', onFinished);
            action.setLoop(THREE.LoopRepeat, Infinity);
            _cambiar(entry, entry.idleClip, 0.4);
        };
        entry.mixer.addEventListener('finished', onFinished);
    }

    function _cambiar(entry, clipName, duracion) {
        if (entry.currentClip === clipName) return;
        const from = entry.actions[entry.currentClip];
        const to   = entry.actions[clipName];
        if (!to) return;
        to.reset();
        if (from) from.crossFadeTo(to, duracion, false);
        to.play();
        entry.currentClip = clipName;
    }

    function update(delta) {
        for (const id in _mixers) {
            _mixers[id].mixer.update(delta);
        }

        // Animación procedural de no-humanos: recomponer el transform SIEMPRE desde
        // la base capturada al registrar (evita deriva acumulada entre frames/gestos).
        _t += delta;
        const ahora = performance.now();
        for (const id in _procedurales) {
            const p = _procedurales[id];
            const h = p.altura;

            // Respiración idle (siempre activa, ínfima)
            let yOff   = _IDLE_AMP * h * Math.sin(_t * _IDLE_FREQ + p.fase);
            let rotX   = 0;
            let rotZ   = 0;

            // Hablar: bob vertical + cabeceo mientras el diálogo está abierto.
            // El pivote del grupo está en el suelo, así que un tilt simétrico hundiría
            // la cabeza en el suelo en la fase hacia abajo. Usamos una envolvente
            // (1−cos)/2 ∈ [0,1]: el modelo solo se inclina HACIA ARRIBA y vuelve al reposo,
            // como un gesto de hablar natural.
            if (p.hablando) {
                // Bob desplazado a [0, 2·AMP]: misma amplitud de movimiento, pero el punto
                // más bajo queda a ras de suelo (no por debajo). Ese pequeño alzado de base
                // compensa también el borde que el cabeceo hundía → ya no se mete en el suelo.
                yOff += _TALK_AMP * h * (1 + Math.sin(_t * _TALK_FREQ));
                rotX += _TALK_TILT * 0.5 * (1 - Math.cos(_t * _TALK_FREQ));
            }

            // Gesto one-shot activo (alegría / susto), con envolvente que vuelve a 0
            if (p.gesto) {
                const elapsed = ahora - p.gestoT0;
                if (p.gesto === 'hops' && elapsed < _HOP_DUR) {
                    yOff += _HOP_AMP * h * Math.abs(Math.sin(elapsed * 0.012)) * (1 - elapsed / _HOP_DUR);
                } else if (p.gesto === 'tremor' && elapsed < _TREMOR_DUR) {
                    // Sobresalto contenido: amplitud y frecuencia suaves (antes parecía un
                    // temblor febril). Sigue siendo un respingo perceptible, no una convulsión.
                    const amp = 0.03 * (1 - elapsed / _TREMOR_DUR);
                    rotZ += amp       * Math.sin(elapsed * 0.045);
                    rotX += amp * 0.4 * Math.sin(elapsed * 0.035);
                } else {
                    p.gesto = null;  // terminado → vuelve a base
                }
            }

            p.grupo.position.y = p.baseY    + yOff;
            p.grupo.rotation.x = p.baseRotX + rotX;
            p.grupo.rotation.z = p.baseRotZ + rotZ;
        }
    }

    return { registrar, registrarProcedural, hablar, callar, playOnce, update };

})();
