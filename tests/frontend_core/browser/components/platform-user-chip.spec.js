/**
 * platform-user-chip: контракт user-id обязателен; интерактив открывает
 * platform.user_info; чужой user_id триггерит загрузку team.members.
 */

import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-user-chip.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { TEAM_EVENTS } from '@platform/lib/events/reducers/team.js';

describe('platform-user-chip', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('без user-id — _resolveUser бросает', async () => {
        const el = document.createElement('platform-user-chip');
        document.body.appendChild(el);
        // _resolveUser требует hostConnected SelectController'а, поэтому
        // ждём первый цикл (даже если render внутри упадёт — мы это сразу
        // проверяем явным вызовом).
        try { await el.updateComplete; } catch { /* render error ожидаем */ }
        expect(() => el._resolveUser()).to.throw(/user-id/);
        el.remove();
    });

    it('size != sm|md — throw при updated', async () => {
        const el = document.createElement('platform-user-chip');
        el.setAttribute('user-id', 'u1');
        document.body.appendChild(el);
        await el.updateComplete;
        let caught = null;
        try {
            el.size = 'xl';
            await el.updateComplete;
        } catch (e) {
            caught = e;
        }
        expect(caught).to.exist;
        el.remove();
    });

    it('диспатчит MEMBERS_LOAD_REQUESTED при первом монтировании если auth=authenticated и список пустой', async () => {
        // 1) auth.user_loaded — переводим в authenticated
        getPlatformBus().dispatch(CoreEvents.AUTH_USER_LOADED, { user: { user_id: 'self', name: 'me' } });
        const events = [];
        getPlatformBus().subscribeAny((e) => events.push(e));
        const el = await fixture(html`<platform-user-chip user-id="u1"></platform-user-chip>`);
        await elementUpdated(el);
        const req = events.find((e) => e.type === TEAM_EVENTS.MEMBERS_LOAD_REQUESTED);
        expect(req).to.exist;
    });

    it('клик по интерактивному чипу с найденным членом → openModal platform.user_info', async () => {
        getPlatformBus().dispatch(CoreEvents.AUTH_USER_LOADED, { user: { user_id: 'self', name: 'me' } });
        getPlatformBus().dispatch(TEAM_EVENTS.MEMBERS_LOADED, { items: [{ user_id: 'u1', name: 'Alice', email: 'a@b' }] });
        const events = [];
        getPlatformBus().subscribeAny((e) => events.push(e));
        const el = await fixture(html`<platform-user-chip user-id="u1"></platform-user-chip>`);
        await elementUpdated(el);
        el._onClick();
        const open = events.find((e) => e.type === CoreEvents.UI_MODAL_OPEN);
        expect(open).to.exist;
        expect(open.payload.kind).to.equal('platform.user_info');
        expect(open.payload.props.userId).to.equal('u1');
    });

    it('interactive=false → клик не открывает модалку', async () => {
        getPlatformBus().dispatch(CoreEvents.AUTH_USER_LOADED, { user: { user_id: 'self', name: 'me' } });
        getPlatformBus().dispatch(TEAM_EVENTS.MEMBERS_LOADED, { items: [{ user_id: 'u1', name: 'Alice' }] });
        const el = await fixture(html`<platform-user-chip user-id="u1" .interactive=${false}></platform-user-chip>`);
        await elementUpdated(el);
        const events = [];
        getPlatformBus().subscribeAny((e) => events.push(e));
        el._onClick();
        expect(events.find((e) => e.type === CoreEvents.UI_MODAL_OPEN)).to.be.undefined;
    });
});
