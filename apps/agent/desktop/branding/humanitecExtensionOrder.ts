const PLATFORM_MCP_EXTENSION_ID = 'platform_mcp';

export type HumanitecBundledExtensionRef = {
  id: string;
  humanitec_primary?: boolean;
  priority?: number;
};

export function reorderHumanitecBundledExtensions<T extends HumanitecBundledExtensionRef>(
  extensions: T[],
): T[] {
  const primary: T[] = [];
  const rest: T[] = [];
  for (const extension of extensions) {
    if (extension.id === PLATFORM_MCP_EXTENSION_ID || extension.humanitec_primary === true) {
      primary.push(extension);
      continue;
    }
    rest.push(extension);
  }
  return [...primary, ...rest];
}

export function humanitecExtensionDisplayRank(extensionId: string): number {
  if (extensionId === PLATFORM_MCP_EXTENSION_ID) {
    return 0;
  }
  return 1;
}

export const HUMANITEC_PLATFORM_MCP_DISPLAY_NAME = 'Humanitec';
