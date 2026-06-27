import fs from 'node:fs';
import path from 'node:path';

export type HumanitecAgentCredentials = {
  device_id: string;
  token: string;
  frontend_base_url: string;
  tunnel_ws_url: string;
  platform_mcp_url: string;
  company_id: string;
  company_subdomain: string | null;
  llm_api_base_url: string;
  llm_provider_id: string;
  llm_model_id: string;
};

export function humanitecAgentStorePath(userDataPath: string): string {
  return path.join(userDataPath, 'humanitec-agent.json');
}

function requireCredentialString(
  parsed: HumanitecAgentCredentials,
  field: keyof HumanitecAgentCredentials,
): void {
  const value = parsed[field];
  if (typeof value !== 'string' || !value) {
    throw new Error(`humanitec-agent.json: ${field} обязателен`);
  }
}

export function loadHumanitecAgentCredentials(userDataPath: string): HumanitecAgentCredentials | null {
  const storePath = humanitecAgentStorePath(userDataPath);
  if (!fs.existsSync(storePath)) {
    return null;
  }
  const raw = fs.readFileSync(storePath, 'utf-8');
  const parsed = JSON.parse(raw) as HumanitecAgentCredentials;
  requireCredentialString(parsed, 'device_id');
  requireCredentialString(parsed, 'token');
  requireCredentialString(parsed, 'frontend_base_url');
  requireCredentialString(parsed, 'tunnel_ws_url');
  requireCredentialString(parsed, 'platform_mcp_url');
  requireCredentialString(parsed, 'company_id');
  requireCredentialString(parsed, 'llm_api_base_url');
  requireCredentialString(parsed, 'llm_provider_id');
  requireCredentialString(parsed, 'llm_model_id');
  return parsed;
}

export function saveHumanitecAgentCredentials(
  userDataPath: string,
  credentials: HumanitecAgentCredentials,
): void {
  const storePath = humanitecAgentStorePath(userDataPath);
  fs.writeFileSync(storePath, JSON.stringify(credentials, null, 2) + '\n', 'utf-8');
}

export function clearHumanitecAgentCredentials(userDataPath: string): void {
  const storePath = humanitecAgentStorePath(userDataPath);
  if (fs.existsSync(storePath)) {
    fs.unlinkSync(storePath);
  }
}
