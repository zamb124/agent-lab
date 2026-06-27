import {
  acpCreateCustomProviderFromRequest,
  acpListProviderDetails,
  acpReadDefaults,
  acpSaveDefaults,
} from './acp/providers';

export type HumanitecLlmSetupParams = {
  apiBaseUrl: string;
  deviceToken: string;
  providerId: string;
  modelId: string;
};

export async function isHumanitecLlmConfigured(
  providerId: string,
  modelId: string,
): Promise<boolean> {
  const defaults = await acpReadDefaults();
  if (defaults.modelId !== modelId) {
    return false;
  }
  if (defaults.providerId === providerId) {
    return true;
  }
  if (defaults.providerId === null) {
    return false;
  }
  const providers = await acpListProviderDetails();
  const activeProvider = providers.find((entry) => entry.name === defaults.providerId);
  if (activeProvider === undefined) {
    return false;
  }
  return activeProvider.metadata.display_name === 'Humanitec';
}

export async function ensureHumanitecLlmConfigured(
  params: HumanitecLlmSetupParams,
): Promise<void> {
  const alreadyConfigured = await isHumanitecLlmConfigured(
    params.providerId,
    params.modelId,
  );
  if (alreadyConfigured) {
    return;
  }

  const providers = await acpListProviderDetails();
  const existingProvider = providers.find(
    (entry) => entry.name === params.providerId || entry.metadata.display_name === 'Humanitec',
  );
  let resolvedProviderId = params.providerId;
  if (existingProvider === undefined) {
    const created = await acpCreateCustomProviderFromRequest({
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
    });
    resolvedProviderId = created.provider_name;
  } else {
    resolvedProviderId = existingProvider.name;
  }

  await acpSaveDefaults(resolvedProviderId, params.modelId);
}
