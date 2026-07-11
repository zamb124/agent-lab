/**
 * frontend-team-page: бейдж AI-сотрудника в карточке участника (mobile layout).
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { render } from 'lit';
import {
    teamMembersResource,
    inviteGenerateOp,
} from '../../../../apps/frontend/ui/events/resources/team.resource.js';
import frontendEn from '../../../../core/i18n/translations/en/frontend.json' with { type: 'json' };
import '../../../../apps/frontend/ui/pages/team/team-page.js';

const FACTORIES = [teamMembersResource, inviteGenerateOp];

const EMPLOYEE_MEMBER = {
    user_id: 'flow_employee_demo',
    name: 'AI Worker',
    email: 'ai@example.com',
    roles: ['member'],
    is_flow_employee: true,
    flow_id: 'demo_flow',
    curator_user_ids: ['curator_1'],
};

function bootstrapTeamBus() {
    for (const factory of FACTORIES) {
        registerFactory(factory);
    }
    const collected = collectFactories(FACTORIES);
    return bootstrapTestBus({ slices: collected.slices, effects: collected.effects });
}

function seedFrontendTranslations() {
    const bus = getPlatformBus();
    const prevEn = bus.getState().i18n.translations.en;
    bus.dispatch(
        CoreEvents.I18N_LOCALE_LOADED,
        { locale: 'en', bundle: { ...prevEn, frontend: frontendEn } },
        { source: 'system' },
    );
    bus.dispatch(
        CoreEvents.I18N_LOCALE_CHANGED,
        { locale: 'en', default_namespace: null },
        { source: 'system' },
    );
}

describe('frontend-team-page flow employee badge', () => {
    beforeEach(() => {
        resetPlatformState();
        setDefaultI18nNamespace('frontend');
        bootstrapTeamBus();
        seedFrontendTranslations();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('_renderCard показывает role-tag AI employee только у flow-сотрудника', async () => {
        const el = await fixture(html`<frontend-team-page></frontend-team-page>`);
        await elementUpdated(el);

        const employeeHost = document.createElement('div');
        const humanHost = document.createElement('div');
        render(el._renderCard(EMPLOYEE_MEMBER), employeeHost);
        render(el._renderCard({
            user_id: 'human_1',
            name: 'Human',
            email: 'human@example.com',
            roles: ['admin'],
            is_flow_employee: false,
        }), humanHost);

        const employeeTags = Array.from(employeeHost.querySelectorAll('.role-tag')).map((n) => n.textContent.trim());
        const humanTags = Array.from(humanHost.querySelectorAll('.role-tag')).map((n) => n.textContent.trim());
        expect(employeeTags.some((t) => t.includes('AI employee'))).to.be.true;
        expect(humanTags.some((t) => t.includes('AI employee'))).to.be.false;
    });
});
