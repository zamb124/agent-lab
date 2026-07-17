import {
  comparePlatformToolkitExtensions,
  isPlatformToolkitExtensionId,
  platformToolkitExtensionId,
} from './humanitecToolkitsCatalog';

const LEGACY_PLATFORM_MCP_EXTENSION_ID = 'platform_mcp';

export type HumanitecBundledExtensionRef = {
  id: string;
  humanitec_primary?: boolean;
  priority?: number;
};

export function reorderHumanitecBundledExtensions<T extends HumanitecBundledExtensionRef>(
  extensions: T[],
): T[] {
  const platformToolkits: T[] = [];
  const rest: T[] = [];
  for (const extension of extensions) {
    if (
      extension.id === LEGACY_PLATFORM_MCP_EXTENSION_ID ||
      extension.humanitec_primary === true ||
      isPlatformToolkitExtensionId(extension.id)
    ) {
      platformToolkits.push(extension);
      continue;
    }
    rest.push(extension);
  }
  return [...platformToolkits, ...rest];
}

export function humanitecExtensionDisplayRank(extensionId: string): number {
  if (extensionId === LEGACY_PLATFORM_MCP_EXTENSION_ID || isPlatformToolkitExtensionId(extensionId)) {
    return 0;
  }
  return 1;
}

export function humanitecExtensionSortKey(
  extensionId: string,
  positionById: ReadonlyMap<string, number>,
): number {
  if (!isPlatformToolkitExtensionId(extensionId)) {
    return Number.MAX_SAFE_INTEGER;
  }
  return positionById.get(extensionId) ?? Number.MAX_SAFE_INTEGER;
}

export { comparePlatformToolkitExtensions, platformToolkitExtensionId };

export const HUMANITEC_PLATFORM_MCP_DISPLAY_NAME = 'Linnex';
