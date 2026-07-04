import type { ExtensionConfig } from './api/types.gen';
import { FixedExtensionEntry } from './components/ConfigContext';
import {
  comparePlatformToolkitExtensions,
  HumanitecToolkitCatalogItem,
  isPlatformToolkitExtensionId,
  platformToolkitExtensionId,
} from './humanitecToolkitsCatalog';
import { nameToKey } from './components/settings/extensions/utils';

type HumanitecAgentToolkitsApi = {
  fetchToolkitsCatalog: () => Promise<HumanitecToolkitCatalogItem[]>;
  resolveEnvTemplates: (templates: string[]) => Promise<string[]>;
};

function humanitecAgentToolkitsApi(): HumanitecAgentToolkitsApi | null {
  const api = (
    window as Window & {
      humanitecAgent?: HumanitecAgentToolkitsApi;
    }
  ).humanitecAgent;
  if (api === undefined || typeof api.fetchToolkitsCatalog !== 'function') {
    return null;
  }
  if (typeof api.resolveEnvTemplates !== 'function') {
    return null;
  }
  return api;
}

function platformToolkitHeadersTemplate(): Record<string, string> {
  return {
    Authorization: 'Bearer ${HUMANITEC_DEVICE_TOKEN}',
  };
}

async function resolvePlatformToolkitHeaders(
  api: HumanitecAgentToolkitsApi,
): Promise<Record<string, string>> {
  const templates = platformToolkitHeadersTemplate();
  const headerKeys = Object.keys(templates);
  const resolvedValues = await api.resolveEnvTemplates(
    headerKeys.map((headerKey) => templates[headerKey]),
  );
  const resolvedHeaders: Record<string, string> = {};
  for (let index = 0; index < headerKeys.length; index += 1) {
    const headerKey = headerKeys[index];
    const resolvedHeader = resolvedValues[index];
    if (typeof resolvedHeader !== 'string' || !resolvedHeader.trim()) {
      throw new Error(`resolved header ${headerKey} is empty`);
    }
    resolvedHeaders[headerKey] = resolvedHeader;
  }
  return resolvedHeaders;
}

function platformToolkitNeedsResync(
  existingExt: FixedExtensionEntry,
  catalogItem: HumanitecToolkitCatalogItem,
): boolean {
  if (existingExt.type !== 'streamable_http') {
    return true;
  }
  if (existingExt.uri !== catalogItem.mcp_url) {
    return true;
  }
  if (existingExt.display_name !== catalogItem.name) {
    return true;
  }
  if (existingExt.description !== catalogItem.description) {
    return true;
  }
  return false;
}

export async function syncPlatformToolkitExtensions(
  existingExtensions: FixedExtensionEntry[],
  addExtensionFn: (name: string, config: ExtensionConfig, enabled: boolean) => Promise<void>,
  removeExtensionFn: (configKey: string) => Promise<void>,
): Promise<void> {
  const api = humanitecAgentToolkitsApi();
  if (api === null) {
    return;
  }

  let catalog: HumanitecToolkitCatalogItem[];
  try {
    catalog = await api.fetchToolkitsCatalog();
  } catch (error) {
    console.error('Failed to fetch Humanitec toolkits catalog:', error);
    return;
  }

  const catalogExtensionIds = new Set(
    catalog.map((catalogItem) => platformToolkitExtensionId(catalogItem.toolkit_id)),
  );

  for (const existingExt of existingExtensions) {
    const extensionId = nameToKey(existingExt.name);
    if (!isPlatformToolkitExtensionId(extensionId)) {
      continue;
    }
    if (catalogExtensionIds.has(extensionId)) {
      continue;
    }
    await removeExtensionFn(extensionId);
  }

  const sortedCatalog = [...catalog].sort((left, right) =>
    comparePlatformToolkitExtensions(
      platformToolkitExtensionId(left.toolkit_id),
      platformToolkitExtensionId(right.toolkit_id),
      new Map(
        catalog.map((catalogItem) => [
          platformToolkitExtensionId(catalogItem.toolkit_id),
          catalogItem.position,
        ]),
      ),
    ),
  );

  const resolvedHeaders = await resolvePlatformToolkitHeaders(api);

  for (const catalogItem of sortedCatalog) {
    const extensionId = platformToolkitExtensionId(catalogItem.toolkit_id);
    const existingExt = existingExtensions.find((ext) => nameToKey(ext.name) === extensionId);
    const needsResync =
      existingExt !== undefined && platformToolkitNeedsResync(existingExt, catalogItem);
    if (existingExt !== undefined && !needsResync) {
      continue;
    }
    if (needsResync) {
      await removeExtensionFn(extensionId);
    }

    const extConfig: ExtensionConfig = {
      type: 'streamable_http',
      name: extensionId,
      display_name: catalogItem.name,
      description: catalogItem.description,
      timeout: 300,
      uri: catalogItem.mcp_url,
      headers: resolvedHeaders,
      bundled: true,
    };
    const enabled = existingExt ? existingExt.enabled : catalogItem.default_enabled;
    await addExtensionFn(extensionId, extConfig, enabled);
  }
}

export function humanitecPlatformExtensionDisplayRank(extensionId: string): number {
  if (isPlatformToolkitExtensionId(extensionId)) {
    return 0;
  }
  return 1;
}
