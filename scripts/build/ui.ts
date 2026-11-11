#!/usr/bin/env node
/**
 * ui.ts — сборка UI-бандлов платформы.
 *
 * Каждый сервис с `apps/<svc>/ui/` получает бандл из `ui/index.ts` в
 * `apps/<svc>/ui-dist/`: entry `index.js` (стабильное имя — его грузит
 * index.html), shared/lazy код — в `chunks/[name]-[hash].js`, минификация
 * вне --dev, sourcemap всегда (`linked` вне --dev, `inline` в --dev).
 *
 * Соседние `ui/*.ts` верхнего уровня — дополнительные приложения того же
 * сервиса: `ui/tsd.ts` собирается в `ui-dist/tsd.js` и делит shared-чанки
 * с основным бандлом (stock: консоль + ТСД-терминал).
 *
 * Файлы ui/, не попавшие в граф бандла (ассеты, vendor, html, css), копируются
 * в ui-dist/ как есть — mount продолжает отдавать их по тем же URL.
 *
 * Единый канон зависимостей — npm: `lit`, `marked`, `centrifuge`, CodeMirror,
 * ProseMirror, three, echarts, mermaid, livekit-client, @capacitor/*.
 * Динамические `import('pkg')` становятся lazy-чанками `chunks/` (splitting).
 * URL-импорты (`import('/static/…')`) остаются external — только data-ассеты.
 *
 * Embed-виджеты (внешние сайты, стабильные URL `/static/core/lib/embed-…`)
 * собираются в self-contained бандлы `core/frontend/embed-dist/`: внешний сайт
 * не имеет import-map, поэтому lit и весь граф инлайнятся в один файл. Отдаёт
 * их `core/app/spa.py::mount_core_frontend` по тем же URL.
 *
 * Использование:
 *   node scripts/build/ui.ts [--dev] [--watch] [--apps=flows,crm]
 */
/// <reference types="node" />
import * as esbuild from 'esbuild';
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(path.dirname(fileURLToPath(import.meta.url))));
const APPS_DIR = path.join(ROOT, 'apps');
const CORE_STATIC = path.join(ROOT, 'core', 'frontend', 'static');

const argv = process.argv.slice(2);
const DEV = argv.includes('--dev');
const WATCH = argv.includes('--watch');
const appsArg = argv.find((a) => a.startsWith('--apps='));
const APPS_FILTER: Set<string> | null = appsArg ? new Set(appsArg.slice('--apps='.length).split(',')) : null;

const SOURCE_EXTS = new Set(['.ts', '.js', '.mjs', '.cjs', '.tsx', '.jsx']);

/** Embed-точки входа: self-contained бандлы, отдаваемые по стабильным URL. */
const LIB_DIR = path.join(CORE_STATIC, 'lib');
const EMBED_DIST = path.join(ROOT, 'core', 'frontend', 'embed-dist');
const EMBED_ENTRYPOINTS = [
    'embed-flow-ui/flow-ui-embed-autoload.ts',
    'flow-ui/shell/embed-autoload.ts',
    'embed-chat/linnex-embed-autoload.ts',
    'customer-auth/autoload.ts',
    'map/autoload.ts',
    // Realm-файлы: audio rendering thread, service worker, синхронный brand bootstrap.
    // Исходники .ts, выход — стабильные URL `/static/core/lib/...`.
    'voice/worklets/voice-mic-capture.processor.ts',
    'pwa/sw.ts',
    'assets/brand-sync-bootstrap.ts',
];

/**
 * Модули для HTML-страниц, которые собирает backend (страница embed, shared session, UI Kit preview):
 * загружаются как `/static/core/lib/<путь>.js`. Общий граф (lit, core) выносится в общие чанки.
 */
const PAGE_ENTRYPOINTS = [
    'flow-ui/shell/page-host.ts',
    'flow-ui/components/platform-flow-ui.ts',
];
const DESIGN_SYSTEM_MANIFESTS_DIR = path.join(ROOT, 'tests', 'ui', 'design-system', 'components');
const DESIGN_SYSTEM_IMPORT_PREFIX = '@platform/lib/';

/** Абсолютные URL (/static/…data-ассеты) — внешние; всё остальное резолвится в npm. */
const urlExternalPlugin: esbuild.Plugin = {
    name: 'platform-url-external',
    setup(build) {
        build.onResolve({ filter: /^\// }, (args) =>
            args.kind === 'entry-point' ? undefined : { path: args.path, external: true },
        );
    },
};

interface UiApp {
    svc: string;
    uiDir: string;
    entries: string[];
    outDir: string;
}

function discoverApps(): UiApp[] {
    const apps: UiApp[] = [];
    for (const svc of readdirSync(APPS_DIR)) {
        const uiDir = path.join(APPS_DIR, svc, 'ui');
        if (!existsSync(uiDir) || !statSync(uiDir).isDirectory()) continue;
        const indexEntry = path.join(uiDir, 'index.ts');
        if (!existsSync(indexEntry)) {
            const hasSources = readdirSync(uiDir, { recursive: true }).some((f) => /\.tsx?$/.test(String(f)));
            if (!hasSources) continue;
            throw new Error(`[build-ui] ${svc}: нет точки входа ${path.relative(ROOT, indexEntry)}`);
        }
        if (!APPS_FILTER || APPS_FILTER.has(svc)) {
            // Дополнительные приложения сервиса — соседние `ui/*.ts` верхнего
            // уровня (`index.ts` обязателен и всегда первый).
            const entries = [
                indexEntry,
                ...readdirSync(uiDir)
                    .filter((f) => f !== 'index.ts' && f.endsWith('.ts') && statSync(path.join(uiDir, f)).isFile())
                    .sort()
                    .map((f) => path.join(uiDir, f)),
            ];
            apps.push({ svc, uiDir, entries, outDir: path.join(APPS_DIR, svc, 'ui-dist') });
        }
    }
    return apps;
}

/**
 * Копирует в ui-dist файлы ui/, которых нет в графе бандла (ассеты, vendor, html, css).
 * bundledInputs=null (watch-режим): копируются только не-исходники и vendor/.
 */
/** Файлы/каталоги ui/, которые никогда не попадают в ui-dist (мусор dev-окружения). */
const COPY_EXCLUDE_NAMES = new Set(['node_modules', 'package.json', 'package-lock.json', 'tsconfig.json', '.gitkeep']);

function copyUnbundledAssets(uiDir: string, outDir: string, bundledInputs: Set<string> | null): number {
    let copied = 0;
    const walk = (dir: string) => {
        for (const name of readdirSync(dir)) {
            if (COPY_EXCLUDE_NAMES.has(name)) continue;
            const src = path.join(dir, name);
            const stat = statSync(src);
            if (stat.isDirectory()) {
                walk(src);
                continue;
            }
            const ext = path.extname(name);
            if (ext === '.ts' || ext === '.tsx') continue;
            const isSource = SOURCE_EXTS.has(ext);
            if (isSource && bundledInputs === null && !src.includes(`${path.sep}vendor${path.sep}`)) continue;
            if (isSource && bundledInputs !== null && bundledInputs.has(src)) continue;
            const dst = path.join(outDir, path.relative(uiDir, src));
            mkdirSync(path.dirname(dst), { recursive: true });
            copyFileSync(src, dst);
            copied += 1;
        }
    };
    walk(uiDir);
    return copied;
}

function buildOptions({ entries, outDir }: UiApp): esbuild.BuildOptions & { metafile: true } {
    return {
        entryPoints: [...entries],
        bundle: true,
        splitting: true,
        format: 'esm',
        platform: 'browser',
        target: 'es2022',
        outdir: outDir,
        entryNames: '[name]',
        chunkNames: 'chunks/[name]-[hash]',
        assetNames: 'assets/[name]-[hash]',
        minify: !DEV,
        sourcemap: DEV ? 'inline' : 'linked',
        metafile: true,
        logLevel: 'warning',
        alias: {
            '@platform/lib': path.join(CORE_STATIC, 'lib'),
        },
        plugins: [urlExternalPlugin],
    };
}

async function buildApp(app: UiApp): Promise<esbuild.BuildResult> {
    const { svc, uiDir, outDir } = app;
    rmSync(outDir, { recursive: true, force: true });
    const result = await esbuild.build(buildOptions(app));
    const bundledInputs = new Set(Object.keys(result.metafile.inputs).map((p) => path.resolve(ROOT, p)));
    const copied = copyUnbundledAssets(uiDir, outDir, bundledInputs);
    const outputs = Object.keys(result.metafile.outputs)
        .map((p) => path.relative(outDir, path.resolve(ROOT, p)))
        .filter((p) => p.endsWith('.js'));
    const bytes = Object.values(result.metafile.outputs).reduce((sum, o) => sum + o.bytes, 0);
    console.log(`[build-ui] ${svc}: ${outputs.length} js files, ${(bytes / 1024).toFixed(0)} KiB, ${copied} assets copied`);
    return result;
}

/**
 * Embed-бандлы: один файл на entrypoint, весь граф (включая lit) инлайнится —
 * внешний сайт грузит их без import-map. Выход зеркалит исходный относительный
 * путь в lib/: granian (`--static-path-route /static/core/lib`) и spa.py отдают
 * embed-dist по стабильным URL `/static/core/lib/...`.
 */
async function buildEmbed() {
    const entries = EMBED_ENTRYPOINTS.map((rel) => {
        const abs = path.join(LIB_DIR, rel);
        if (!existsSync(abs)) {
            throw new Error(`[build-ui] embed: нет точки входа ${path.relative(ROOT, abs)}`);
        }
        return abs;
    });
    // В watch-режиме каталог не удаляется: сервисы make app уже стартуют на нём и падают без бандлов.
    if (!WATCH) rmSync(EMBED_DIST, { recursive: true, force: true });
    for (const entry of entries) {
        const rel = path.relative(LIB_DIR, entry).replace(/\.ts$/, '.js');
        await esbuild.build({
            entryPoints: [entry],
            bundle: true,
            splitting: false,
            format: 'esm',
            platform: 'browser',
            target: 'es2022',
            outfile: path.join(EMBED_DIST, rel),
            minify: !DEV,
            sourcemap: DEV ? 'inline' : 'linked',
            logLevel: 'warning',
            alias: {
                '@platform/lib': LIB_DIR,
            },
            plugins: [urlExternalPlugin],
        });
        console.log(`[build-ui] embed: ${rel}`);
    }
    // /static/core/lib целиком отдаётся из embed-dist: туда же ложатся не-TS ассеты lib/ (css, AudioWorklet).
    const assets = copyUnbundledAssets(LIB_DIR, EMBED_DIST, new Set());
    console.log(`[build-ui] embed: ${assets} assets`);
}

/** Модули компонентов UI Kit: путь из `import:` каждого manifest.yaml карточки. */
function designSystemEntries(): string[] {
    const entries: string[] = [];
    for (const name of readdirSync(DESIGN_SYSTEM_MANIFESTS_DIR)) {
        const manifest = path.join(DESIGN_SYSTEM_MANIFESTS_DIR, name, 'manifest.yaml');
        if (!existsSync(manifest)) continue;
        const importPath = /^import:\s*"([^"]+)"\s*$/m.exec(readFileSync(manifest, 'utf8'))?.[1];
        if (typeof importPath !== 'string' || !importPath.startsWith(DESIGN_SYSTEM_IMPORT_PREFIX)) {
            throw new Error(`[build-ui] ${path.relative(ROOT, manifest)}: import должен начинаться с ${DESIGN_SYSTEM_IMPORT_PREFIX}`);
        }
        const rel = importPath.slice(DESIGN_SYSTEM_IMPORT_PREFIX.length).replace(/\.js$/, '.ts');
        const abs = path.join(LIB_DIR, rel);
        if (!existsSync(abs)) {
            throw new Error(`[build-ui] ${path.relative(ROOT, manifest)}: нет модуля ${path.relative(ROOT, abs)}`);
        }
        entries.push(abs);
    }
    if (entries.length === 0) {
        throw new Error('[build-ui] design-system: manifest.yaml компонентов не найдены');
    }
    return entries;
}

async function buildPageModules() {
    const entries = [
        ...PAGE_ENTRYPOINTS.map((rel) => {
            const abs = path.join(LIB_DIR, rel);
            if (!existsSync(abs)) {
                throw new Error(`[build-ui] page: нет точки входа ${path.relative(ROOT, abs)}`);
            }
            return abs;
        }),
        ...designSystemEntries(),
    ];
    await esbuild.build({
        entryPoints: entries,
        outbase: LIB_DIR,
        outdir: EMBED_DIST,
        bundle: true,
        splitting: true,
        format: 'esm',
        platform: 'browser',
        target: 'es2022',
        chunkNames: '_chunks/[name]-[hash]',
        minify: !DEV,
        sourcemap: DEV ? 'inline' : 'linked',
        logLevel: 'warning',
        alias: {
            '@platform/lib': LIB_DIR,
        },
        plugins: [urlExternalPlugin],
    });
    console.log(`[build-ui] page modules: ${entries.length}`);
}

async function main(): Promise<void> {
    await buildEmbed();
    await buildPageModules();
    const apps = discoverApps();
    if (!apps.length) {
        console.error('[build-ui] entries not found (apps/*/ui/index.ts)');
        process.exit(1);
    }
    if (WATCH) {
        // ui-dist не удаляется: esbuild перезаписывает файлы на месте, а сервисы make app раздают их без перерыва.
        for (const app of apps) {
            const ctx = await esbuild.context({
                ...buildOptions(app),
                minify: false,
                sourcemap: 'inline',
                metafile: false,
            });
            await ctx.watch();
            console.log(`[build-ui] watching ${app.svc}`);
        }
        // Ассеты в watch-режиме копируем один раз — редко меняются.
        for (const app of apps) {
            copyUnbundledAssets(app.uiDir, app.outDir, null);
        }
        return;
    }
    for (const app of apps) {
        await buildApp(app);
    }
    console.log(`[build-ui] OK: ${apps.length} apps`);
}

await main();
