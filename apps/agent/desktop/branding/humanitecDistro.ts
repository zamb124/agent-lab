import fs from 'node:fs';
import path from 'node:path';

export type HumanitecDistroDefaults = {
  id: string;
  display_name: string;
  bundle_name: string;
  protocol_scheme: string;
  auth_callback_path: string;
  pairing_path: string;
  primary_color: string;
  platform_mcp_path: string;
  default_frontend_base_url: string;
  default_extensions: string[];
};

const FRONTEND_BASE_URL_ARG_PREFIX = '--humanitec-frontend-base-url=';

export function applyHumanitecFrontendBaseUrlFromLaunchConfig(): void {
  for (const arg of process.argv) {
    if (!arg.startsWith(FRONTEND_BASE_URL_ARG_PREFIX)) {
      continue;
    }
    const configuredBase = arg.slice(FRONTEND_BASE_URL_ARG_PREFIX.length).trim();
    if (configuredBase) {
      process.env.HUMANITEC_FRONTEND_BASE_URL = configuredBase.replace(/\/+$/, '');
    }
    return;
  }
}

export function loadHumanitecDistroDefaults(): HumanitecDistroDefaults | null {
  const candidates = [
    path.join(process.resourcesPath, 'humanitec.defaults.json'),
    path.join(__dirname, '..', 'humanitec.defaults.json'),
  ];
  for (const candidatePath of candidates) {
    if (!fs.existsSync(candidatePath)) {
      continue;
    }
    const raw = fs.readFileSync(candidatePath, 'utf-8');
    return JSON.parse(raw) as HumanitecDistroDefaults;
  }
  return null;
}

export function applyHumanitecDistroEnv(): HumanitecDistroDefaults | null {
  applyHumanitecFrontendBaseUrlFromLaunchConfig();
  const defaults = loadHumanitecDistroDefaults();
  if (defaults === null) {
    return null;
  }
  process.env.GOOSE_BUNDLE_NAME = defaults.bundle_name;
  process.env.HUMANITEC_PLATFORM_MCP_PATH = defaults.platform_mcp_path;
  process.env.HUMANITEC_PROTOCOL_SCHEME = defaults.protocol_scheme;
  const existingFrontendBase = process.env.HUMANITEC_FRONTEND_BASE_URL;
  if (typeof existingFrontendBase !== 'string' || !existingFrontendBase.trim()) {
    process.env.HUMANITEC_FRONTEND_BASE_URL = defaults.default_frontend_base_url;
  }
  if (defaults.default_extensions.length > 0) {
    process.env.HUMANITEC_DEFAULT_EXTENSIONS = defaults.default_extensions.join(',');
  }
  return defaults;
}
