/**
 * <cosmic-scene> — фиксированная fullscreen WebGL-сцена публичных страниц.
 *
 * Слои: FBM-неbula (hue лерпится по главам), starfield Points, «agent core»
 * (икосаэдр transmission + орбитальные кольца + CanvasTexture-лейбл главы —
 * аналог экрана девайса quantumwallet.tech). Поза объекта и камеры — функция
 * прогресса скролла: состояние ставит CosmicScrollController через свойства.
 *
 * three.js грузится ленивым чанком (`import('three')`). WebGL2 нет — элемент
 * скрывается, остаётся CSS-неbula фона scope. prefers-reduced-motion — один
 * статичный кадр без цикла.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { cssVar } from '@platform/lib/utils/css-var.js';
import type * as THREE from 'three';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';

type ThreeModule = typeof THREE;

const NEBULA_FRAGMENT = /* glsl */ `
precision highp float;

uniform float uTime;
uniform float uHueA;
uniform float uHueB;
uniform float uIntensity;
uniform float uProgress;
uniform vec2 uRes;

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(
        mix(hash(i + vec2(0.0, 0.0)), hash(i + vec2(1.0, 0.0)), u.x),
        mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x),
        u.y
    );
}

float fbm(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    mat2 rot = mat2(0.8, 0.6, -0.6, 0.8);
    for (int i = 0; i < 5; i++) {
        v += a * noise(p);
        p = rot * p * 2.0 + vec2(100.0);
        a *= 0.5;
    }
    return v;
}

vec3 hsl2rgb(float h, float s, float l) {
    vec3 rgb = clamp(abs(mod(h * 6.0 + vec3(0.0, 4.0, 2.0), 6.0) - 3.0) - 1.0, 0.0, 1.0);
    return l + s * (rgb - 0.5) * (1.0 - abs(2.0 * l - 1.0));
}

void main() {
    vec2 uv = gl_FragCoord.xy / uRes;
    vec2 p = (uv - 0.5) * vec2(uRes.x / uRes.y, 1.0);

    float slow = uTime * 0.03;
    float n = fbm(p * 1.7 + vec2(slow, -uProgress * 2.2));
    float m = fbm(p * 3.4 - vec2(slow * 1.3));

    float hue = mix(uHueA, uHueB, uv.x * 0.7 + n * 0.45);
    vec3 neb = hsl2rgb(hue, 0.78, 0.55);

    vec3 base = vec3(0.008, 0.012, 0.024);
    float depth = fbm(p * 0.9 + vec2(0.0, uProgress * 1.2));
    float glow = smoothstep(1.25, 0.05, length(p - vec2(0.1, -0.1))) * 0.85;

    vec3 col = base
        + neb * (n * 0.5 + m * 0.28) * uIntensity * glow
        + neb * pow(n, 3.0) * 0.22
        + hsl2rgb(uHueB, 0.6, 0.35) * pow(depth, 4.0) * 0.35;

    float vig = 1.0 - dot(uv - 0.5, uv - 0.5) * 1.1;
    gl_FragColor = vec4(col * vig, 1.0);
}
`;

const NEBULA_VERTEX = /* glsl */ `
void main() {
    gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

interface NebulaUniforms {
    [uniform: string]: { value: unknown };
    uTime: { value: number };
    uHueA: { value: number };
    uHueB: { value: number };
    uIntensity: { value: number };
    uProgress: { value: number };
    uRes: { value: THREE.Vector2 };
}

export class CosmicScene extends PlatformElement {
    static override properties: PropertyDeclarations = {
        chapter: { type: Number, attribute: false },
        label: { type: String, attribute: false },
        progress: { type: Number, attribute: false },
        hue: { type: Number, attribute: false },
    };

    declare chapter: number;
    declare label: string;
    declare progress: number;
    declare hue: number;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                position: fixed;
                inset: 0;
                z-index: 0;
                pointer-events: none;
                display: block;
                background: var(--marketing-cosmic-bg);
            }
            :host([hidden]) { display: none; }
            canvas {
                display: block;
                width: 100%;
                height: 100%;
            }
        `,
    ];

    private _three: ThreeModule | null = null;
    private _renderer: THREE.WebGLRenderer | null = null;
    private _scene: THREE.Scene | null = null;
    private _camera: THREE.PerspectiveCamera | null = null;
    private _uniforms: NebulaUniforms | null = null;
    private _starfield: THREE.Points | null = null;
    private _core: THREE.Group | null = null;
    private _ringA: THREE.Mesh | null = null;
    private _ringB: THREE.Mesh | null = null;
    private _labelSprite: THREE.Sprite | null = null;
    private _labelTexture: THREE.CanvasTexture | null = null;
    private _face: THREE.Sprite | null = null;
    private _faceMat: THREE.SpriteMaterial | null = null;
    private _faceGlow: THREE.Sprite | null = null;
    private _faceGlowMat: THREE.SpriteMaterial | null = null;
    private _disposables: { dispose(): void }[] = [];
    private _clockOffset = 0;
    private _targetHue = 0;
    private _currentHue = 0;
    private _reduced = false;
    private _live = false;

    constructor() {
        super();
        this.chapter = 0;
        this.label = '';
        this.progress = 0;
        this.hue = 0;
    }

    override firstUpdated(): void {
        this._reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        const probe = document.createElement('canvas').getContext('webgl2');
        if (probe === null) {
            this.hidden = true;
            return;
        }
        void this._init();
        this.useDomEvent(window, 'resize', () => this._resize());
        this.useDomEvent(document, 'visibilitychange', () => {
            if (document.hidden) {
                this._stopLoop();
            } else if (this._live) {
                this._startLoop();
            }
        });
    }

    override disconnectedCallback(): void {
        this._stopLoop();
        for (const d of this._disposables) {
            d.dispose();
        }
        this._disposables = [];
        if (this._renderer !== null) {
            this._renderer.dispose();
            this._renderer = null;
        }
        super.disconnectedCallback();
    }

    override updated(changed: PropertyValues<this>): void {
        if (changed.has('hue')) {
            this._targetHue = this.hue;
        }
        if (changed.has('label')) {
            this._drawLabel();
        }
        if (this._reduced && this._renderer !== null && this._scene !== null && this._camera !== null) {
            this._pose();
            this._renderer.render(this._scene, this._camera);
        }
    }

    private async _init(): Promise<void> {
        const THREE_NS = await import('three');
        if (!this.isConnected) {
            return;
        }
        this._three = THREE_NS;

        const canvas = this._requireCanvas();
        const renderer = new THREE_NS.WebGLRenderer({
            canvas,
            antialias: true,
            powerPreference: 'high-performance',
        });
        const coarse = window.matchMedia('(pointer: coarse)').matches;
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, coarse ? 1.5 : 2));
        renderer.setClearColor(0x030508, 1);
        this._renderer = renderer;

        const scene = new THREE_NS.Scene();
        scene.fog = new THREE_NS.FogExp2(0x030508, 0.16);
        this._scene = scene;

        this._camera = new THREE_NS.PerspectiveCamera(50, 1, 0.1, 60);
        this._camera.position.set(0, 0, 6);

        this._buildNebula(THREE_NS, scene);
        this._buildStarfield(THREE_NS, scene, coarse);
        this._buildCore(THREE_NS, scene);
        this._buildGrid(THREE_NS, scene);
        this._resize();

        this._live = true;
        if (this._reduced) {
            this._pose();
            renderer.render(scene, this._camera);
        } else {
            this._startLoop();
        }
    }

    private _buildNebula(T: ThreeModule, scene: THREE.Scene): void {
        const uniforms: NebulaUniforms = {
            uTime: { value: 0 },
            uHueA: { value: 0.55 },
            uHueB: { value: 0.65 },
            uIntensity: { value: 1 },
            uProgress: { value: 0 },
            uRes: { value: new T.Vector2(1, 1) },
        };
        this._uniforms = uniforms;
        const geo = new T.PlaneGeometry(2, 2);
        const mat = new T.ShaderMaterial({
            uniforms,
            vertexShader: NEBULA_VERTEX,
            fragmentShader: NEBULA_FRAGMENT,
            depthWrite: false,
            depthTest: false,
        });
        const mesh = new T.Mesh(geo, mat);
        mesh.renderOrder = -10;
        mesh.frustumCulled = false;
        scene.add(mesh);
        this._disposables.push(geo, mat);
    }

    private _buildStarfield(T: ThreeModule, scene: THREE.Scene, coarse: boolean): void {
        const count = coarse ? 500 : 1400;
        const positions = new Float32Array(count * 3);
        const sizes = new Float32Array(count);
        for (let i = 0; i < count; i++) {
            positions[i * 3] = (Math.random() - 0.5) * 22;
            positions[i * 3 + 1] = (Math.random() - 0.5) * 14;
            positions[i * 3 + 2] = -Math.random() * 10;
            sizes[i] = Math.random();
        }
        const geo = new T.BufferGeometry();
        geo.setAttribute('position', new T.BufferAttribute(positions, 3));
        geo.setAttribute('aSize', new T.BufferAttribute(sizes, 1));
        const mat = new T.PointsMaterial({
            color: new T.Color(cssVar('--marketing-cosmic-cyan', '#8fd8ff')),
            size: 0.045,
            sizeAttenuation: true,
            transparent: true,
            opacity: 0.85,
            blending: T.AdditiveBlending,
            depthWrite: false,
        });
        const points = new T.Points(geo, mat);
        points.renderOrder = -5;
        scene.add(points);
        this._starfield = points;
        this._disposables.push(geo, mat);
    }

    private _buildCore(T: ThreeModule, scene: THREE.Scene): void {
        const core = new T.Group();
        const accent = new T.Color(cssVar('--marketing-cosmic-cyan', '#3ddcff'));
        const deep = new T.Color(cssVar('--marketing-cosmic-blue', '#3a4be2'));

        const geo = new T.IcosahedronGeometry(0.9, 1);
        const mat = new T.MeshPhysicalMaterial({
            color: new T.Color(0x0a1620),
            metalness: 0.1,
            roughness: 0.12,
            transmission: 0.92,
            thickness: 1.4,
            ior: 1.45,
            iridescence: 0.9,
            iridescenceIOR: 1.3,
            clearcoat: 0.6,
            clearcoatRoughness: 0.25,
            envMapIntensity: 1.4,
        });
        const body = new T.Mesh(geo, mat);
        core.add(body);
        this._disposables.push(geo, mat);

        const wireGeo = new T.IcosahedronGeometry(0.915, 1);
        const wireMat = new T.MeshBasicMaterial({
            color: accent,
            wireframe: true,
            transparent: true,
            opacity: 0.22,
        });
        const wire = new T.Mesh(wireGeo, wireMat);
        core.add(wire);
        this._disposables.push(wireGeo, wireMat);

        const ringGeoA = new T.TorusGeometry(1.45, 0.004, 8, 160);
        const ringMatA = new T.MeshBasicMaterial({ color: accent, transparent: true, opacity: 0.55 });
        this._ringA = new T.Mesh(ringGeoA, ringMatA);
        this._ringA.rotation.x = Math.PI / 2.4;
        core.add(this._ringA);
        this._disposables.push(ringGeoA, ringMatA);

        const ringGeoB = new T.TorusGeometry(1.7, 0.003, 8, 160);
        const ringMatB = new T.MeshBasicMaterial({ color: deep, transparent: true, opacity: 0.35 });
        this._ringB = new T.Mesh(ringGeoB, ringMatB);
        this._ringB.rotation.x = Math.PI / 1.9;
        this._ringB.rotation.z = 0.6;
        core.add(this._ringB);
        this._disposables.push(ringGeoB, ringMatB);

        const inner = new T.PointLight(accent, 6, 12, 1.8);
        core.add(inner);
        const rim = new T.PointLight(deep, 3.5, 14, 1.8);
        rim.position.set(-3, 2, 3);
        scene.add(rim);
        scene.add(new T.AmbientLight(0x223344, 1.6));

        this._labelSprite = this._makeLabelSprite(T);
        this._labelSprite.position.set(0, -1.9, 0.4);
        core.add(this._labelSprite);

        core.position.set(0, 0.1, 1.2);
        this._core = core;
        scene.add(core);
        this._loadFace(T);
        void document.fonts.ready.then(() => this._drawLabel());
    }

    /** «Живое» лицо Лары внутри ядра: портрет обрезан кругом-маской,
        болтается билбордом в центре икосаэдра, дышит и глитчит в _pose. */
    private _loadFace(T: ThreeModule): void {
        new T.TextureLoader().load('/static/frontend/assets/images/main_img.png', (img) => {
            if (!this.isConnected || this._core === null) {
                return;
            }
            const size = 512;
            const canvas = document.createElement('canvas');
            canvas.width = size;
            canvas.height = size;
            const ctx = canvas.getContext('2d');
            if (ctx === null) {
                throw new Error('cosmic-scene: 2d context unavailable');
            }
            const src = img.image;
            const sw = Math.min(src.width, src.height);
            const sx = (src.width - sw) / 2;
            const sy = (src.height - sw) * 0.22;
            ctx.drawImage(src, sx, sy, sw, sw, 0, 0, size, size);
            ctx.globalCompositeOperation = 'destination-in';
            const mask = ctx.createRadialGradient(
                size / 2, size / 2, size * 0.2,
                size / 2, size / 2, size * 0.5,
            );
            mask.addColorStop(0, 'rgba(255,255,255,1)');
            mask.addColorStop(0.7, 'rgba(255,255,255,0.92)');
            mask.addColorStop(1, 'rgba(255,255,255,0)');
            ctx.fillStyle = mask;
            ctx.fillRect(0, 0, size, size);
            ctx.globalCompositeOperation = 'source-over';

            const tex = new T.CanvasTexture(canvas);
            tex.colorSpace = T.SRGBColorSpace;
            this._faceMat = new T.SpriteMaterial({
                map: tex,
                transparent: true,
                opacity: 0.85,
                depthWrite: false,
            });
            this._face = new T.Sprite(this._faceMat);
            this._face.scale.set(1.6, 1.6, 1);
            this._face.position.set(0, 0.05, 1.0);
            this._face.renderOrder = 3;
            this._core.add(this._face);
            this._disposables.push(tex, this._faceMat);

            const glowCanvas = document.createElement('canvas');
            glowCanvas.width = 256;
            glowCanvas.height = 256;
            const gtx = glowCanvas.getContext('2d');
            if (gtx === null) {
                throw new Error('cosmic-scene: 2d context unavailable');
            }
            const glow = gtx.createRadialGradient(128, 128, 8, 128, 128, 128);
            glow.addColorStop(0, 'rgba(255,255,255,0.85)');
            glow.addColorStop(0.4, 'rgba(255,255,255,0.28)');
            glow.addColorStop(1, 'rgba(255,255,255,0)');
            gtx.fillStyle = glow;
            gtx.fillRect(0, 0, 256, 256);
            const glowTex = new T.CanvasTexture(glowCanvas);
            glowTex.colorSpace = T.SRGBColorSpace;
            const glowMat = new T.SpriteMaterial({
                map: glowTex,
                color: new T.Color(cssVar('--marketing-cosmic-cyan', '#3ddcff')),
                transparent: true,
                opacity: 0.4,
                depthWrite: false,
                blending: T.AdditiveBlending,
            });
            this._faceGlowMat = glowMat;
            this._faceGlow = new T.Sprite(glowMat);
            this._faceGlow.scale.set(2.9, 2.9, 1);
            this._faceGlow.position.set(0, 0.05, 0.9);
            this._faceGlow.renderOrder = 2;
            this._core.add(this._faceGlow);
            this._disposables.push(glowTex, glowMat);

            if (this._reduced && this._renderer !== null && this._scene !== null && this._camera !== null) {
                this._pose();
                this._renderer.render(this._scene, this._camera);
            }
        });
    }

    private _makeLabelSprite(T: ThreeModule): THREE.Sprite {
        const canvas = document.createElement('canvas');
        canvas.width = 1024;
        canvas.height = 320;
        const tex = new T.CanvasTexture(canvas);
        tex.colorSpace = T.SRGBColorSpace;
        this._labelTexture = tex;
        const mat = new T.SpriteMaterial({
            map: tex,
            transparent: true,
            opacity: 0.95,
            depthWrite: false,
        });
        const sprite = new T.Sprite(mat);
        sprite.scale.set(3.4, 1.06, 1);
        this._disposables.push(mat, tex);
        return sprite;
    }

    private _drawLabel(): void {
        if (this._labelTexture === null) {
            return;
        }
        const canvas = this._labelTexture.image;
        if (!(canvas instanceof HTMLCanvasElement)) {
            throw new Error('cosmic-scene: label texture image is not a canvas');
        }
        const ctx = canvas.getContext('2d');
        if (ctx === null) {
            throw new Error('cosmic-scene: 2d context unavailable');
        }
        const mono = cssVar('--font-mono', "'JetBrains Mono', monospace");
        const cyan = cssVar('--marketing-cosmic-cyan', '#3ddcff');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = 'rgba(255,255,255,0.6)';
        ctx.font = `500 34px ${mono}`;
        ctx.fillText('— AGENT CORE —', canvas.width / 2, 70);
        ctx.fillStyle = cyan;
        ctx.font = `600 92px ${mono}`;
        ctx.fillText(this.label.toUpperCase(), canvas.width / 2, 190);
        this._labelTexture.needsUpdate = true;
    }

    private _buildGrid(T: ThreeModule, scene: THREE.Scene): void {
        const lineMat = new T.LineBasicMaterial({
            color: new T.Color(cssVar('--marketing-cosmic-ink', '#1b2a3d')),
            transparent: true,
            opacity: 0.4,
        });
        const points: THREE.Vector3[] = [];
        for (let i = -4; i <= 4; i++) {
            const y = i * 1.4;
            points.push(new T.Vector3(-14, y, -6), new T.Vector3(14, y, -6));
        }
        const geo = new T.BufferGeometry().setFromPoints(points);
        const lines = new T.LineSegments(geo, lineMat);
        lines.renderOrder = -4;
        scene.add(lines);
        this._disposables.push(geo, lineMat);
    }

    private _pose(): void {
        const t = this._clockOffset;
        const p = this.progress;
        if (this._core !== null) {
            this._core.rotation.y = p * Math.PI * 2 + Math.sin(t * 0.25) * 0.14;
            this._core.rotation.x = Math.sin(p * Math.PI) * 0.22 + Math.sin(t * 0.4) * 0.05;
            this._core.position.y = 0.1 + Math.sin(t * 0.55) * 0.07;
            const zoom = 1 + Math.sin(p * Math.PI) * 0.18;
            this._core.scale.setScalar(zoom);
        }
        if (this._ringA !== null) {
            this._ringA.rotation.z = t * 0.3 + p * 2.4;
        }
        if (this._ringB !== null) {
            this._ringB.rotation.z = -t * 0.22 - p * 1.7;
        }
        if (this._face !== null && this._faceMat !== null) {
            const breathe = 1 + Math.sin(t * 1.35) * 0.03;
            this._face.scale.set(1.6 * breathe, 1.6 * breathe, 1);
            this._faceMat.opacity = 0.78 + Math.sin(t * 2.1) * 0.12;
            this._faceMat.color.setHSL(this._currentHue, 0.42, 0.88);
            this._face.position.y = 0.05 + Math.sin(t * 0.9) * 0.025;
            this._face.position.x = t % 7.3 < 0.09 ? (Math.random() - 0.5) * 0.05 : 0;
        }
        if (this._faceGlow !== null && this._faceGlowMat !== null) {
            this._faceGlowMat.opacity = 0.3 + Math.sin(t * 1.7) * 0.12;
            this._faceGlowMat.color.setHSL(this._currentHue, 0.85, 0.62);
            const gs = 2.9 + Math.sin(t * 1.35) * 0.12;
            this._faceGlow.scale.set(gs, gs, 1);
        }
        if (this._starfield !== null) {
            this._starfield.rotation.z = t * 0.008 + p * 0.35;
            this._starfield.position.y = p * 2.4;
        }
        if (this._camera !== null) {
            this._camera.position.x = Math.sin(p * Math.PI * 1.6) * 0.5;
            this._camera.position.y = 0.15 + p * 0.6;
            this._camera.lookAt(0, 0.1, 1.2);
        }
    }

    private _tick = (): void => {
        if (this._renderer === null || this._scene === null || this._camera === null) {
            return;
        }
        this._clockOffset = this._renderer.info.render.frame / 60;
        const hueLerp = this._targetHue - this._currentHue;
        if (Math.abs(hueLerp) > 0.0004) {
            this._currentHue += hueLerp * 0.055;
        } else {
            this._currentHue = this._targetHue;
        }
        if (this._uniforms !== null) {
            const base = this._currentHue;
            this._uniforms.uHueA.value = base;
            this._uniforms.uHueB.value = base + 0.09;
            this._uniforms.uTime.value = this._clockOffset;
            this._uniforms.uProgress.value = this.progress;
            this._uniforms.uIntensity.value = 1 + Math.sin(this.progress * Math.PI) * 0.15;
        }
        this._pose();
        this._renderer.render(this._scene, this._camera);
    };

    private _startLoop(): void {
        if (this._renderer === null) {
            return;
        }
        this._renderer.setAnimationLoop(this._tick);
    }

    private _stopLoop(): void {
        if (this._renderer !== null) {
            this._renderer.setAnimationLoop(null);
        }
    }

    private _resize(): void {
        if (this._renderer === null || this._camera === null || this._uniforms === null) {
            return;
        }
        const w = window.innerWidth;
        const h = window.innerHeight;
        this._renderer.setSize(w, h, false);
        this._camera.aspect = w / h;
        this._camera.updateProjectionMatrix();
        this._uniforms.uRes.value.set(w * this._renderer.getPixelRatio(), h * this._renderer.getPixelRatio());
    }

    private _requireCanvas(): HTMLCanvasElement {
        const canvas = this.renderRoot.querySelector('canvas');
        if (!(canvas instanceof HTMLCanvasElement)) {
            throw new Error('cosmic-scene: canvas element missing');
        }
        return canvas;
    }

    /** Текст «экрана» agent core — лейбл активной главы, ставит контроллер. */
    setChapterLabel(label: string): void {
        if (this.label !== label) {
            this.label = label;
        }
        void document.fonts.ready.then(() => this._drawLabel());
    }

    override render(): TemplateResult {
        return html`<canvas></canvas>`;
    }
}

customElements.define('cosmic-scene', CosmicScene);
