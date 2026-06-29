import { useCallback, useEffect, useState } from 'react';
import { Button } from './components/ui/button';
import { defineMessages, useIntl } from './i18n';
import { ensureHumanitecLlmConfigured } from './humanitecLlmSetup';

const i18n = defineMessages({
  title: {
    id: 'humanitecOnboarding.title',
    defaultMessage: 'Connect HumanitecAgent to platform',
  },
  description: {
    id: 'humanitecOnboarding.description',
    defaultMessage:
      'Enter the 6-digit pairing code from platform Settings → HumanitecAgent, or open Settings to generate one.',
  },
  pairingCodePlaceholder: {
    id: 'humanitecOnboarding.pairingCodePlaceholder',
    defaultMessage: '000000',
  },
  pairButton: {
    id: 'humanitecOnboarding.pairButton',
    defaultMessage: 'Pair device',
  },
  openSettings: {
    id: 'humanitecOnboarding.openSettings',
    defaultMessage: 'Open platform Settings',
  },
  pairingInProgress: {
    id: 'humanitecOnboarding.pairingInProgress',
    defaultMessage: 'Pairing…',
  },
  invalidCode: {
    id: 'humanitecOnboarding.invalidCode',
    defaultMessage: 'Pairing code must be 6 digits',
  },
  llmSetupInProgress: {
    id: 'humanitecOnboarding.llmSetupInProgress',
    defaultMessage: 'Configuring Platform Brain…',
  },
  llmSetupFailed: {
    id: 'humanitecOnboarding.llmSetupFailed',
    defaultMessage: 'Failed to configure platform LLM',
  },
});

type HumanitecAgentCredentialsPayload = {
  device_id: string;
  token: string;
  llm_api_base_url: string;
  llm_provider_id: string;
  llm_model_id: string;
};

type HumanitecAgentApi = {
  status: () => Promise<{ paired: boolean; credentials: HumanitecAgentCredentialsPayload | null }>;
  pair: (pairingCode: string) => Promise<unknown>;
  openSettings: () => Promise<void>;
  distro: () => Promise<{ display_name: string; primary_color: string } | null>;
  resyncExtensions: () => Promise<void>;
};

function resolveHumanitecAgentApi(): HumanitecAgentApi | null {
  const api = (window as Window & { humanitecAgent?: HumanitecAgentApi }).humanitecAgent;
  if (!api) {
    return null;
  }
  return api;
}

interface HumanitecPairingStepProps {
  onPaired: () => void;
}

function HumanitecPairingStep({ onPaired }: HumanitecPairingStepProps) {
  const intl = useIntl();
  const [displayName, setDisplayName] = useState('HumanitecAgent');
  const [primaryColor, setPrimaryColor] = useState('#0066FF');
  const [pairingCode, setPairingCode] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isPairing, setIsPairing] = useState(false);
  const [settingsOpened, setSettingsOpened] = useState(false);

  const agentApi = resolveHumanitecAgentApi();
  if (agentApi === null) {
    throw new Error('humanitecAgent preload API missing');
  }

  useEffect(() => {
    void agentApi.distro().then((distro) => {
      if (distro === null) {
        return;
      }
      setDisplayName(distro.display_name);
      setPrimaryColor(distro.primary_color);
    });
  }, [agentApi]);

  useEffect(() => {
    if (settingsOpened) {
      return;
    }
    setSettingsOpened(true);
    void agentApi.openSettings();
  }, [agentApi, settingsOpened]);

  const handlePair = useCallback(async () => {
    const normalizedCode = pairingCode.trim();
    if (normalizedCode.length !== 6 || !/^\d+$/.test(normalizedCode)) {
      setErrorMessage(intl.formatMessage(i18n.invalidCode));
      return;
    }
    setErrorMessage(null);
    setIsPairing(true);
    try {
      await agentApi.pair(normalizedCode);
      onPaired();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setIsPairing(false);
    }
  }, [agentApi, intl, onPaired, pairingCode]);

  return (
    <div className="h-screen w-full bg-background-default flex flex-col items-center justify-center p-4">
      <div className="max-w-md w-full">
        <div
          className="mb-6 inline-flex size-12 items-center justify-center rounded-xl text-lg font-semibold text-white"
          style={{ backgroundColor: primaryColor }}
        >
          H
        </div>
        <h1 className="text-2xl sm:text-3xl font-light mb-2">{displayName}</h1>
        <h2 className="text-lg font-light mb-3">{intl.formatMessage(i18n.title)}</h2>
        <p className="text-text-muted mb-6">{intl.formatMessage(i18n.description)}</p>
        <input
          id="pairing-code"
          data-humanitec-pairing-code
          className="w-full mb-3 rounded-lg border border-border-default bg-background-secondary px-4 py-3 text-2xl tracking-[0.3em] text-center"
          maxLength={6}
          inputMode="numeric"
          autoComplete="one-time-code"
          placeholder={intl.formatMessage(i18n.pairingCodePlaceholder)}
          value={pairingCode}
          onChange={(event) => setPairingCode(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              void handlePair();
            }
          }}
        />
        {errorMessage !== null ? (
          <p className="text-red-500 mb-3 text-sm">{errorMessage}</p>
        ) : null}
        <div className="flex flex-col gap-2">
          <Button
            data-humanitec-pair-submit
            disabled={isPairing}
            onClick={() => {
              void handlePair();
            }}
          >
            {isPairing ? intl.formatMessage(i18n.pairingInProgress) : intl.formatMessage(i18n.pairButton)}
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              void agentApi.openSettings();
            }}
          >
            {intl.formatMessage(i18n.openSettings)}
          </Button>
        </div>
      </div>
    </div>
  );
}

interface HumanitecOnboardingGuardProps {
  children: React.ReactNode;
}

export default function HumanitecOnboardingGuard({ children }: HumanitecOnboardingGuardProps) {
  const intl = useIntl();
  const [phase, setPhase] = useState<'checking' | 'pairing' | 'llm_setup' | 'ready'>('checking');
  const [llmSetupError, setLlmSetupError] = useState<string | null>(null);
  const [credentials, setCredentials] = useState<HumanitecAgentCredentialsPayload | null>(null);

  const runLlmSetup = useCallback(async (nextCredentials: HumanitecAgentCredentialsPayload) => {
    setPhase('llm_setup');
    setLlmSetupError(null);
    try {
      await ensureHumanitecLlmConfigured({
        apiBaseUrl: nextCredentials.llm_api_base_url,
        deviceToken: nextCredentials.token,
        providerId: nextCredentials.llm_provider_id,
        modelId: nextCredentials.llm_model_id,
      });
      const agentApi = resolveHumanitecAgentApi();
      if (agentApi !== null) {
        await agentApi.resyncExtensions();
      }
      setPhase('ready');
    } catch (error) {
      setLlmSetupError(error instanceof Error ? error.message : String(error));
    }
  }, []);

  const refreshStatus = useCallback(async () => {
    const agentApi = resolveHumanitecAgentApi();
    if (agentApi === null) {
      setPhase('ready');
      return;
    }
    const status = await agentApi.status();
    if (!status.paired || status.credentials === null) {
      setPhase('pairing');
      return;
    }
    setCredentials(status.credentials);
    await runLlmSetup(status.credentials);
  }, [runLlmSetup]);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  if (phase === 'checking') {
    return null;
  }

  if (phase === 'pairing') {
    return (
      <HumanitecPairingStep
        onPaired={() => {
          void refreshStatus();
        }}
      />
    );
  }

  if (phase === 'llm_setup') {
    if (llmSetupError !== null) {
      return (
        <div className="h-screen w-full bg-background-default flex flex-col items-center justify-center p-4">
          <p className="text-red-500 mb-4">{intl.formatMessage(i18n.llmSetupFailed)}: {llmSetupError}</p>
          {credentials !== null ? (
            <Button
              onClick={() => {
                void runLlmSetup(credentials);
              }}
            >
              Retry
            </Button>
          ) : null}
        </div>
      );
    }
    return (
      <div className="h-screen w-full bg-background-default flex flex-col items-center justify-center p-4">
        <p className="text-text-muted">{intl.formatMessage(i18n.llmSetupInProgress)}</p>
      </div>
    );
  }

  return <>{children}</>;
}
