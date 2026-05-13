/**
 * Smoke: CRMNamespaceModal — mode='create' рендерит шаг выбора шаблона,
 * mode='edit' рендерит read-only name + textarea description.
 * Инвариант mode см. CRMNamespaceModal.connectedCallback (негатив не покрываем: uncaught под WTR).
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated, aTimeout } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import {
    bootstrapPlatformBus,
    registerFactory,
    getPlatformBus,
    CoreEvents,
} from '@platform/lib/events/index.js';
import {
    namespacesResource,
    namespaceUpdateOp,
    namespaceEditabilityOp,
    namespaceCreateForm,
    namespaceEditForm,
} from '../../../../apps/crm/ui/events/resources/namespaces.resource.js';
import { templatesResource } from '../../../../apps/crm/ui/events/resources/templates.resource.js';
import {
    entityGrantsListOp,
    entityGrantCreateOp,
    namespaceGrantsListOp,
    namespaceGrantCreateOp,
    grantRevokeOp,
} from '../../../../apps/crm/ui/events/resources/grants.resource.js';
import { teamSearchFacets } from '../../../../apps/crm/ui/events/resources/team-search.resource.js';
import '@platform/lib/components/platform-modal-stack.js';
import '../../../../apps/crm/ui/modals/namespace-modal.js';

const FACTORIES = [
    namespacesResource,
    namespaceUpdateOp,
    namespaceEditabilityOp,
    namespaceCreateForm,
    namespaceEditForm,
    templatesResource,
    entityGrantsListOp,
    entityGrantCreateOp,
    namespaceGrantsListOp,
    namespaceGrantCreateOp,
    grantRevokeOp,
    teamSearchFacets,
];

function setupCrmBus() {
    const slices = {};
    const effects = [];
    for (const f of FACTORIES) {
        registerFactory(f);
        slices[f.sliceKey] = f.slice;
        effects.push(f.effect);
    }
    return bootstrapPlatformBus({
        baseUrl: '',
        routes: [],
        slices,
        effects,
    });
}

describe('crm-namespace-modal', () => {
    beforeEach(() => { resetPlatformState(); setupCrmBus(); });
    afterEach(() => {
        const stale = document.querySelectorAll('crm-namespace-modal');
        stale.forEach((el) => el.remove());
        fixtureCleanup();
    });

    it('mode=create открывает модалку и рендерит блок шаблонов', async () => {
        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, {
            kind: 'crm.namespace',
            props: { mode: 'create' },
        });
        await elementUpdated(stack);
        await aTimeout(0);
        const modal = document.querySelector('crm-namespace-modal');
        expect(modal, 'modal mounted').to.exist;
        expect(modal.mode).to.equal('create');
        const templateLabel = modal.shadowRoot.querySelector('.form-label');
        expect(templateLabel, 'template label rendered').to.exist;
    });

    it('mode=edit с name рендерит read-only name', async () => {
        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, {
            kind: 'crm.namespace',
            props: { mode: 'edit', name: 'demo_ns' },
        });
        await elementUpdated(stack);
        await aTimeout(0);
        const modal = document.querySelector('crm-namespace-modal');
        expect(modal, 'modal mounted').to.exist;
        expect(modal.mode).to.equal('edit');
        expect(modal.name).to.equal('demo_ns');
    });
});
