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

function buildHumanitecProviderRequest(params: HumanitecLlmSetupParams): UpdateCustomProviderRequest {
  return {
    engine: 'openai_compatible',
    display_name: 'Humanitec',
    api_url: params.apiBaseUrl,
    api_key: params.deviceToken,
    models: [params.modelId],
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
  const providerRequest = buildHumanitecProviderRequest(params);
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
