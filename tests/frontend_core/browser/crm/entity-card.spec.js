/**
 * Smoke: CRMEntityCard — create и edit: верстка, статусы из entities.status, score у связи.
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
import { entityGrantsListOp } from '../../../../apps/crm/ui/events/resources/grants.resource.js';
import { relatedEntitiesOp } from '../../../../apps/crm/ui/events/resources/graph.resource.js';
import crmRu from '../../../../core/i18n/translations/ru/crm.json' with { type: 'json' };
import '../../../../apps/crm/ui/components/entity-card.js';

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
    entityGrantsListOp,
    relatedEntitiesOp,
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
        document.querySelectorAll('crm-entity-card').forEach((el) => el.remove());
        fixtureCleanup();
    });

    it('panel-mode=create рендерит область выбора типа', async () => {
        const el = await fixture(html`
            <crm-entity-card panel-mode="create"></crm-entity-card>
        `);
        await elementUpdated(el);
        await aTimeout(0);
        const root = el.shadowRoot;
        expect(root, 'shadowRoot').to.exist;
        const scroll = root.querySelector('.scroll');
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
        const el = await fixture(html`
            <crm-entity-card
                panel-mode="edit"
                entity-id="e_test_1"
                layout-variant="detailSummary"
                .cardBundle=${bundle}
            ></crm-entity-card>
        `);
        await elementUpdated(el);
        await aTimeout(0);
        const root = el.shadowRoot;
        const text = (root && root.textContent) ? root.textContent : '';
        expect(text.includes('entity_modal.status_')).to.equal(false);
        const statusRow = root.querySelector('.edit-name-status-row');
        const sheetStatus = root.querySelector('.sheet-block platform-field[type="enum"]');
        const statusField = (statusRow && statusRow.querySelector('platform-field[type="enum"]')) || sheetStatus;
        expect(statusField, 'status platform-field').to.exist;
        const pfEnum = statusField.shadowRoot && statusField.shadowRoot.querySelector('platform-field-enum');
        expect(pfEnum, 'platform-field-enum').to.exist;
        const statusInner = pfEnum.shadowRoot && pfEnum.shadowRoot.querySelector('select');
        expect(statusInner, 'status select inside platform-field').to.exist;
        const firstOpt = statusInner.querySelector('option[value="active"]');
        expect(firstOpt, 'status option').to.exist;
        expect((firstOpt.textContent || '').length > 0).to.equal(true);
        expect((firstOpt.textContent || '').includes('Актив')).to.equal(true);
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
        const el = await fixture(html`
            <crm-entity-card
                panel-mode="edit"
                entity-id="e_main"
                layout-variant="full"
                .cardBundle=${bundle}
            ></crm-entity-card>
        `);
        await elementUpdated(el);
        await aTimeout(0);
        const root = el.shadowRoot;
        const neighborRows = root.querySelector('crm-related-neighbor-rows');
        expect(neighborRows, 'neighbor rows host').to.exist;
        const nrRoot = neighborRows.shadowRoot;
        expect(nrRoot, 'neighbor rows shadow').to.exist;
        const scoreEl = nrRoot.querySelector('.neighbor-strength-fill');
        expect(scoreEl, 'semantic match strength bar').to.exist;
    });
});
