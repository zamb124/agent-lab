import { A2UI_EXTENSION_URI, LINNEX_CATALOG_ID } from './constants.js';

export function supportsLinnexFlowUI(agentCard) {
    const extensions = agentCard?.capabilities?.extensions;
    if (!Array.isArray(extensions)) return false;
    const extension = extensions.find((item) => item?.uri === A2UI_EXTENSION_URI);
    if (!extension) return false;
    const catalogs = extension.params?.supportedCatalogIds || extension.params?.supported_catalog_ids;
    return Array.isArray(catalogs) && catalogs.includes(LINNEX_CATALOG_ID);
}
