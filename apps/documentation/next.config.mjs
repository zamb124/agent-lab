import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createMDX } from 'fumadocs-mdx/next';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const withMDX = createMDX();

/** Совпадает с монтированием FastAPI (`/documentation/`). Должен совпадать с `docPublicBasePath` в lib/shared.ts. */
const DOC_BASE_PATH = '/documentation';

/** @type {import('next').NextConfig} */
const config = {
  output: 'export',
  basePath: DOC_BASE_PATH,
  trailingSlash: true,
  reactStrictMode: true,
  // Иначе при `basePath` и статическом экспорте Bloom-filter иногда даёт ложное срабатывание
  // и клиентская навигация удваивает префикс (`/documentation/documentation/...`).
  experimental: {
    clientRouterFilter: false,
  },
  turbopack: {
    root: __dirname,
  },
};

export default withMDX(config);
