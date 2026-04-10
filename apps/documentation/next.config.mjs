import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createMDX } from 'fumadocs-mdx/next';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const withMDX = createMDX();

/** @type {import('next').NextConfig} */
const config = {
  output: 'export',
  basePath: '/documentation',
  trailingSlash: true,
  reactStrictMode: true,
  turbopack: {
    root: __dirname,
  },
};

export default withMDX(config);
