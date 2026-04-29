import { ServiceRegistry } from '@platform/lib/services/ServiceRegistry.js';
import {
  expect,
  fixture,
  html,
  setupPlatformServices,
  teardownPlatformServices,
  waitUntil,
} from './helpers/index.js';

import { CRMStore } from '../../apps/crm/ui/store/crm.store.js';
import '../../apps/crm/ui/pages/graph-page.js';

function createForceGraphMock() {
  const cameraState = { x: 0, y: 0, z: 1000 };
  const api = {
    _destructor: () => {},
    backgroundColor: () => api,
    cooldownTicks: () => api,
    warmupTicks: () => api,
    showNavInfo: () => api,
    nodeLabel: () => api,
    nodeThreeObject: () => api,
    nodeThreeObjectExtend: () => api,
    nodePositionUpdate: () => api,
    nodeColor: () => api,
    nodeVal: () => api,
    linkLabel: () => api,
    linkColor: () => api,
    linkOpacity: () => api,
    linkWidth: () => api,
    linkThreeObject: () => api,
    linkThreeObjectExtend: () => api,
    linkPositionUpdate: () => api,
    linkDirectionalArrowLength: () => api,
    linkDirectionalArrowRelPos: () => api,
    linkDirectionalArrowColor: () => api,
    linkDirectionalParticles: () => api,
    linkDirectionalParticleWidth: () => api,
    linkDirectionalParticleSpeed: () => api,
    enableNodeDrag: () => api,
    onNodeClick: () => api,
    onNodeHover: () => api,
    onLinkClick: () => api,
    onNodeDragEnd: () => api,
    onEngineTick: () => api,
    onEngineStop: () => api,
    d3Force: () => ({ strength: () => api }),
    d3VelocityDecay: () => api,
    nodeRelSize: () => api,
    graphData: () => api,
    cameraPosition: (...args) => {
      if (args.length === 0) {
        return cameraState;
      }
      const [nextPosition] = args;
      if (nextPosition && typeof nextPosition === 'object') {
        cameraState.x = nextPosition.x;
        cameraState.y = nextPosition.y;
        cameraState.z = nextPosition.z;
      }
      return api;
    },
    centerAt: () => api,
    zoomToFit: () => api,
  };
  return api;
}

describe('crm graph page', () => {
  beforeEach(async () => {
    await setupPlatformServices('/crm');
    ServiceRegistry.register('crmApi', {
      getEntities: async () => ([
        { entity_id: 'entity-1', entity_type: 'contact', name: 'Entity One', attributes: {}, created_at: '2026-01-01T00:00:00Z' },
        { entity_id: 'entity-2', entity_type: 'note', name: 'Entity Two', attributes: {}, created_at: '2026-12-31T00:00:00Z' },
      ]),
      getEntityTimelineBounds: async () => ({
        min_created_at: '2026-01-01T00:00:00Z',
        max_created_at: '2026-12-31T00:00:00Z',
        total_entities: 2,
      }),
      getOverviewGraph: async () => ({
        nodes: [
          { entity_id: 'entity-1', entity_type: 'contact', name: 'Entity One', level: 0, access: true, created_at: '2026-01-01T00:00:00Z' },
          { entity_id: 'entity-2', entity_type: 'note', name: 'Entity Two', level: 1, access: true, created_at: '2026-12-31T00:00:00Z' },
        ],
        edges: [
          { edge_id: 'edge-1', source_id: 'entity-1', target_id: 'entity-2', relationship_type: 'knows', is_directed: true, weight: 1.0, confidence: 1.0 },
        ],
      }),
      getInfluenceGraph: async () => ({
        nodes: [
          { entity_id: 'entity-1', entity_type: 'contact', name: 'Entity One', level: 0, access: true, created_at: '2026-01-01T00:00:00Z' },
          { entity_id: 'entity-2', entity_type: 'note', name: 'Entity Two', level: 1, access: true, created_at: '2026-12-31T00:00:00Z' },
        ],
        edges: [
          { edge_id: 'edge-1', source_id: 'entity-1', target_id: 'entity-2', relationship_type: 'knows', is_directed: true, weight: 1.0, confidence: 1.0 },
        ],
      }),
      getRelatedEntities: async () => ({ incoming: [], outgoing: [], undirected: [] }),
      getShortestPath: async () => ({
        path: ['entity-1', 'entity-2'],
        edges: [],
        exists: true,
        total_distance: 1.0,
        undirected_path: ['entity-1', 'entity-2'],
        undirected_edges: [],
        undirected_exists: true,
        undirected_total_distance: 1.0,
      }),
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
      analyzeNote: async () => ({}),
      getEntityTypes: async () => ([
        { type_id: 'contact', name: 'Contact', color: '#7ac7ff', namespace: 'default' },
        { type_id: 'note', name: 'Note', color: '#ffb457', namespace: 'default' },
        { type_id: 'task', name: 'Task', color: '#8ce9a2', namespace: 'default' },
      ]),
      getEntityTypesByNamespace: async () => ([
        { type_id: 'contact', name: 'Contact', color: '#7ac7ff', namespace: 'default' },
        { type_id: 'note', name: 'Note', color: '#ffb457', namespace: 'default' },
        { type_id: 'task', name: 'Task', color: '#8ce9a2', namespace: 'default' },
      ]),
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
    window.THREE = {
      CanvasTexture: class {
        constructor() {
          this.needsUpdate = false;
        }
      },
      SpriteMaterial: class {
        constructor() {}
      },
      Sprite: class {
        constructor() {
          this.position = { set: () => {} };
          this.scale = { set: () => {} };
          this.visible = true;
        }
      },
    };
    CRMStore.setState({
      namespaces: {
        list: [{ name: 'default', company_id: 'test-company' }],
        templates: [],
        templateDetails: null,
        schemaOptions: null,
        current: { name: 'default', company_id: 'test-company' },
        settingsSelected: null,
        settingsEditability: null,
        settingsLoading: false,
        settingsSaving: false,
        grants: [],
        loading: false,
      },
      entities: {
        notes: [],
        currentNoteId: null,
        noteText: '',
        noteRelatedEntities: [],
        list: [],
        entityTypes: [
          { type_id: 'contact', name: 'Contact', color: '#4ea8ff', namespace: 'default' },
          { type_id: 'note', name: 'Note', color: '#f5b14c', namespace: 'default' },
          { type_id: 'task', name: 'Task', color: '#34c38f', namespace: 'default' },
        ],
        relationshipTypes: [],
        currentEntityId: null,
        currentEntity: null,
        currentEntityRelated: [],
        relationships: [],
        filters: { namespace: 'default', entity_type: null, entity_subtype: null, status: null, priority: null, date_from: null, date_to: null, tags: [], search: '', user_id: null },
        entitiesLoading: false,
        cardLoading: false,
      },
    });
    window.ForceGraph3D = () => () => createForceGraphMock();
    const vendorScript = document.createElement('script');
    vendorScript.src = '/crm/ui/vendor/3d-force-graph/3d-force-graph.min.js';
    document.head.appendChild(vendorScript);
  });

  afterEach(() => {
    document.querySelectorAll('script[src*="3d-force-graph.min.js"]').forEach((script) => script.remove());
    delete window.ForceGraph3D;
    delete window.THREE;
    teardownPlatformServices();
  });

  it('инициализирует 3D граф и показывает матрицу покрытия', async () => {
    const el = await fixture(html`<graph-page></graph-page>`);
    await waitUntil(() => Boolean(el.shadowRoot.querySelector('graph-canvas')));
    await waitUntil(() => el._graphNodes.length > 0);
    const content = el.shadowRoot.textContent;
    expect(content).to.contain('Матрица покрытия API');
    expect(content).to.contain('covered_by_native_ui');
    expect(content).to.contain('covered_by_json_runner_only');
  });

  it('поддерживает graph режимы influence/related/path', async () => {
    const el = await fixture(html`<graph-page></graph-page>`);
    await waitUntil(() => Boolean(el.shadowRoot.querySelector('graph-search-pill')));
    const searchPill = el.shadowRoot.querySelector('graph-search-pill');
    expect(searchPill).to.exist;
    expect(searchPill.modes).to.deep.equal(['influence', 'related', 'path']);
  });

  it('использует офлайн vendor script для 3d-force-graph', async () => {
    const response = await fetch('/apps/crm/ui/index.html');
    expect(response.status).to.equal(200);
    const htmlContent = await response.text();
    expect(htmlContent).to.contain('/crm/ui/vendor/3d-force-graph/3d-force-graph.min.js');
  });

  it('не показывает fullscreen toggle в canvas-first UI', async () => {
    const el = await fixture(html`<graph-page></graph-page>`);
    await waitUntil(() => Boolean(el.shadowRoot.querySelector('graph-canvas')));
    const fullscreenButton = Array.from(el.shadowRoot.querySelectorAll('button'))
      .find((button) => button.textContent.includes('Fullscreen'));
    expect(fullscreenButton).to.not.exist;
  });

  it('рендерит правую икон-панель с tooltip', async () => {
    const el = await fixture(html`<graph-page></graph-page>`);
    await waitUntil(() => Boolean(el.shadowRoot.querySelector('graph-toolbar')));
    const toolbar = el.shadowRoot.querySelector('graph-toolbar');
    expect(toolbar).to.exist;
    expect(toolbar.actions.length).to.be.greaterThan(6);
  });

  it('запускает canvas режим выбора маршрута через toolbar action', async () => {
    const el = await fixture(html`<graph-page></graph-page>`);
    await waitUntil(() => Boolean(el.shadowRoot.querySelector('graph-toolbar')));
    el._onToolbarAction('path_mode');
    expect(el._canvasPathState).to.equal('pick_source');
  });

  it('не падает при выборе одинаковых source и target', async () => {
    const el = await fixture(html`<graph-page></graph-page>`);
    await waitUntil(() => Boolean(el.shadowRoot.querySelector('graph-canvas')));
    el._canvasPathState = 'pick_target';
    el._pathSourceId = 'entity-1';
    el._onCanvasNodeClick({ id: 'entity-1' });
    expect(el._canvasPathState).to.equal('pick_target');
    expect(el._canvasPathHint).to.equal('Выбери другую сущность для target');
  });

  it('фильтрует видимый граф по левому поиску', async () => {
    const el = await fixture(html`<graph-page></graph-page>`);
    await waitUntil(() => Boolean(el.shadowRoot.querySelector('graph-canvas')));
    el._entitySearchQuery = 'Entity Two';
    await el.updateComplete;
    const snapshot = el._getVisibleGraphSnapshot();
    expect(snapshot.isFiltered).to.equal(true);
    expect(snapshot.nodes.length).to.equal(1);
  });

  it('формирует timeline query params для backend фильтра', async () => {
    const el = await fixture(html`<graph-page></graph-page>`);
    await waitUntil(() => Boolean(el.shadowRoot.querySelector('graph-canvas')));
    el._timelineStartPercent = 50;
    el._timelineEndPercent = 100;
    await el.updateComplete;
    const params = el._getTimelineQueryParams();
    expect(params).to.have.property('created_at_from');
    expect(params).to.have.property('created_at_to');
  });

  it('не очищает сцену если путь не найден', async () => {
    const el = await fixture(html`<graph-page></graph-page>`);
    await waitUntil(() => Boolean(el.shadowRoot.querySelector('graph-canvas')));
    await waitUntil(() => el._graphNodes.length > 0);
    el.crmApi.getShortestPath = async () => ({
      path: [],
      edges: [],
      exists: false,
      total_distance: 0,
      undirected_path: [],
      undirected_edges: [],
      undirected_exists: false,
      undirected_total_distance: 0,
    });
    el._pathSourceId = 'entity-1';
    el._pathTargetId = 'entity-2';
    await el._buildPathGraph();
    expect(el._graphNodes.length).to.be.greaterThan(0);
    expect(el._canvasPathHint).to.equal('Маршрут не найден');
  });
});
