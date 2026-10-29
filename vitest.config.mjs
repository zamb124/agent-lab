import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';
import { existsSync } from 'node:fs';
import path from 'node:path';

const rootDir = path.dirname(fileURLToPath(import.meta.url));

// Период миграции: `import './x.js'` указывает на `x.ts`. Свежий .js на диске
// выигрывает — иначе отдаём .ts-соседа.
const jsToTsSibling = {
    name: 'platform-js-to-ts-sibling',
    enforce: 'pre',
    resolveId(source, importer) {
        if (!source.endsWith('.js') || !importer) return null;
        const jsPath = source.startsWith('@platform/lib/')
            ? path.join(rootDir, 'core/frontend/static/lib', source.slice('@platform/lib/'.length))
            : path.resolve(path.dirname(importer), source);
        const tsPath = jsPath.slice(0, -'.js'.length) + '.ts';
        return existsSync(jsPath) || !existsSync(tsPath) ? null : tsPath;
    },
};

export default defineConfig({
    plugins: [jsToTsSibling],
    test: {
        include: ['tests/frontend_core/unit/**/*.spec.{js,ts}'],
        environment: 'node',
        globals: false,
        coverage: {
            provider: 'v8',
            reporter: ['text', 'lcov'],
            include: [
                'core/frontend/static/lib/events/**/*.{js,ts}',
                'core/frontend/static/lib/utils/platform-deeplink-paths.{js,ts}',
            ],
            exclude: [
                'core/frontend/static/lib/events/devtools.{js,ts}',
                'core/frontend/static/lib/events/factories/register.{js,ts}',
            ],
            // v8 считает исходные строки. Порог — пол текущего набора unit-тестов.
            thresholds: {
                lines: 81,
                branches: 70,
                functions: 75,
                statements: 79,
            },
        },
    },
    resolve: {
        alias: {
            '@platform/lib': path.resolve(rootDir, 'core/frontend/static/lib'),
        },
    },
});
