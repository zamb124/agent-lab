#!/usr/bin/env node
/**
 * build_ui.mjs — сборка UI-бандлов платформы.
 *
 * Каждый сервис с `apps/<svc>/ui/index.ts|index.js` получает бандл в
 * `apps/<svc>/ui-dist/`: entry `index.js` (стабильное имя — его грузит
 * index.html), shared/lazy код — в `chunks/[name]-[hash].js`, минификация
 * вне --dev, sourcemap всегда (`linked` вне --dev, `inline` в --dev).
 *
 * Файлы ui/, не попавшие в граф бандла (ассеты, vendor, html, css), копируются
 * в ui-dist/ как есть — mount продолжает отдавать их по тем же URL.
 *
 * Vendored модули, импортированные относительным путём (`assets/js/lit/…`,
 * `marked.esm.min.js`, `centrifuge.esm.min.js`), редиректятся в npm-пакеты —
 * иначе в бандл попали бы две копии Lit и customElements.define упал бы.
 * URL-импорты (`import('/static/…')`, `import('/crm/ui/vendor/…')`) остаются
 * external — это осознанный lazy-load тяжёлых вендоров (CodeMirror, three).
 *
 * Использование:
 *   node scripts/build_ui.mjs [--dev] [--watch] [--apps=flows,crm]
 */
import * as esbuild from 'esbuild';
import { execSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const APPS_DIR = path.join(ROOT, 'apps');
const CORE_STATIC = path.join(ROOT, 'core', 'frontend', 'static');

const argv = process.argv.slice(2);
const DEV = argv.includes('--dev');
const WATCH = argv.includes('--watch');
const appsArg = argv.find((a) => a.startsWith('--apps='));
const APPS_FILTER = appsArg ? new Set(appsArg.slice('--apps='.length).split(',')) : null;

const SOURCE_EXTS = new Set(['.ts', '.js', '.mjs', '.cjs', '.tsx', '.jsx']);

/** Единый lit/@capacitor/vendored-resolver: предотвращает дубли модулей в бандле. */
const vendoredDedupPlugin = {
    name: 'platform-vendored-dedup',
    setup(build) {
        const vendoredToNpm = [
            [/assets\/js\/lit\/lit\.min\.js$/, 'lit'],
            [/assets\/js\/lit\/decorators\.min\.js$/, 'lit/decorators.js'],
            [/assets\/js\/lit\/directives\/class-map\.min\.js$/, 'lit/directives/class-map.js'],
            [/assets\/js\/lit\/directives\/repeat\.min\.js$/, 'lit/directives/repeat.js'],
            [/assets\/js\/lit\/directives\/unsafe-html\.min\.js$/, 'lit/directives/unsafe-html.js'],
            [/assets\/js\/lit\/directives\/guard\.min\.js$/, 'lit/directives/guard.js'],
            [/assets\/js\/lit\/directives\/when\.min\.js$/, 'lit/directives/when.js'],
            [/assets\/js\/marked\/marked\.esm\.min\.js$/, 'marked'],
            [/assets\/js\/centrifuge\/centrifuge\.esm\.min\.js$/, 'centrifuge'],
        ];
        for (const [filter, target] of vendoredToNpm) {
            build.onResolve({ filter }, (args) =>
                build.resolve(target, { resolveDir: args.resolveDir, kind: args.kind }),
            );
        }
        // @capacitor/* не в package.json — vendored под core/frontend/static/assets/js/vendor/.
        const capacitorVendor = path.join(CORE_STATIC, 'assets', 'js', 'vendor', '@capacitor');
        for (const pkg of ['core', 'app', 'push-notifications', 'splash-screen']) {
            build.onResolve({ filter: new RegExp(`^@capacitor/${pkg}$`) }, () => ({
                path: path.join(capacitorVendor, pkg, 'index.js'),
            }));
        }
        // Абсолютные URL (/static/…, /<svc>/ui/vendor/…) — внешние lazy/ассеты.
        build.onResolve({ filter: /^\// }, (args) =>
            args.kind === 'entry-point' ? undefined : { path: args.path, external: true },
        );
    },
};

function discoverApps() {
    const apps = [];
    for (const svc of readdirSync(APPS_DIR)) {
        const uiDir = path.join(APPS_DIR, svc, 'ui');
        if (!statSyncSafe(uiDir)?.isDirectory()) continue;
        const entry = ['index.ts', 'index.js'].map((f) => path.join(uiDir, f)).find(existsSync);
        if (entry && (!APPS_FILTER || APPS_FILTER.has(svc))) {
            apps.push({ svc, uiDir, entry, outDir: path.join(APPS_DIR, svc, 'ui-dist') });
        }
    }
    return apps;
}

function statSyncSafe(p) {
    try {
        return statSync(p);
    } catch {
        return null;
    }
}

/**
 * Копирует в ui-dist файлы ui/, которых нет в графе бандла (ассеты, vendor, html, css).
 * bundledInputs=null (watch-режим): копируются только не-исходники и vendor/.
 */
/** Файлы/каталоги ui/, которые никогда не попадают в ui-dist (мусор dev-окружения). */
const COPY_EXCLUDE_NAMES = new Set(['node_modules', 'package.json', 'package-lock.json', 'tsconfig.json']);

function copyUnbundledAssets(uiDir, outDir, bundledInputs) {
    let copied = 0;
    const walk = (dir) => {
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

function gitSha() {
    try {
        return execSync('git rev-parse --short HEAD', { cwd: ROOT, encoding: 'utf-8' }).trim();
    } catch {
        return 'unknown';
    }
}

function buildOptions({ uiDir, entry, outDir }) {
    return {
        entryPoints: [entry],
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
        plugins: [vendoredDedupPlugin],
    };
}

async function buildApp({ svc, uiDir, entry, outDir }) {
    rmSync(outDir, { recursive: true, force: true });
    const result = await esbuild.build(buildOptions({ uiDir, entry, outDir }));
    const bundledInputs = new Set(Object.keys(result.metafile.inputs).map((p) => path.resolve(ROOT, p)));
    const copied = copyUnbundledAssets(uiDir, outDir, bundledInputs);
    const outputs = Object.keys(result.metafile.outputs)
        .map((p) => path.relative(outDir, path.resolve(ROOT, p)))
        .filter((p) => p.endsWith('.js'));
    writeFileSync(
        path.join(outDir, 'ui-manifest.json'),
        JSON.stringify(
            {
                service: svc,
                entry: 'index.js',
                builtAt: new Date().toISOString(),
                sha: gitSha(),
                js: outputs,
            },
            null,
            2,
        ),
    );
    const bytes = Object.values(result.metafile.outputs).reduce((sum, o) => sum + o.bytes, 0);
    console.log(`[build-ui] ${svc}: ${outputs.length} js files, ${(bytes / 1024).toFixed(0)} KiB, ${copied} assets copied`);
    return result;
}

async function main() {
    const apps = discoverApps();
    if (!apps.length) {
        console.error('[build-ui] entries not found (apps/*/ui/index.ts|index.js)');
        process.exit(1);
    }
    if (WATCH) {
        for (const app of apps) {
            rmSync(app.outDir, { recursive: true, force: true });
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
