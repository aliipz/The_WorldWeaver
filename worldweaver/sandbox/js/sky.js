/**
 * WorldWeaver — sky.js
 * Cielo dinámico: sol/luna, nubes orbitantes, estrellas, lluvia.
 *
 * API:
 *   const ctrl = iniciarCielo(cieloConfig, scene);
 *   // En el animate loop:
 *   ctrl.update(t);   // t = performance.now() * 0.001
 */

// Crea una esfera grande (BackSide) con degradado vertical de colores
function _domeDegradado(scene, capas) {
    // capas: array de { y: float (-1..1 normalizado), color: THREE.Color }
    //        ordenado de menor a mayor y
    const geo = new THREE.SphereGeometry(45, 24, 16);
    const pos = geo.attributes.position;
    const colArr = new Float32Array(pos.count * 3);
    const yMin = -45, yMax = 45;

    for (let i = 0; i < pos.count; i++) {
        const t = Math.max(0, Math.min(1, (pos.getY(i) - yMin) / (yMax - yMin)));
        // Encuentra el segmento correcto
        let c = new THREE.Color();
        for (let s = 0; s < capas.length - 1; s++) {
            if (t >= capas[s].t && t <= capas[s + 1].t) {
                const local = (t - capas[s].t) / (capas[s + 1].t - capas[s].t);
                c.lerpColors(capas[s].color, capas[s + 1].color, local);
                break;
            }
        }
        colArr[i * 3]     = c.r;
        colArr[i * 3 + 1] = c.g;
        colArr[i * 3 + 2] = c.b;
    }
    geo.setAttribute('color', new THREE.BufferAttribute(colArr, 3));
    scene.add(new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.BackSide })));
}

window.iniciarCielo = function (cielo, scene) {
    if (!cielo) return { update: () => {} };

    const tipo    = cielo.tipo;
    const animados = [];
    const rng = (a, b) => a + Math.random() * (b - a);

    // ── Degradado de fondo (atardecer / amanecer) ─────────────────────────────
    if (tipo === 'atardecer') {
        scene.background = null;
        _domeDegradado(scene, [
            { t: 0.0,  color: new THREE.Color('#100414') },  // nadir: casi negro violáceo
            { t: 0.38, color: new THREE.Color('#4a0c18') },  // bajo: rojo oscuro
            { t: 0.48, color: new THREE.Color('#c03010') },  // horizonte alto: naranja-rojo
            { t: 0.56, color: new THREE.Color('#e86820') },  // horizonte bajo: dorado-naranja
            { t: 0.62, color: new THREE.Color('#ff9030') },  // punta horizonte: más cálido
            { t: 0.72, color: new THREE.Color('#c02818') },  // sube: vuelve a rojo
            { t: 0.85, color: new THREE.Color('#4a0a28') },  // alto: violeta oscuro
            { t: 1.0,  color: new THREE.Color('#0c0418') },  // cénit: casi negro
        ]);
    }

    if (tipo === 'amanecer') {
        scene.background = null;
        _domeDegradado(scene, [
            { t: 0.0,  color: new THREE.Color('#080810') },  // nadir
            { t: 0.40, color: new THREE.Color('#1c1040') },  // bajo: azul oscuro
            { t: 0.50, color: new THREE.Color('#c04828') },  // horizonte: rosa-naranja
            { t: 0.58, color: new THREE.Color('#ff9060') },  // pico cálido
            { t: 0.66, color: new THREE.Color('#8030a0') },  // sube: violeta
            { t: 0.80, color: new THREE.Color('#181438') },  // alto: azul-índigo
            { t: 1.0,  color: new THREE.Color('#080810') },  // cénit
        ]);
    }

    // ── Sol ───────────────────────────────────────────────────────────────────
    const TIPOS_CON_SOL = ['amanecer', 'manana_despejada', 'manana_nublada', 'mediodia_soleado', 'atardecer'];
    if (TIPOS_CON_SOL.includes(tipo)) {
        const colorSol = {
            amanecer:          0xff9900,   // dorado-naranja
            manana_despejada:  0xffdd00,   // amarillo brillante
            manana_nublada:    0xffe080,   // amarillo pálido
            mediodia_soleado:  0xffee00,   // amarillo intenso
            atardecer:         0xff4010,   // naranja-rojo
        }[tipo] ?? 0xffdd00;
        // Sol en el borde del cilindro (R=22): para amanecer/atardecer en el horizonte,
        // para el resto en lo alto. Tamaño escalado para mantener aspecto visual correcto.
        const R = 24;  // borde del cilindro exterior
        const radioSol = {
            amanecer:         1.1,
            atardecer:        1.3,
            mediodia_soleado: 0.55,
            manana_despejada: 0.65,
            manana_nublada:   0.70,
        }[tipo] ?? 0.65;

        const p   = cielo.pos_sol;
        const len = Math.sqrt(p.x * p.x + p.y * p.y + p.z * p.z) || 1;
        const nx = p.x / len, ny = p.y / len, nz = p.z / len;

        const esHorizonte = ['amanecer', 'atardecer'].includes(tipo);
        const pos = {
            x: nx * R,
            // Horizonte: justo a la altura de los ojos (y≈2). Alto: sube según elevación.
            y: esHorizonte ? 2.0 + ny * 2.0 : ny * 14 + 4.0,
            z: nz * R,
        };

        const sol = new THREE.Mesh(
            new THREE.SphereGeometry(radioSol, 20, 20),
            new THREE.MeshBasicMaterial({ color: colorSol, fog: false })
        );
        sol.position.set(pos.x, pos.y, pos.z);
        scene.add(sol);

        // Halo difuso
        const haloMat = new THREE.MeshBasicMaterial({ color: colorSol, transparent: true, opacity: 0.12, fog: false });
        const halo = new THREE.Mesh(new THREE.SphereGeometry(radioSol * 2.8, 20, 20), haloMat);
        halo.position.copy(sol.position);
        scene.add(halo);

        animados.push({ update: t => {
            haloMat.opacity = 0.08 + 0.06 * Math.sin(t * 0.35);
        }});
    }

    // ── Luna + estrellas (solo noche despejada — noche_cerrada tiene nubes) ──
    if (tipo === 'noche_estrellada') {
        // Luna — en el borde del cilindro, alta pero visible
        const luna = new THREE.Mesh(
            new THREE.SphereGeometry(1.4, 20, 20),
            new THREE.MeshBasicMaterial({ color: 0xffffff, fog: false })
        );
        luna.position.set(-14, 14, -16);
        scene.add(luna);

        const haloLunaMat = new THREE.MeshBasicMaterial({ color: 0xddeeff, transparent: true, opacity: 0.09, fog: false });
        const haloLuna = new THREE.Mesh(new THREE.SphereGeometry(2.6, 20, 20), haloLunaMat);
        haloLuna.position.copy(luna.position);
        scene.add(haloLuna);
        animados.push({ update: t => { haloLunaMat.opacity = 0.06 + 0.04 * Math.sin(t * 0.28); } });

        // Estrellas en grupos independientes — cada grupo parpadea a su propio ritmo
        const totalEstrellas = 420;
        const numGrupos      = 9;
        const porGrupo       = Math.ceil(totalEstrellas / numGrupos);

        for (let g = 0; g < numGrupos; g++) {
            const N   = g < numGrupos - 1 ? porGrupo : totalEstrellas - porGrupo * (numGrupos - 1);
            const pos = new Float32Array(N * 3);
            const esPrincipal = g < numGrupos * 0.7;  // 70% estrellas blancas, 30% azuladas
            const phiMax = esPrincipal ? 0.52 : 0.42;
            // Radio al borde del cilindro exterior (~22-24 u). sizeAttenuation escala el
            // tamaño con la distancia, así que size también sube proporcionalmente (~4×).
            const radio  = esPrincipal ? 22 + Math.random() * 1.5 : 23 + Math.random() * 1.0;

            for (let i = 0; i < N; i++) {
                const theta = Math.random() * Math.PI * 2;
                const phi   = Math.random() * Math.PI * phiMax;
                pos[i * 3]     = radio * Math.sin(phi) * Math.cos(theta);
                pos[i * 3 + 1] = radio * Math.cos(phi) + 2.5;
                pos[i * 3 + 2] = radio * Math.sin(phi) * Math.sin(theta);
            }
            const geo = new THREE.BufferGeometry();
            geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
            const mat = new THREE.PointsMaterial({
                color: esPrincipal ? 0xffffff : 0xc8dcff,
                size:  esPrincipal ? 0.24 : 0.14,
                sizeAttenuation: true,
                transparent: true,
                opacity: 0.9,
                fog: false,
            });
            scene.add(new THREE.Points(geo, mat));

            // Ritmo propio: fase y velocidad distintas por grupo
            // ampMin bajo para que lleguen casi a apagarse en el valle del seno
            const fase   = g * (Math.PI * 2 / numGrupos) + Math.random() * 1.2;
            const vel    = 0.45 + Math.random() * 0.55;
            const ampMin = 0.05 + Math.random() * 0.15;   // 0.05–0.20 (antes 0.45–0.65)
            animados.push({ update: t => {
                mat.opacity = ampMin + (1 - ampMin) * Math.abs(Math.sin(t * vel + fase));
            }});
        }
    }

    // ── Cielo mágico: domo degradado + aurora ────────────────────────────────
    if (tipo === 'cielo_magico') {
        scene.background = null;
        _domeDegradado(scene, [
            { t: 0.0,  color: new THREE.Color('#04010c') },
            { t: 0.35, color: new THREE.Color('#1a0440') },
            { t: 0.50, color: new THREE.Color('#3a0870') },
            { t: 0.62, color: new THREE.Color('#20a080') },  // aurora teal
            { t: 0.72, color: new THREE.Color('#8010c0') },  // violeta intenso
            { t: 0.85, color: new THREE.Color('#200850') },
            { t: 1.0,  color: new THREE.Color('#04010c') },
        ]);

        // Franjas de aurora animadas
        const auroraColors = [0x20e0a0, 0x8020e0, 0x40a0ff, 0xe040a0];
        const franjas = [];
        for (let i = 0; i < 4; i++) {
            const mat = new THREE.MeshBasicMaterial({
                color: auroraColors[i], transparent: true, opacity: 0,
                side: THREE.DoubleSide, depthWrite: false,
            });
            const franja = new THREE.Mesh(new THREE.PlaneGeometry(12, 0.6 + rng(0, 0.4)), mat);
            franja.rotation.x = Math.PI / 2 - 0.3 + rng(-0.1, 0.1);
            franja.position.set(rng(-2, 2), 5.0 + i * 0.5, rng(-3, -1));
            scene.add(franja);
            franjas.push({ mat, fase: i * 1.3 + rng(0, 1), vel: 0.3 + rng(0, 0.25) });
        }
        // Estrellas visibles en cielo mágico
        const N = 200, posE = new Float32Array(N * 3);
        for (let i = 0; i < N; i++) {
            const theta = Math.random() * Math.PI * 2, phi = Math.random() * Math.PI * 0.5;
            const r = 5.2 + Math.random() * 0.4;
            posE[i*3] = r*Math.sin(phi)*Math.cos(theta); posE[i*3+1] = r*Math.cos(phi)+2.5; posE[i*3+2] = r*Math.sin(phi)*Math.sin(theta);
        }
        const geoE = new THREE.BufferGeometry(); geoE.setAttribute('position', new THREE.BufferAttribute(posE, 3));
        const matE = new THREE.PointsMaterial({ color: 0xeeccff, size: 0.05, transparent: true, opacity: 0.8 });
        scene.add(new THREE.Points(geoE, matE));
        animados.push({ update: t => {
            for (const f of franjas) f.mat.opacity = 0.08 + 0.12 * Math.abs(Math.sin(t * f.vel + f.fase));
            matE.opacity = 0.6 + 0.4 * Math.sin(t * 0.5);
        }});
    }

    // ── Niebla densa: partículas de niebla flotante ───────────────────────────
    if (tipo === 'niebla_densa') {
        const N = 400, pos = new Float32Array(N * 3);
        for (let i = 0; i < N; i++) {
            pos[i*3] = rng(-6, 6); pos[i*3+1] = rng(0, 5); pos[i*3+2] = rng(-6, 6);
        }
        const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
        const mat = new THREE.PointsMaterial({ color: 0xdde0e4, size: 0.15, transparent: true, opacity: 0.18, sizeAttenuation: true });
        const puntos = new THREE.Points(geo, mat);
        scene.add(puntos);
        animados.push({ update: t => {
            const a = puntos.geometry.attributes.position;
            for (let i = 0; i < N; i++) {
                a.setX(i, a.getX(i) + Math.sin(t * 0.2 + i) * 0.002);
                a.setY(i, a.getY(i) + Math.sin(t * 0.15 + i * 0.7) * 0.001);
            }
            a.needsUpdate = true;
            mat.opacity = 0.14 + 0.06 * Math.sin(t * 0.3);
        }});
    }

    // ── Nubes ─────────────────────────────────────────────────────────────────
    const TIPOS_CON_NUBES = ['amanecer', 'manana_despejada', 'manana_nublada', 'mediodia_soleado', 'atardecer', 'noche_cerrada', 'tormenta', 'lluvia_suave', 'dia_nevado', 'niebla_densa'];
    if (TIPOS_CON_NUBES.includes(tipo)) {
        const cfg = {
            amanecer:          { n: 5,  color: 0xff9966, op: 0.68 },
            manana_despejada:  { n: 4,  color: 0xffffff, op: 0.68 },
            manana_nublada:    { n: 10, color: 0xd8dde2, op: 0.90 },
            mediodia_soleado:  { n: 2,  color: 0xffffff, op: 0.60 },
            atardecer:         { n: 6,  color: 0xff8855, op: 0.72 },
            noche_cerrada:     { n: 5,  color: 0x101018, op: 0.80 },
            tormenta:          { n: 13, color: 0x404850, op: 0.92 },
            lluvia_suave:      { n: 9,  color: 0x6878a0, op: 0.82 },
            dia_nevado:        { n: 11, color: 0xe8ecf0, op: 0.92 },
            niebla_densa:      { n: 8,  color: 0xd0d4d8, op: 0.60 },
        }[tipo];

        const mat = new THREE.MeshBasicMaterial({ color: cfg.color, transparent: true, opacity: cfg.op });
        const pivotes = [];

        for (let i = 0; i < cfg.n; i++) {
            const pivote = new THREE.Group();
            pivote.rotation.y = (i / cfg.n) * Math.PI * 2 + rng(0, 0.5);
            scene.add(pivote);

            const nube = new THREE.Group();
            nube.position.set(rng(2.8, 4.8), rng(4.0, 6.0), 0);
            pivote.add(nube);

            const nBolas = 4 + Math.floor(rng(0, 4));
            for (let j = 0; j < nBolas; j++) {
                const r    = rng(0.20, 0.42);
                const bola = new THREE.Mesh(new THREE.SphereGeometry(r, 7, 7), mat);
                bola.position.set(
                    (j - nBolas / 2) * rng(0.24, 0.40) + rng(-0.08, 0.08),
                    rng(-0.14, 0.14),
                    rng(-0.08, 0.08)
                );
                nube.add(bola);
            }

            pivotes.push({ pivote, vel: 0.00005 + rng(0, 0.00009), nube, baseY: nube.position.y });
        }

        animados.push({ update: t => {
            for (const { pivote, vel, nube, baseY } of pivotes) {
                pivote.rotation.y += vel;
                nube.position.y = baseY + 0.09 * Math.sin(t * 0.22 + pivote.rotation.y * 4);
            }
        }});
    }

    // ── Lluvia ────────────────────────────────────────────────────────────────
    if (['tormenta', 'lluvia_suave'].includes(tipo)) {
        const intensidad = tipo === 'tormenta' ? 0.75 : 0.45;
        const N = tipo === 'tormenta' ? 900 : 500;
        const pos = new Float32Array(N * 3);
        for (let i = 0; i < N; i++) {
            pos[i * 3]     = rng(-6.5, 6.5);
            pos[i * 3 + 1] = rng(0, 10);
            pos[i * 3 + 2] = rng(-6.5, 6.5);
        }
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
        const matL = new THREE.PointsMaterial({ color: 0x8899cc, size: 0.04, transparent: true, opacity: intensidad });
        const puntos = new THREE.Points(geo, matL);
        scene.add(puntos);

        animados.push({ update: () => {
            const a = puntos.geometry.attributes.position;
            for (let i = 0; i < N; i++) {
                const y = a.getY(i) - 0.10;
                a.setY(i, y < 0 ? 10 : y);
            }
            a.needsUpdate = true;
        }});
    }

    // ── Nieve ─────────────────────────────────────────────────────────────────
    if (tipo === 'dia_nevado') {
        const N = 350;
        const pos   = new Float32Array(N * 3);
        const phaseX = new Float32Array(N);  // fase individual deriva horizontal
        const freqX  = new Float32Array(N);  // frecuencia deriva
        const velY   = new Float32Array(N);  // velocidad caída
        for (let i = 0; i < N; i++) {
            pos[i * 3]     = rng(-6.5, 6.5);
            pos[i * 3 + 1] = rng(0, 10);
            pos[i * 3 + 2] = rng(-6.5, 6.5);
            phaseX[i] = rng(0, Math.PI * 2);
            freqX[i]  = 0.18 + rng(0, 0.22);
            velY[i]   = 0.028 + rng(0, 0.022);
        }
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
        const matN = new THREE.PointsMaterial({
            color: 0xf0f4ff, size: 0.08, transparent: true, opacity: 0.80, sizeAttenuation: true,
        });
        const puntos = new THREE.Points(geo, matN);
        scene.add(puntos);

        animados.push({ update: t => {
            const a = puntos.geometry.attributes.position;
            for (let i = 0; i < N; i++) {
                let y = a.getY(i) - velY[i];
                let x = a.getX(i) + Math.sin(t * freqX[i] + phaseX[i]) * 0.004;
                if (y < 0) { y = 10; x = rng(-6.5, 6.5); }
                a.setY(i, y);
                a.setX(i, x);
            }
            a.needsUpdate = true;
        }});
    }

    // ── Update ────────────────────────────────────────────────────────────────
    function update(t) {
        for (const a of animados) a.update(t);
    }

    return { update };
};
