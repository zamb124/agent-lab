import '@platform/lib/components/app-loader.js';
import {
  expect,
  fixture,
  html,
  setupPlatformServices,
  teardownPlatformServices,
} from './helpers/index.js';

describe('import maps @platform', () => {
  beforeEach(async () => {
    await setupPlatformServices('');
  });

  afterEach(() => {
    teardownPlatformServices();
  });

  it('рендерит app-loader с PlatformElement', async () => {
    const el = await fixture(html`<app-loader></app-loader>`);
    expect(el.shadowRoot).to.be.ok;
  });
});
