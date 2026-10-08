import { existsSync } from 'node:fs';
import { importMapsPlugin } from '@web/dev-server-import-maps';
import { esbuildPlugin } from '@web/dev-server-esbuild';
import { nodeResolvePlugin } from '@web/dev-server';
import { playwrightLauncher } from '@web/test-runner-playwright';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { browserTestDevMiddleware } from './web-test-runner.middleware.mjs';

const rootDir = path.dirname(fileURLToPath(import.meta.url));
const pageNavigationTimeoutMs = 120_000;
const litDevModeMessage =
    'Lit is in dev mode. Not recommended for production! See https://lit.dev/msg/dev-mode for more information.';

// Период миграции: спецификатор `./foo.js`, когда на диске только `foo.ts`.
// .js на диске выигрывает — свежий источник не подменяется.
// Отдача .ts-контента под .js URL — единое URL-пространство: иначе resolveImport
// esbuild-плагина внутри .ts переписывает specifier на .ts, и один модуль грузится
// под двум URL (.js и .ts) — двойная регистрация customElements.
const tsSiblingMiddleware = async (ctx, next) => {
    const urlPath = decodeURIComponent(ctx.path);
    if (urlPath.endsWith('.js')) {
        const fsPath = path.join(rootDir, urlPath);
        const tsPath = fsPath.slice(0, -'.js'.length) + '.ts';
        if (!existsSync(fsPath) && existsSync(tsPath)) {
            ctx.path = urlPath.slice(0, -'.js'.length) + '.ts';
        }
    }
    return next();
};

// Симметрично middleware: гасим resolveImport плагина, который в .ts-файлах
// переписывает specifier `./x.js` → `./x.ts` — см. tsSiblingMiddleware.
const tsEsbuildPlugin = esbuildPlugin({ ts: true });
tsEsbuildPlugin.resolveImport = undefined;

// node-resolve с .ts в extensions тоже переписывает specifier `./x.js` → `./x.ts`
// для отсутствующего на диске .js — оборачиваем и возвращаем исходный specifier.
const tsNodeResolvePlugin = nodeResolvePlugin(rootDir, false);
const resolveImportOriginal = tsNodeResolvePlugin.resolveImport;
tsNodeResolvePlugin.resolveImport = async (args) => {
    const resolved = await resolveImportOriginal(args);
    if (
        typeof resolved === 'string'
        && args.source.endsWith('.js')
        && args.source.startsWith('.')
        && resolved.endsWith('.ts')
    ) {
        return args.source;
    }
    return resolved;
};

export default {
    rootDir,
    files: [
        'tests/frontend_core/browser/**/*.spec.{js,ts}',
        'tests/ui/design-system/components/**/contract.spec.{js,ts}',
        'tests/ui/design-system/flows/**/*.spec.{js,ts}',
    ],
    hostname: '127.0.0.1',
    concurrentBrowsers: 1,
    // Test files run in isolated pages. A single-page queue no longer fits the
    // suite-wide timeout as the browser suite grows, while a small bounded
    // parallelism keeps local/CI resource usage predictable.
    concurrency: 4,
    browserStartTimeout: 120_000,
    testsStartTimeout: 60_000,
    middleware: [tsSiblingMiddleware, browserTestDevMiddleware],
    nodeResolve: false,
    filterBrowserLogs(log) {
        return !log.args.some((arg) => typeof arg === 'string' && arg.includes(litDevModeMessage));
    },
    plugins: [
        tsEsbuildPlugin,
        importMapsPlugin({
            inject: {
                importMap: {
                    imports: {
                        'lit': '/core/frontend/static/assets/js/lit/lit.min.js',
                        'lit/directives/class-map.js':
                            '/core/frontend/static/assets/js/lit/directives/class-map.min.js',
                        'lit/directives/repeat.js':
                            '/core/frontend/static/assets/js/lit/directives/repeat.min.js',
                        'lit/directives/unsafe-html.js':
                            '/core/frontend/static/assets/js/lit/directives/unsafe-html.min.js',
                        'lit/directives/when.js': '/core/frontend/static/assets/js/lit/directives/when.min.js',
                        'lit/directives/guard.js': '/core/frontend/static/assets/js/lit/directives/guard.min.js',
                        '@platform/lib/': '/core/frontend/static/lib/',
                        'centrifuge': '/core/frontend/static/assets/js/centrifuge/centrifuge.esm.min.js',
                        'marked': '/core/frontend/static/assets/js/marked/marked.esm.min.js',
                        '@capacitor/app': '/core/frontend/static/assets/js/vendor/@capacitor/app/index.js',
                        '@capacitor/core': '/core/frontend/static/assets/js/vendor/@capacitor/core/index.js',
                        '@capacitor/splash-screen': '/core/frontend/static/assets/js/vendor/@capacitor/splash-screen/index.js',
                        '@capacitor/push-notifications':
                            '/core/frontend/static/assets/js/vendor/@capacitor/push-notifications/index.js',
                    },
                },
            },
        }),
        tsNodeResolvePlugin,
    ],
    browsers: [
        playwrightLauncher({
            launchOptions: { headless: true },
            product: 'chromium',
            createPage: async ({ context }) => {
                const page = await context.newPage();
                page.setDefaultTimeout(pageNavigationTimeoutMs);
                page.setDefaultNavigationTimeout(pageNavigationTimeoutMs);
                return page;
            },
        }),
    ],
};
