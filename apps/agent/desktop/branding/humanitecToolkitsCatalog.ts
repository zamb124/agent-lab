export type HumanitecToolkitCatalogItem = {
  toolkit_id: string;
  name: string;
  description: string;
  default_enabled: boolean;
  position: number;
  mcp_url: string;
};

export function platformToolkitExtensionId(toolkitId: string): string {
  return `platform_${toolkitId}`;
}

export function isPlatformToolkitExtensionId(extensionId: string): boolean {
  return extensionId.startsWith('platform_');
}

export function comparePlatformToolkitExtensions(
  leftId: string,
  rightId: string,
  positionById: ReadonlyMap<string, number>,
): number {
  const leftRank = positionById.get(leftId) ?? Number.MAX_SAFE_INTEGER;
  const rightRank = positionById.get(rightId) ?? Number.MAX_SAFE_INTEGER;
  if (leftRank !== rightRank) {
    return leftRank - rightRank;
  }
  return leftId.localeCompare(rightId);
}
