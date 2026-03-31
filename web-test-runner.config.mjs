import { importMapsPlugin } from '@web/dev-server-import-maps';
import { playwrightLauncher } from '@web/test-runner-playwright';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const rootDir = path.dirname(fileURLToPath(import.meta.url));

export default {
  rootDir,
  files: 'tests/ui_components/**/*.test.js',
  nodeResolve: true,
  plugins: [
    importMapsPlugin({
      inject: {
        importMap: {
          imports: {
            '@platform/lib/': '/core/frontend/static/lib/',
            '@platform/services/': '/core/frontend/static/services/',
            '@capacitor/app': '/core/frontend/static/assets/js/vendor/@capacitor/app/index.js',
            '@capacitor/core': '/core/frontend/static/assets/js/vendor/@capacitor/core/index.js',
          },
        },
      },
    }),
  ],
  browsers: [
    playwrightLauncher({
      launchOptions: { headless: true },
      product: 'chromium',
    }),
  ],
};
