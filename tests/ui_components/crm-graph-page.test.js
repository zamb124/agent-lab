import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';
import {
  expect,
  fixture,
  html,
  setupPlatformServices,
  teardownPlatformServices,
  waitUntil,
} from './helpers/index.js';

import '../../apps/crm/ui/pages/graph-page.js';

function createForceGraphMock() {
  const api = {
    _destructor: () => {},
    backgroundColor: () => api,
    cooldownTicks: () => api,
    warmupTicks: () => api,
    nodeLabel: () => api,
    nodeColor: () => api,
    nodeVal: () => api,
    linkLabel: () => api,
    linkColor: () => api,
    linkWidth: () => api,
    linkDirectionalArrowLength: () => api,
    linkDirectionalArrowRelPos: () => api,
    linkDirectionalParticles: () => api,
    linkDirectionalParticleWidth: () => api,
    onNodeClick: () => api,
    onNodeHover: () => api,
    onLinkClick: () => api,
    d3Force: () => ({ strength: () => api }),
    nodeRelSize: () => api,
    graphData: () => api,
    cameraPosition: () => api,
  };
  return api;
}

describe('crm graph page', () => {
  beforeEach(async () => {
    await setupPlatformServices('/crm');
    ServiceRegistry.register('crmApi', {
      getEntities: async () => ([
        { entity_id: 'entity-1', entity_type: 'contact', name: 'Entity One', attributes: {} },
        { entity_id: 'entity-2', entity_type: 'note', name: 'Entity Two', attributes: {} },
      ]),
      getInfluenceGraph: async () => ({
        nodes: [
          { entity_id: 'entity-1', entity_type: 'contact', name: 'Entity One', level: 0, access: true },
          { entity_id: 'entity-2', entity_type: 'note', name: 'Entity Two', level: 1, access: true },
        ],
        edges: [
          { edge_id: 'edge-1', source_id: 'entity-1', target_id: 'entity-2', relationship_type: 'knows', is_directed: true, weight: 1.0 },
        ],
      }),
      getRelatedEntities: async () => ({ incoming: [], outgoing: [], undirected: [] }),
      getShortestPath: async () => ({ path: ['entity-1', 'entity-2'], edges: [], exists: true, total_distance: 1.0 }),
      searchEntities: async () => ([{ entity_id: 'entity-1', name: 'Entity One' }]),
      getEntityRelationships: async () => ({ relationships: [] }),
      uploadAttachment: async () => ({ status: 'ok' }),
      createEntity: async () => ({ status: 'ok' }),
      updateEntity: async () => ({ status: 'ok' }),
      deleteEntity: async () => ({ status: 'ok' }),
      createRelationship: async () => ({ status: 'ok' }),
      deleteRelationship: async () => ({ status: 'ok' }),
      grantToUser: async () => ({ status: 'ok' }),
      grantToCompany: async () => ({ status: 'ok' }),
      makeEntityPublic: async () => ({ status: 'ok' }),
      grantNamespaceToUser: async () => ({ status: 'ok' }),
      grantNamespaceToCompany: async () => ({ status: 'ok' }),
      makeNamespacePublic: async () => ({ status: 'ok' }),
      revokeGrant: async () => ({ status: 'ok' }),
      createAccessRequest: async () => ({ status: 'ok' }),
      listAccessRequests: async () => ([]),
      approveAccessRequest: async () => ({ status: 'ok' }),
      rejectAccessRequest: async () => ({ status: 'ok' }),
      getNamespaces: async () => ([]),
      createNamespace: async () => ({ status: 'ok' }),
      getNamespaceTemplates: async () => ([]),
      getNamespaceGrants: async () => ([]),
      getEntityAttachments: async () => ([]),
      getEntity: async () => ({ entity_id: 'entity-1' }),
      findEntitiesByText: async () => ([]),
      analyzeText: async () => ({}),
      getEntityTypes: async () => ([]),
      getEntityTypesByNamespace: async () => ([]),
      createEntityType: async () => ({}),
      getRelationships: async () => ([]),
      getRelationship: async () => ({}),
      getRelationshipTypes: async () => ({ relationship_types: [] }),
      createRelationshipType: async () => ({}),
      getEntityWithRelatedEntities: async () => ({ entity: {}, relationships: [], relatedEntities: [] }),
      getEntityCard: async () => ({}),
      getDailySummary: async () => ({}),
      getEntityGrants: async () => ([]),
      getAccessRequest: async () => ({}),
      getNamespaceEditability: async () => ({}),
      updateNamespace: async () => ({}),
      getTemplateSchemaOptions: async () => ({}),
      getNamespaceTemplate: async () => ({}),
      createNamespaceTemplate: async () => ({}),
      updateNamespaceTemplate: async () => ({}),
      deleteNamespaceTemplate: async () => ({}),
      upsertNamespaceTemplateType: async () => ({}),
      deleteNamespaceTemplateType: async () => ({}),
      deleteAttachment: async () => ({}),
    });
    window.ForceGraph3D = () => () => createForceGraphMock();
    const vendorScript = document.createElement('script');
    vendorScript.src = '/crm/ui/vendor/3d-force-graph/3d-force-graph.min.js';
    document.head.appendChild(vendorScript);
  });

  afterEach(() => {
    document.querySelectorAll('script[src*="3d-force-graph.min.js"]').forEach((script) => script.remove());
    delete window.ForceGraph3D;
    teardownPlatformServices();
  });

  it('инициализирует 3D граф и показывает матрицу покрытия', async () => {
    const el = await fixture(html`<graph-page></graph-page>`);
    await waitUntil(() => Boolean(el.shadowRoot.querySelector('#graph-canvas')));
    await waitUntil(() => el._graphNodes.length > 0);
    const content = el.shadowRoot.textContent;
    expect(content).to.contain('Матрица покрытия API');
    expect(content).to.contain('covered_by_native_ui');
    expect(content).to.contain('covered_by_json_runner_only');
  });

  it('поддерживает graph режимы influence/related/path', async () => {
    const el = await fixture(html`<graph-page></graph-page>`);
    await waitUntil(() => Boolean(el.shadowRoot.querySelector('.toolbar-select')));
    const modeSelect = el.shadowRoot.querySelector('.toolbar-select');
    const options = Array.from(modeSelect.querySelectorAll('option')).map((option) => option.value);
    expect(options).to.deep.equal(['influence', 'related', 'path']);
  });

  it('использует офлайн vendor script для 3d-force-graph', async () => {
    const response = await fetch('/apps/crm/ui/index.html');
    expect(response.status).to.equal(200);
    const htmlContent = await response.text();
    expect(htmlContent).to.contain('/crm/ui/vendor/3d-force-graph/3d-force-graph.min.js');
  });

  it('включает fullscreen режим графа', async () => {
    const el = await fixture(html`<graph-page></graph-page>`);
    await waitUntil(() => Boolean(el.shadowRoot.querySelector('#graph-canvas')));
    const fullscreenButton = Array.from(el.shadowRoot.querySelectorAll('button'))
      .find((button) => button.textContent.includes('Fullscreen графа'));
    expect(fullscreenButton).to.exist;
    fullscreenButton.click();
    await waitUntil(() => el.shadowRoot.querySelector('.layout').classList.contains('fullscreen'));
  });
});
