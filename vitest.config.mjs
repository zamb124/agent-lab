import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const rootDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
    test: {
        include: ['tests/frontend_core/unit/**/*.spec.js'],
        environment: 'node',
        globals: false,
        coverage: {
            provider: 'v8',
            reporter: ['text', 'lcov'],
            include: [
                'core/frontend/static/lib/events/**/*.js',
                'core/frontend/static/lib/utils/platform-deeplink-paths.js',
            ],
            exclude: [
                'core/frontend/static/lib/events/devtools.js',
                'core/frontend/static/lib/events/factories/register.js',
            ],
            thresholds: {
                lines: 85,
                branches: 70,
                functions: 75,
                statements: 85,
            },
        },
    },
    resolve: {
        alias: {
            '@platform/lib': path.resolve(rootDir, 'core/frontend/static/lib'),
            '@platform/services': path.resolve(rootDir, 'core/frontend/static/services'),
        },
    },
});
