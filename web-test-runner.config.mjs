import { existsSync } from 'node:fs';
import { importMapsPlugin } from '@web/dev-server-import-maps';
import { esbuildPlugin } from '@web/dev-server-esbuild';
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
    nodeResolve: true,
    filterBrowserLogs(log) {
        return !log.args.some((arg) => typeof arg === 'string' && arg.includes(litDevModeMessage));
    },
    plugins: [
        esbuildPlugin({ ts: true }),
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
