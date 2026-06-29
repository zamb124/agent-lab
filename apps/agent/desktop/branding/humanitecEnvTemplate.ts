const ENV_TEMPLATE_PATTERN = /\$\{([A-Z0-9_]+)\}/g;

export function resolveHumanitecEnvTemplate(value: string): string {
  return value.replace(ENV_TEMPLATE_PATTERN, (_match, envName: string) => {
    const envValue = process.env[envName];
    if (typeof envValue !== 'string' || !envValue.trim()) {
      throw new Error(`${envName} is not set`);
    }
    return envValue.trim();
  });
}

export function resolveHumanitecEnvTemplates(templates: string[]): string[] {
  return templates.map((template) => resolveHumanitecEnvTemplate(template));
}
