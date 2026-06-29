import type { ExtensionConfig } from './api/types.gen';

type HumanitecAgentEnvApi = {
  resolveEnvTemplates: (templates: string[]) => Promise<string[]>;
};

type StreamableExtensionEntry = ExtensionConfig & {
  uri?: string;
  headers?: { [key: string]: string };
};

function humanitecAgentEnvApi(): HumanitecAgentEnvApi | null {
  const api = (window as Window & { humanitecAgent?: HumanitecAgentEnvApi }).humanitecAgent;
  if (api === undefined || typeof api.resolveEnvTemplates !== 'function') {
    return null;
  }
  return api;
}

export function extensionConfigHasUnresolvedEnvTemplates(
  uri: string | undefined,
  headers: Record<string, string> | undefined,
): boolean {
  if (typeof uri === 'string' && uri.includes('${')) {
    return true;
  }
  if (headers === undefined) {
    return false;
  }
  return Object.values(headers).some((headerValue) => headerValue.includes('${'));
}

export function bundledStreamableHttpNeedsResync(
  existingExt: StreamableExtensionEntry,
  bundledUri: string | undefined,
  bundledHeaders: Record<string, string> | undefined,
): boolean {
  if (existingExt.type !== 'streamable_http') {
    return false;
  }
  if (extensionConfigHasUnresolvedEnvTemplates(existingExt.uri, existingExt.headers)) {
    return true;
  }
  if (!extensionConfigHasUnresolvedEnvTemplates(bundledUri, bundledHeaders)) {
    return false;
  }
  return extensionConfigHasUnresolvedEnvTemplates(existingExt.uri, existingExt.headers);
}

export async function resolveStreamableHttpBundledConfig(
  uri: string,
  headers: Record<string, string> | undefined,
): Promise<{ uri: string; headers: Record<string, string> | undefined }> {
  if (!extensionConfigHasUnresolvedEnvTemplates(uri, headers)) {
    return { uri, headers };
  }
  const api = humanitecAgentEnvApi();
  if (api === null) {
    return { uri, headers };
  }
  const headerKeys: string[] = [];
  const templates: string[] = [uri];
  if (headers !== undefined) {
    for (const [headerKey, headerValue] of Object.entries(headers)) {
      headerKeys.push(headerKey);
      templates.push(headerValue);
    }
  }
  const resolvedTemplates = await api.resolveEnvTemplates(templates);
  const resolvedUri = resolvedTemplates[0];
  if (typeof resolvedUri !== 'string' || !resolvedUri.trim()) {
    throw new Error('resolved platform MCP uri is empty');
  }
  if (headers === undefined) {
    return { uri: resolvedUri, headers: undefined };
  }
  const resolvedHeaders: Record<string, string> = {};
  for (let index = 0; index < headerKeys.length; index += 1) {
    const headerKey = headerKeys[index];
    const resolvedHeader = resolvedTemplates[index + 1];
    if (typeof resolvedHeader !== 'string' || !resolvedHeader.trim()) {
      throw new Error(`resolved header ${headerKey} is empty`);
    }
    resolvedHeaders[headerKey] = resolvedHeader;
  }
  return { uri: resolvedUri, headers: resolvedHeaders };
}
