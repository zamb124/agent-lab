import { FLOW_UI_CATALOG_MANIFEST } from './manifest.js';
import { registerFlowUIComponent, flowUIComponentRenderer } from './registry.js';
import { registerBasicCatalog } from './basic/register.js';
import { registerPlatformCatalog } from './platform/register.js';

let registered = false;

export function ensureFlowUICatalogRegistered() {
    if (registered) return;
    registerBasicCatalog(registerFlowUIComponent);
    registerPlatformCatalog(registerFlowUIComponent);
    const missing = Object.keys(FLOW_UI_CATALOG_MANIFEST.components)
        .filter((type) => !flowUIComponentRenderer(type));
    if (missing.length > 0) {
        throw new Error(`flow-ui: catalog renderers missing for ${missing.join(', ')}`);
    }
    registered = true;
}
