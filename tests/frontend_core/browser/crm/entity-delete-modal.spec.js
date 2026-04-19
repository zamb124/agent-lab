/**
 * Smoke: CRMEntityDeleteModal — confirm → REMOVE_REQUESTED для entityId,
 * REMOVED → close + navigate(redirectRoute).
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated, aTimeout } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import {
    bootstrapPlatformBus,
    registerFactory,
    getPlatformBus,
    CoreEvents,
} from '@platform/lib/events/index.js';
import { entitiesResource } from '../../../../apps/crm/ui/events/resources/entities.resource.js';
import '@platform/lib/components/platform-modal-stack.js';
import '../../../../apps/crm/ui/modals/entity-delete-modal.js';

function setupCrmBus() {
    registerFactory(entitiesResource);
    return bootstrapPlatformBus({
        baseUrl: '',
        routes: [],
        slices: { [entitiesResource.sliceKey]: entitiesResource.slice },
        effects: [entitiesResource.effect],
    });
}

describe('crm-entity-delete-modal', () => {
    beforeEach(() => { resetPlatformState(); setupCrmBus(); });
    afterEach(() => {
        document.querySelectorAll('crm-entity-delete-modal').forEach((el) => el.remove());
        fixtureCleanup();
    });

    it('рендерит шапку и кнопку confirm; confirm диспатчит REMOVE_REQUESTED', async () => {
        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        const bus = getPlatformBus();

        const captured = [];
        const off = bus.subscribeType(entitiesResource.events.REMOVE_REQUESTED, (event) => {
            captured.push(event);
        });

        bus.dispatch(CoreEvents.UI_MODAL_OPEN, {
            kind: 'crm.entity_delete',
            props: { entityId: 'abc-123', redirectRoute: 'entities' },
        });
        await elementUpdated(stack);
        await aTimeout(0);

        const modal = document.querySelector('crm-entity-delete-modal');
        expect(modal, 'modal mounted').to.exist;
        expect(modal.entityId).to.equal('abc-123');
        expect(modal.redirectRoute).to.equal('entities');

        const confirmBtn = modal.shadowRoot.querySelector('button.btn-danger');
        expect(confirmBtn, 'confirm btn rendered').to.exist;
        confirmBtn.click();
        await aTimeout(0);

        expect(captured.length, 'REMOVE_REQUESTED dispatched').to.be.greaterThan(0);
        const payload = captured[captured.length - 1].payload;
        expect(payload[entitiesResource.idField]).to.equal('abc-123');

        off();
    });
});
