import { app, BrowserWindow, ipcMain, shell } from 'electron';
import os from 'node:os';
import path from 'node:path';
import { randomUUID } from 'node:crypto';

import { loadHumanitecDistroDefaults } from './humanitecDistro';
import {
  clearHumanitecAgentCredentials,
  loadHumanitecAgentCredentials,
  saveHumanitecAgentCredentials,
  type HumanitecAgentCredentials,
} from './humanitecAgentStore';
import { HumanitecTunnelClient } from './humanitecTunnelClient';

type AgentLlmBundlePayload = {
  provider_id: string;
  model_id: string;
  api_base_url: string;
};

type DeviceRegisterResponsePayload = {
  device_id: string;
  token: string;
  platform_mcp_url: string;
  frontend_base_url: string;
  tunnel_ws_url: string;
  company_id: string;
  company_subdomain: string | null;
  llm: AgentLlmBundlePayload;
};

const DEV_PROBE_ORIGINS = [
  'http://system.lvh.me:8002',
  'http://system.lvh.me:9004',
];

let tunnelClient: HumanitecTunnelClient | null = null;
let pairingWindow: BrowserWindow | null = null;
let runtimeInitialized = false;
let devProbeFrontendBaseUrl: string | null = null;

function devProbeEnabled(): boolean {
  if (process.env.HUMANITEC_DEV_PROBE === '1') {
    return true;
  }
  return process.env.NODE_ENV === 'development';
}

async function probeDevFrontendBaseUrl(): Promise<string | null> {
  if (!devProbeEnabled()) {
    return null;
  }
  for (const origin of DEV_PROBE_ORIGINS) {
    const discoverUrl = `${origin}/frontend/api/agent/discover?origin=${encodeURIComponent(origin)}`;
    try {
      const response = await fetch(discoverUrl);
      if (!response.ok) {
        continue;
      }
      const body = (await response.json()) as { frontend_base_url?: string };
      if (typeof body.frontend_base_url === 'string' && body.frontend_base_url) {
        return body.frontend_base_url.replace(/\/+$/, '');
      }
    } catch {
      continue;
    }
  }
  return null;
}

function resolveFrontendBaseUrl(): string {
  const envBase = process.env.HUMANITEC_FRONTEND_BASE_URL;
  if (typeof envBase === 'string' && envBase.trim()) {
    return envBase.trim().replace(/\/+$/, '');
  }
  const credentials = loadHumanitecAgentCredentials(app.getPath('userData'));
  if (credentials !== null && credentials.frontend_base_url) {
    return credentials.frontend_base_url;
  }
  if (devProbeFrontendBaseUrl !== null) {
    return devProbeFrontendBaseUrl;
  }
  const defaults = loadHumanitecDistroDefaults();
  if (defaults !== null && defaults.default_frontend_base_url) {
    return defaults.default_frontend_base_url.replace(/\/+$/, '');
  }
  throw new Error('frontend base URL is not configured');
}

function credentialsFromRegisterBody(body: DeviceRegisterResponsePayload): HumanitecAgentCredentials {
  if (typeof body.llm !== 'object' || body.llm === null) {
    throw new Error('register response missing llm bundle');
  }
  if (typeof body.llm.api_base_url !== 'string' || !body.llm.api_base_url) {
    throw new Error('register response llm.api_base_url is required');
  }
  if (typeof body.llm.provider_id !== 'string' || !body.llm.provider_id) {
    throw new Error('register response llm.provider_id is required');
  }
  if (typeof body.llm.model_id !== 'string' || !body.llm.model_id) {
    throw new Error('register response llm.model_id is required');
  }
  return {
    device_id: body.device_id,
    token: body.token,
    frontend_base_url: body.frontend_base_url,
    tunnel_ws_url: body.tunnel_ws_url,
    platform_mcp_url: body.platform_mcp_url,
    company_id: body.company_id,
    company_subdomain: body.company_subdomain,
    llm_api_base_url: body.llm.api_base_url,
    llm_provider_id: body.llm.provider_id,
    llm_model_id: body.llm.model_id,
  };
}

function applyPlatformMcpEnv(credentials: HumanitecAgentCredentials): void {
  process.env.HUMANITEC_PLATFORM_MCP_URL = credentials.platform_mcp_url;
  process.env.HUMANITEC_DEVICE_TOKEN = credentials.token;
  notifyExtensionsResync();
  for (const window of BrowserWindow.getAllWindows()) {
    window.webContents.send('humanitec-agent:platform-mcp-env-updated', {
      platform_mcp_url: credentials.platform_mcp_url,
    });
  }
}

function notifyExtensionsResync(): void {
  for (const window of BrowserWindow.getAllWindows()) {
    window.webContents.send('humanitec-agent:extensions-resync');
  }
}

async function persistRegisteredDevice(body: DeviceRegisterResponsePayload): Promise<HumanitecAgentCredentials> {
  const credentials = credentialsFromRegisterBody(body);
  saveHumanitecAgentCredentials(app.getPath('userData'), credentials);
  applyPlatformMcpEnv(credentials);
  await startHumanitecTunnel(credentials);
  return credentials;
}

export async function discoverHumanitecAgent(
  originOverride?: string,
): Promise<Record<string, unknown>> {
  const frontendBase = resolveFrontendBaseUrl();
  const discoverUrl = new URL(`${frontendBase}/frontend/api/agent/discover`);
  if (originOverride) {
    discoverUrl.searchParams.set('origin', originOverride);
  }
  const response = await fetch(discoverUrl.toString());
  if (!response.ok) {
    throw new Error(`discover failed: HTTP ${response.status}`);
  }
  return (await response.json()) as Record<string, unknown>;
}

async function registerDevicePayload(
  pathSuffix: string,
  payload: Record<string, string>,
  sessionToken?: string,
): Promise<HumanitecAgentCredentials> {
  const frontendBase = resolveFrontendBaseUrl();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (sessionToken) {
    headers.Authorization = `Bearer ${sessionToken}`;
  }
  const response = await fetch(`${frontendBase}/frontend/api/agent/${pathSuffix}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`register failed: HTTP ${response.status} ${detail}`);
  }
  const body = (await response.json()) as DeviceRegisterResponsePayload;
  return persistRegisteredDevice(body);
}

export async function registerHumanitecDevice(pairingCode: string): Promise<HumanitecAgentCredentials> {
  const deviceId = randomUUID();
  const hostname = os.hostname();
  return registerDevicePayload('register', {
    pairing_code: pairingCode,
    device_id: deviceId,
    device_name: os.userInfo().username || hostname,
    os: process.platform,
    hostname,
  });
}

export async function registerHumanitecDeviceWithAuth(
  sessionToken: string,
): Promise<HumanitecAgentCredentials> {
  const deviceId = randomUUID();
  const hostname = os.hostname();
  return registerDevicePayload(
    'register-with-auth',
    {
      device_id: deviceId,
      device_name: os.userInfo().username || hostname,
      os: process.platform,
      hostname,
    },
    sessionToken,
  );
}

export async function startHumanitecTunnel(
  credentials?: HumanitecAgentCredentials,
): Promise<void> {
  const resolved =
    credentials ?? loadHumanitecAgentCredentials(app.getPath('userData'));
  if (resolved === null) {
    throw new Error('HumanitecAgent credentials missing');
  }
  if (tunnelClient !== null) {
    tunnelClient.disconnect();
    tunnelClient = null;
  }
  const userDataPath = app.getPath('userData');
  tunnelClient = new HumanitecTunnelClient({
    credentials: resolved,
    log: (message) => console.log(`[HumanitecAgent] ${message}`),
    onPolicy: (policy) => {
      console.log('[HumanitecAgent] tunnel policy', policy);
    },
    onDisconnected: (code, reason) => {
      console.log(`[HumanitecAgent] tunnel disconnected ${code} ${reason}`);
      if (code === 4401) {
        stopHumanitecTunnel();
        clearHumanitecAgentCredentials(userDataPath);
        delete process.env.HUMANITEC_PLATFORM_MCP_URL;
        delete process.env.HUMANITEC_DEVICE_TOKEN;
      }
    },
  });
  tunnelClient.connect();
}

export function stopHumanitecTunnel(): void {
  if (tunnelClient !== null) {
    tunnelClient.disconnect();
    tunnelClient = null;
  }
}

export function openHumanitecPairingWindow(): void {
  if (pairingWindow !== null && !pairingWindow.isDestroyed()) {
    pairingWindow.focus();
    return;
  }
  pairingWindow = new BrowserWindow({
    width: 420,
    height: 320,
    resizable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  pairingWindow.on('closed', () => {
    pairingWindow = null;
  });
  void pairingWindow.loadFile(path.join(__dirname, 'humanitec-pairing.html'));
}

export async function handleHumanitecDeepLink(url: string): Promise<boolean> {
  const defaults = loadHumanitecDistroDefaults();
  if (defaults === null) {
    return false;
  }
  const parsed = new URL(url);
  if (parsed.protocol !== `${defaults.protocol_scheme}:`) {
    return false;
  }

  if (parsed.hostname === defaults.auth_callback_path.split('/')[0]) {
    const sessionToken = parsed.searchParams.get('token');
    if (!sessionToken) {
      throw new Error('auth callback without token');
    }
    await registerHumanitecDeviceWithAuth(sessionToken);
    return true;
  }

  if (parsed.hostname === defaults.pairing_path) {
    const pairingCode = parsed.searchParams.get('code');
    if (!pairingCode) {
      openHumanitecPairingWindow();
      return true;
    }
    await registerHumanitecDevice(pairingCode);
    return true;
  }

  return false;
}

export async function initHumanitecAgentRuntime(): Promise<void> {
  if (runtimeInitialized) {
    return;
  }
  runtimeInitialized = true;

  const defaults = loadHumanitecDistroDefaults();
  if (defaults === null) {
    return;
  }

  if (devProbeEnabled()) {
    const probedBase = await probeDevFrontendBaseUrl();
    if (probedBase !== null) {
      devProbeFrontendBaseUrl = probedBase;
      const existingFrontendBase = process.env.HUMANITEC_FRONTEND_BASE_URL;
      if (typeof existingFrontendBase !== 'string' || !existingFrontendBase.trim()) {
        process.env.HUMANITEC_FRONTEND_BASE_URL = probedBase;
      }
    }
  }

  ipcMain.handle('humanitec-agent:discover', async (_event, originOverride?: string) => {
    return discoverHumanitecAgent(originOverride);
  });

  ipcMain.handle('humanitec-agent:pair', async (_event, pairingCode: string) => {
    return registerHumanitecDevice(pairingCode);
  });

  ipcMain.handle('humanitec-agent:status', async () => {
    const credentials = loadHumanitecAgentCredentials(app.getPath('userData'));
    return {
      paired: credentials !== null,
      credentials,
    };
  });

  ipcMain.handle('humanitec-agent:logout', async () => {
    stopHumanitecTunnel();
    clearHumanitecAgentCredentials(app.getPath('userData'));
    delete process.env.HUMANITEC_PLATFORM_MCP_URL;
    delete process.env.HUMANITEC_DEVICE_TOKEN;
  });

  ipcMain.handle('humanitec-agent:open-pairing', async () => {
    openHumanitecPairingWindow();
  });

  ipcMain.handle('humanitec-agent:extensions-resync', async () => {
    notifyExtensionsResync();
  });

  ipcMain.handle('humanitec-agent:distro', async () => {
    return loadHumanitecDistroDefaults();
  });

  ipcMain.handle('humanitec-agent:open-settings', async () => {
    const frontendBase = resolveFrontendBaseUrl();
    await shell.openExternal(`${frontendBase}/settings`);
  });

  const credentials = loadHumanitecAgentCredentials(app.getPath('userData'));
  if (credentials !== null) {
    applyPlatformMcpEnv(credentials);
    void startHumanitecTunnel(credentials);
  }
}
