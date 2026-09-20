import { build } from 'esbuild';

const ENTRY = `
export { Centrifuge, UnauthorizedError } from 'centrifuge';
`;

await build({
    stdin: {
        contents: ENTRY,
        resolveDir: process.cwd(),
        sourcefile: 'centrifuge-bundle-entry.js',
        loader: 'js',
    },
    outfile: 'core/frontend/static/assets/js/centrifuge/centrifuge.esm.min.js',
    bundle: true,
    format: 'esm',
    target: 'es2020',
    minify: true,
    sourcemap: false,
    legalComments: 'none',
});
