import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, defineDocs } from 'fumadocs-mdx/config';
import { metaSchema, pageSchema } from 'fumadocs-core/source/schema';

const here = path.dirname(fileURLToPath(import.meta.url));
// Скомпилированный конфиг кладётся в `.source/`; оттуда на корень репозитория — на один уровень выше.
const docsRoot =
  path.basename(here) === '.source'
    ? path.join(here, '../../../docs')
    : path.join(here, '../../docs');

export const docs = defineDocs({
  dir: docsRoot,
  docs: {
    schema: pageSchema,
    files: [
      'index.mdx',
      'guides/**/*.mdx',
      'guides/**/*.md',
      'scenarios/**/*.mdx',
    ],
    postprocess: {
      includeProcessedMarkdown: true,
    },
  },
  meta: {
    schema: metaSchema,
  },
});

export default defineConfig({
  mdxOptions: {},
});
