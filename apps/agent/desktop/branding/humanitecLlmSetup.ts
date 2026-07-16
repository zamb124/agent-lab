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
  /** Каталог моделей уже загружен в main process (без CORS с file://). */
  modelIds: string[];
};

async function buildHumanitecProviderRequest(
  params: HumanitecLlmSetupParams,
): Promise<UpdateCustomProviderRequest> {
  if (params.modelIds.length === 0) {
    throw new Error('Humanitec models catalog is empty');
  }
  return {
    engine: 'openai_compatible',
    display_name: 'Linnex',
    api_url: params.apiBaseUrl,
    api_key: params.deviceToken,
    models: params.modelIds,
    supports_streaming: true,
    requires_auth: true,
    headers: {
      Authorization: `Bearer ${params.deviceToken}`,
    },
  };
}

function isPlatformLlmProviderDisplayName(displayName: string): boolean {
  // Legacy installs used "Humanitec"; current distro UI label is "Linnex".
  return displayName === 'Linnex' || displayName === 'Humanitec';
}

function isHumanitecProviderEntry(
  entry: { name: string; metadata: { display_name: string } },
  providerId: string,
): boolean {
  return (
    entry.name === providerId || isPlatformLlmProviderDisplayName(entry.metadata.display_name)
  );
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
  return isPlatformLlmProviderDisplayName(activeProvider.metadata.display_name);
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
