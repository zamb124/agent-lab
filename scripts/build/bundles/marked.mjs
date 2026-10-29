import { build } from 'esbuild';

const ENTRY = `
export { Marked } from 'marked';
`;

await build({
    stdin: {
        contents: ENTRY,
        resolveDir: process.cwd(),
        sourcefile: 'marked-bundle-entry.js',
        loader: 'js',
    },
    outfile: 'core/frontend/static/assets/js/marked/marked.esm.min.js',
    bundle: true,
    format: 'esm',
    target: 'es2020',
    minify: true,
    sourcemap: false,
    legalComments: 'none',
});
