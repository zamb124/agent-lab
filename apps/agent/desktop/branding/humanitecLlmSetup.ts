import {
  acpCreateCustomProviderFromRequest,
  acpListProviderDetails,
  acpReadDefaults,
  acpSaveDefaults,
  acpUpdateCustomProviderFromRequest,
} from './acp/providers';
import type { UpdateCustomProviderRequest } from './api';

export type HumanitecLlmSetupParams = {
  apiBaseUrl: string;
  deviceToken: string;
  providerId: string;
  modelId: string;
};

type AgentOpenAIModelsResponse = {
  data: Array<{ id: string }>;
};

async function fetchHumanitecLlmModelIds(params: HumanitecLlmSetupParams): Promise<string[]> {
  const modelsUrl = `${params.apiBaseUrl.replace(/\/+$/, '')}/models`;
  const response = await fetch(modelsUrl, {
    headers: {
      Authorization: `Bearer ${params.deviceToken}`,
    },
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Humanitec models fetch failed: HTTP ${response.status} ${detail}`);
  }
  const body = (await response.json()) as AgentOpenAIModelsResponse;
  if (!Array.isArray(body.data)) {
    throw new Error('Humanitec models response missing data');
  }
  const modelIds: string[] = [];
  const seenModelIds = new Set<string>();
  for (const item of body.data) {
    if (typeof item.id !== 'string' || !item.id.trim()) {
      continue;
    }
    const normalizedModelId = item.id.trim();
    if (seenModelIds.has(normalizedModelId)) {
      continue;
    }
    seenModelIds.add(normalizedModelId);
    modelIds.push(normalizedModelId);
  }
  if (modelIds.length === 0) {
    throw new Error('Humanitec models catalog is empty');
  }
  return modelIds;
}

async function buildHumanitecProviderRequest(
  params: HumanitecLlmSetupParams,
): Promise<UpdateCustomProviderRequest> {
  const modelIds = await fetchHumanitecLlmModelIds(params);
  return {
    engine: 'openai_compatible',
    display_name: 'Humanitec',
    api_url: params.apiBaseUrl,
    api_key: params.deviceToken,
    models: modelIds,
    supports_streaming: true,
    requires_auth: true,
    headers: {
      Authorization: `Bearer ${params.deviceToken}`,
    },
  };
}

function isHumanitecProviderEntry(
  entry: { name: string; metadata: { display_name: string } },
  providerId: string,
): boolean {
  return entry.name === providerId || entry.metadata.display_name === 'Humanitec';
}

export async function isHumanitecLlmConfigured(
  providerId: string,
  modelId: string,
): Promise<boolean> {
  const defaults = await acpReadDefaults();
  if (defaults.modelId !== modelId) {
    return false;
  }
  if (defaults.providerId === null) {
    return false;
  }

  const providers = await acpListProviderDetails();
  const activeProvider = providers.find((entry) => entry.name === defaults.providerId);
  if (activeProvider === undefined) {
    return false;
  }
  if (!activeProvider.is_configured) {
    return false;
  }
  if (defaults.providerId === providerId) {
    return true;
  }
  return activeProvider.metadata.display_name === 'Humanitec';
}

export async function ensureHumanitecLlmConfigured(
  params: HumanitecLlmSetupParams,
): Promise<void> {
  const providerRequest = await buildHumanitecProviderRequest(params);
  const providers = await acpListProviderDetails();
  const existingProvider = providers.find((entry) =>
    isHumanitecProviderEntry(entry, params.providerId),
  );

  let resolvedProviderId = params.providerId;
  if (existingProvider === undefined) {
    const created = await acpCreateCustomProviderFromRequest(providerRequest);
    resolvedProviderId = created.provider_name;
  } else {
    resolvedProviderId = existingProvider.name;
    await acpUpdateCustomProviderFromRequest(resolvedProviderId, providerRequest);
  }

  await acpSaveDefaults(resolvedProviderId, params.modelId);
}
