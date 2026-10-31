/**
 * Smoke: CRMEntityCard — create и edit: верстка, статусы из entities.status, score у связи.
 */

import type { SliceDef } from '@platform/lib/events/reducers/index.js';
import { fixture, fixtureCleanup, html, expect, elementUpdated, aTimeout } from '../helpers/render.js';
import { resetPlatformState } from '../helpers/reset.js';
import {
    bootstrapPlatformBus,
    registerFactory,
    getPlatformBus,
    CoreEvents,
} from '@platform/lib/events/index.js';
import {
    entitiesResource,
    entityCardOp,
    entityUpdateOp,
    entityCreateForm,
    entityEditForm,
    entitySearchOp,
} from '../../../../apps/crm/ui/events/resources/entities.resource.js';
import { entityTypesResource } from '../../../../apps/crm/ui/events/resources/entity-types.resource.js';
import { relationshipsResource } from '../../../../apps/crm/ui/events/resources/relationships.resource.js';
import { relationshipTypesResource } from '../../../../apps/crm/ui/events/resources/relationship-types.resource.js';
import {
    attachmentsListOp,
    attachmentUploadOp,
    attachmentDeleteOp,
} from '../../../../apps/crm/ui/events/resources/attachments.resource.js';
import { grantsListOp } from '../../../../apps/crm/ui/events/resources/grants.resource.js';
import { relatedEntitiesOp } from '../../../../apps/crm/ui/events/resources/graph.resource.js';
import crmRu from '../../../../core/i18n/translations/ru/crm.json' with { type: 'json' };
import '../../../../apps/crm/ui/components/entity-card.js';
import {q, qs, qsa, shadow, type TestEl} from '../helpers/dom.js';

const FACTORIES = [
    entitiesResource,
    entityCardOp,
    entityUpdateOp,
    entityCreateForm,
    entityEditForm,
    entitySearchOp,
    entityTypesResource,
    relationshipsResource,
    relationshipTypesResource,
    attachmentsListOp,
    attachmentUploadOp,
    attachmentDeleteOp,
    grantsListOp,
    relatedEntitiesOp,
];

function setupCrmBus() {
    const slices: Record<string, SliceDef> = {};
    const effects: any[] = [];
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

function seedCrmTranslations() {
    const bus = getPlatformBus();
    const state = bus.getState().i18n;
    const prevRu = state.translations.ru;
    bus.dispatch(
        CoreEvents.I18N_LOCALE_LOADED,
        {
            locale: 'ru',
            bundle: {
                ...prevRu,
                crm: crmRu,
            },
        },
        { source: 'system' },
    );
    bus.dispatch(
        CoreEvents.I18N_LOCALE_CHANGED,
        { locale: 'ru', default_namespace: null },
        { source: 'system' },
    );
}

describe('crm-entity-card', () => {
    beforeEach(() => {
        resetPlatformState();
        setupCrmBus();
        seedCrmTranslations();
    });
    afterEach(() => {
        qsa(document!, 'crm-entity-card').forEach((el) => el.remove());
        fixtureCleanup();
    });

    it('panel-mode=create рендерит область выбора типа', async () => {
        const el = await fixture<TestEl>(html`
            <crm-entity-card panel-mode="create"></crm-entity-card>
        `);
        await elementUpdated(el);
        await aTimeout(0);
        const root = shadow(el);
        expect(root, 'shadowRoot').to.exist;
        const scroll = qs(root!, '.scroll');
        expect(scroll, 'main scroll area').to.exist;
    });

    it('panel-mode=edit с cardBundle: статусы переведены, без ключа entity_modal.status_', async () => {
        const bundle = {
            entity: {
                entity_id: 'e_test_1',
                name: 'Entity A',
                description: '',
                status: 'active',
                namespace: 'ns',
                entity_type: 'note',
                entity_subtype: '',
                attributes: {},
                tags: [],
            },
            relationships: [],
            related_entities: [],
            attachments: [],
        };
        const el = await fixture<TestEl>(html`
            <crm-entity-card
                panel-mode="edit"
                entity-id="e_test_1"
                layout-variant="detailSummary"
                .cardBundle=${bundle}
            ></crm-entity-card>
        `);
        await elementUpdated(el);
        await aTimeout(0);
        const root = shadow(el);
        const text = (root && root.textContent) ? root.textContent : '';
        expect(text.includes('entity_modal.status_')).to.equal(false);
        const statusRow = q(root!, '.edit-name-status-row');
        const sheetStatus = qs(root!, '.sheet-block platform-field[type="enum"]');
        const statusField = (statusRow && qs(statusRow!, 'platform-field[type="enum"]')) || sheetStatus;
        expect(statusField, 'status platform-field').to.exist;
        const pfEnum = shadow(statusField) && qs(shadow(statusField), 'platform-field-enum');
        expect(pfEnum, 'platform-field-enum').to.exist;
        const enumInp = shadow(pfEnum) && qs(shadow(pfEnum), 'input.field-pill-enum-input');
        expect(enumInp, 'enum combobox inside platform-field').to.exist;
        enumInp.focus();
        await elementUpdated(pfEnum);
        const activeRow = qs(shadow(pfEnum), '[data-enum-value="active"]');
        expect(activeRow, 'status enum row active').to.exist;
        expect((activeRow.textContent || '').includes('Актив')).to.equal(true);
    });

    it('panel-mode=edit: связь с score показывает полосу силы связи', async () => {
        const bundle = {
            entity: {
                entity_id: 'e_main',
                name: 'Main',
                description: '',
                status: 'active',
                namespace: 'ns',
                entity_type: 'note',
                entity_subtype: '',
                attributes: {},
                tags: [],
            },
            relationships: [
                {
                    relationship_id: 'r1',
                    source_entity_id: 'e_main',
                    target_entity_id: 'e_other',
                    relationship_type: 'mentions',
                },
            ],
            related_entities: [
                {
                    entity_id: 'e_other',
                    name: 'Other',
                    entity_type: 'contact',
                    score: 0.73,
                },
            ],
            attachments: [],
        };
        const el = await fixture<TestEl>(html`
            <crm-entity-card
                panel-mode="edit"
                entity-id="e_main"
                layout-variant="full"
                .cardBundle=${bundle}
            ></crm-entity-card>
        `);
        await elementUpdated(el);
        await aTimeout(0);
        const root = shadow(el);
        const neighborRows = qs(root!, 'crm-related-neighbor-rows');
        expect(neighborRows, 'neighbor rows host').to.exist;
        const nrRoot = shadow(neighborRows);
        expect(nrRoot, 'neighbor rows shadow').to.exist;
        const scoreEl = qs(nrRoot!, '.neighbor-strength-fill');
        expect(scoreEl, 'semantic match strength bar').to.exist;
    });
});
