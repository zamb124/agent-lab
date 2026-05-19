import { importMapsPlugin } from '@web/dev-server-import-maps';
import { playwrightLauncher } from '@web/test-runner-playwright';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { browserTestDevMiddleware } from './web-test-runner.middleware.mjs';

const rootDir = path.dirname(fileURLToPath(import.meta.url));
const pageNavigationTimeoutMs = 120_000;
const litDevModeMessage =
    'Lit is in dev mode. Not recommended for production! See https://lit.dev/msg/dev-mode for more information.';

export default {
    rootDir,
    files: ['tests/frontend_core/browser/**/*.spec.js'],
    hostname: '127.0.0.1',
    concurrentBrowsers: 1,
    concurrency: 1,
    browserStartTimeout: 120_000,
    testsStartTimeout: 60_000,
    middleware: [browserTestDevMiddleware],
    nodeResolve: true,
    filterBrowserLogs(log) {
        return !log.args.some((arg) => typeof arg === 'string' && arg.includes(litDevModeMessage));
    },
    plugins: [
        importMapsPlugin({
            inject: {
                importMap: {
                    imports: {
                        '@platform/lib/': '/core/frontend/static/lib/',
                        '@platform/services/': '/core/frontend/static/services/',
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
