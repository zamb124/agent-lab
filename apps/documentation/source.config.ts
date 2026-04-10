import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, defineDocs } from 'fumadocs-mdx/config';
import { metaSchema, pageSchema } from 'fumadocs-core/source/schema';

const here = path.dirname(fileURLToPath(import.meta.url));

export const docs = defineDocs({
  dir: path.join(here, '../../docs'),
  docs: {
    schema: pageSchema,
    files: [
      'index.mdx',
      'guides/**/*.mdx',
      'guides/**/*.md',
      'scenarios/**/index.mdx',
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
