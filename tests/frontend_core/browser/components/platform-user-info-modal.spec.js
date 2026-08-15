/**
 * platform-user-info-modal: бейдж/секция flow-сотрудника, редактор, кураторы, act-as.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { TEAM_EVENTS } from '@platform/lib/events/reducers/team.js';
import platformEn from '../../../../core/i18n/translations/en/platform.json' with { type: 'json' };
import '@platform/lib/components/platform-user-info-modal.js';

const EMPLOYEE = {
    user_id: 'flow_employee_test_flow',
    name: 'AI Worker',
    email: 'ai@example.com',
    roles: ['member'],
    is_flow_employee: true,
    flow_id: 'test_flow',
    curator_user_ids: ['curator_1'],
};

function seedPlatformTranslations() {
    const bus = getPlatformBus();
    const prevEn = bus.getState().i18n.translations.en;
    bus.dispatch(
        CoreEvents.I18N_LOCALE_LOADED,
        { locale: 'en', bundle: { ...prevEn, platform: platformEn } },
        { source: 'system' },
    );
    bus.dispatch(
        CoreEvents.I18N_LOCALE_CHANGED,
        { locale: 'en', default_namespace: null },
        { source: 'system' },
    );
}

function seedAuthUser({
    userId = 'admin_1',
    roles = ['owner', 'admin'],
    canAdmin = true,
} = {}) {
    getPlatformBus().dispatch(CoreEvents.AUTH_USER_LOADED, {
        user: {
            user_id: userId,
            name: 'Admin',
            roles,
            canAdmin,
            raw: {
                user_id: userId,
                roles,
                emails: ['admin@example.com'],
                can_admin: canAdmin,
            },
        },
    });
}

function seedTeamMembers(items) {
    getPlatformBus().dispatch(TEAM_EVENTS.MEMBERS_LOADED, { items });
}

async function mountOtherUserModal(userId) {
    const el = await fixture(html`
        <platform-user-info-modal user-id=${userId} .open=${true}></platform-user-info-modal>
    `);
    await elementUpdated(el);
    return el;
}

function footerText(el) {
    const footer = el.shadowRoot.querySelector('.modal-footer, .actions');
    return footer ? footer.textContent : '';
}

describe('platform-user-info-modal flow employee', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
        setDefaultI18nNamespace('platform');
        seedPlatformTranslations();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('показывает бейдж и секцию AI-сотрудника с ссылкой на редактор', async () => {
        seedAuthUser();
        seedTeamMembers([EMPLOYEE]);
        const el = await mountOtherUserModal(EMPLOYEE.user_id);

        const badge = el.shadowRoot.querySelector('.role-chip');
        expect(badge).to.exist;
        expect(badge.textContent).to.include('AI employee');

        const section = el.shadowRoot.querySelector('.channels-section');
        expect(section).to.exist;
        expect(section.textContent).to.include('AI employee');

        const editorLink = section.querySelector('a[href="/flows/editor/test_flow"]');
        expect(editorLink).to.exist;
    });

    it('рендерит чипы кураторов в секции сотрудника', async () => {
        seedAuthUser();
        seedTeamMembers([EMPLOYEE]);
        const el = await mountOtherUserModal(EMPLOYEE.user_id);

        const curatorChip = el.shadowRoot.querySelector('platform-user-chip[user-id="curator_1"]');
        expect(curatorChip).to.exist;
    });

    it('_canActAs: admin видит кнопку act-as', async () => {
        seedAuthUser({ userId: 'admin_1', roles: ['admin'], canAdmin: true });
        seedTeamMembers([EMPLOYEE]);
        const el = await mountOtherUserModal(EMPLOYEE.user_id);

        expect(el._canActAs(el._resolveUser().user)).to.be.true;
        expect(footerText(el)).to.include('Act as employee');
    });

    it('_canActAs: куратор видит act-as', async () => {
        seedAuthUser({ userId: 'curator_1', roles: ['member'], canAdmin: false });
        seedTeamMembers([EMPLOYEE]);
        const el = await mountOtherUserModal(EMPLOYEE.user_id);

        expect(el._canActAs(el._resolveUser().user)).to.be.true;
        expect(footerText(el)).to.include('Act as employee');
    });

    it('_canActAs: обычный member без кураторства не видит act-as', async () => {
        seedAuthUser({ userId: 'member_2', roles: ['member'], canAdmin: false });
        seedTeamMembers([EMPLOYEE]);
        const el = await mountOtherUserModal(EMPLOYEE.user_id);

        expect(el._canActAs(el._resolveUser().user)).to.be.false;
        expect(footerText(el)).to.not.include('Act as employee');
    });

    it('обычный участник без is_flow_employee не показывает бейдж и секцию', async () => {
        seedAuthUser();
        seedTeamMembers([{
            user_id: 'human_1',
            name: 'Human',
            email: 'human@example.com',
            roles: ['member'],
            is_flow_employee: false,
        }]);
        const el = await mountOtherUserModal('human_1');

        const body = el.shadowRoot.textContent;
        expect(body).to.not.include('flow_employee_open_editor');
        expect(el.shadowRoot.querySelector('.channels-section')).to.be.null;
    });
});
