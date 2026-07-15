/**
 * frontend-team-page: бейдж AI-сотрудника в карточке участника (mobile layout).
 */

import { fixtureCleanup, expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { collectFactories } from '@platform/lib/events/factories/register.js';
import { registerFactory } from '@platform/lib/events/factory-registry.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import {
    teamMembersResource,
    inviteGenerateOp,
} from '../../../../apps/frontend/ui/events/resources/team.resource.js';
import frontendEn from '../../../../core/i18n/translations/en/frontend.json' with { type: 'json' };
import { FrontendTeamPage } from '../../../../apps/frontend/ui/pages/team/team-page.js';

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

function templateText(value) {
    if (typeof value === 'string') return value;
    if (Array.isArray(value)) return value.map(templateText).join(' ');
    if (value && Array.isArray(value.values)) return value.values.map(templateText).join(' ');
    return '';
}

function createRenderSubject() {
    const subject = Object.create(FrontendTeamPage.prototype);
    subject.t = (key) => key === 'team_page.flow_employee_badge' ? 'AI employee' : key;
    return subject;
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

    it('_renderRow показывает role-tag AI employee только у flow-сотрудника', () => {
        // Это контракт pure render helper. Не подключаем страницу к DOM, потому
        // что её autoload ресурса не имеет отношения к проверяемому badge.
        const el = createRenderSubject();
        const employeeText = templateText(el._renderRow(EMPLOYEE_MEMBER));
        const humanText = templateText(el._renderRow({
            user_id: 'human_1',
            name: 'Human',
            email: 'human@example.com',
            roles: ['admin'],
            is_flow_employee: false,
        }));

        expect(employeeText).to.include('AI employee');
        expect(humanText).not.to.include('AI employee');
    });

    it('_renderCard показывает role-tag AI employee только у flow-сотрудника', () => {
        const el = createRenderSubject();
        const employeeText = templateText(el._renderCard(EMPLOYEE_MEMBER));
        const humanText = templateText(el._renderCard({
            user_id: 'human_1',
            name: 'Human',
            email: 'human@example.com',
            roles: ['admin'],
            is_flow_employee: false,
        }));

        expect(employeeText).to.include('AI employee');
        expect(humanText).not.to.include('AI employee');
    });
});
