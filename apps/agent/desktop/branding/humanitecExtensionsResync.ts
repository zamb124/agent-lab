type HumanitecAgentResyncApi = {
  onExtensionsResync: (callback: () => void) => void;
};

export function installHumanitecExtensionsResyncListener(resync: () => void): () => void {
  const api = (window as Window & { humanitecAgent?: HumanitecAgentResyncApi }).humanitecAgent;
  if (api === undefined || typeof api.onExtensionsResync !== 'function') {
    return () => {};
  }
  api.onExtensionsResync(resync);
  return () => {};
}
