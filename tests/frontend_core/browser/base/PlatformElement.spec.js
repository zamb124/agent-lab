/**
 * PlatformElement: все 17 helpers + контракт «throw на отсутствие args».
 *
 * Не тестируем реальные сетевые/DOM-эффекты — слушаем bus через subscribeAny.
 */

import { html as litHtml } from 'lit';
import { fixture, html, expect } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';

class HostEl extends PlatformElement {
    static i18nNamespace = 'platform';
    render() { return litHtml`<span>host</span>`; }
}
customElements.define('frontend-core-host-el', HostEl);

async function makeHost() {
    return fixture(html`<frontend-core-host-el></frontend-core-host-el>`);
}

function captureBusEvents() {
    const events = [];
    getPlatformBus().subscribeAny((e) => events.push(e));
    return events;
}

describe('PlatformElement: dispatch', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('dispatch без type — throw', async () => {
        const el = await makeHost();
        expect(() => el.dispatch('')).to.throw(/type required/);
        expect(() => el.dispatch(null)).to.throw(/type required/);
    });

    it('dispatch без payload — throw (zero-guess)', async () => {
        const el = await makeHost();
        expect(() => el.dispatch('test/x/y')).to.throw(/payload required/);
    });

    it('dispatch валидный — попадает в bus', async () => {
        const el = await makeHost();
        const events = captureBusEvents();
        el.dispatch('test/x/y', { foo: 1 });
        const ev = events.find((e) => e.type === 'test/x/y');
        expect(ev.payload).to.deep.equal({ foo: 1 });
    });
});

describe('PlatformElement: helper toast', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('toast без i18n_key — throw', async () => {
        const el = await makeHost();
        expect(() => el.toast('')).to.throw(/i18n_key required/);
    });

    it('toast с неизвестным type — throw', async () => {
        const el = await makeHost();
        expect(() => el.toast('platform:msg', { type: 'cosmic' })).to.throw(/invalid type/);
    });

    it('toast квалифицирует ключ префиксом namespace', async () => {
        const el = await makeHost();
        const events = captureBusEvents();
        el.toast('hello');
        const t = events.find((e) => e.type === CoreEvents.UI_TOAST_SHOW);
        expect(t.payload.i18n_key).to.equal('platform:hello');
    });

    it('toast с явным namespace в ключе не дописывает повторно', async () => {
        const el = await makeHost();
        const events = captureBusEvents();
        el.toast('crm:something');
        const t = events.find((e) => e.type === CoreEvents.UI_TOAST_SHOW);
        expect(t.payload.i18n_key).to.equal('crm:something');
    });
});

describe('PlatformElement: helper openModal / closeModal', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('openModal без kind — throw', async () => {
        const el = await makeHost();
        expect(() => el.openModal()).to.throw(/kind/);
        expect(() => el.openModal({})).to.throw(/kind/);
    });

    it('openModal с строкой → UI_MODAL_OPEN', async () => {
        const el = await makeHost();
        const events = captureBusEvents();
        el.openModal('platform.user_info', { userId: 'u1' });
        const ev = events.find((e) => e.type === CoreEvents.UI_MODAL_OPEN);
        expect(ev.payload).to.deep.equal({ kind: 'platform.user_info', props: { userId: 'u1' } });
    });

    it('openModal с классом и static modalKind', async () => {
        class Modal { static modalKind = 'platform.test_modal'; }
        const el = await makeHost();
        const events = captureBusEvents();
        el.openModal(Modal);
        const ev = events.find((e) => e.type === CoreEvents.UI_MODAL_OPEN);
        expect(ev.payload.kind).to.equal('platform.test_modal');
    });

    it('openModal с классом без static modalKind — throw', async () => {
        const el = await makeHost();
        class BadModal {}
        expect(() => el.openModal(BadModal)).to.throw(/modalKind/);
    });

    it('closeModal с пустой строкой — throw', async () => {
        const el = await makeHost();
        expect(() => el.closeModal('')).to.throw(/non-empty string/);
    });

    it('closeModal без аргумента → UI_MODAL_CLOSE с kind=null', async () => {
        const el = await makeHost();
        const events = captureBusEvents();
        el.closeModal();
        const ev = events.find((e) => e.type === CoreEvents.UI_MODAL_CLOSE);
        expect(ev.payload).to.deep.equal({ kind: null });
    });
});

describe('PlatformElement: helper navigate', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('navigate без routeKey — throw', async () => {
        const el = await makeHost();
        expect(() => el.navigate()).to.throw(/routeKey/);
        expect(() => el.navigate('')).to.throw(/routeKey/);
    });

    it('navigate с params не-объектом — throw', async () => {
        const el = await makeHost();
        expect(() => el.navigate('home', null)).to.throw(/params/);
    });

    it('navigate → ROUTER_NAVIGATE_REQUESTED', async () => {
        const el = await makeHost();
        const events = captureBusEvents();
        el.navigate('home', { x: 1 });
        const ev = events.find((e) => e.type === CoreEvents.ROUTER_NAVIGATE_REQUESTED);
        expect(ev.payload).to.deep.equal({ routeKey: 'home', params: { x: 1 } });
    });
});

describe('PlatformElement: helper copyToClipboard', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('требует text', async () => {
        const el = await makeHost();
        expect(() => el.copyToClipboard()).to.throw(/text/);
        expect(() => el.copyToClipboard(123)).to.throw(/text/);
    });

    it('требует options.success_i18n_key/error_i18n_key', async () => {
        const el = await makeHost();
        expect(() => el.copyToClipboard('x')).to.throw(/options/);
        expect(() => el.copyToClipboard('x', {})).to.throw(/success_i18n_key/);
        expect(() => el.copyToClipboard('x', { success_i18n_key: 'a' })).to.throw(/error_i18n_key/);
    });

    it('диспатчит UI_CLIPBOARD_COPY_REQUESTED', async () => {
        const el = await makeHost();
        const events = captureBusEvents();
        el.copyToClipboard('hello', { success_i18n_key: 'ok', error_i18n_key: 'err' });
        const ev = events.find((e) => e.type === CoreEvents.UI_CLIPBOARD_COPY_REQUESTED);
        expect(ev.payload).to.include({ text: 'hello', success_i18n_key: 'ok', error_i18n_key: 'err' });
    });
});

describe('PlatformElement: helper setLocale / setTheme / switchCompany', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('setLocale требует non-empty string', async () => {
        const el = await makeHost();
        expect(() => el.setLocale('')).to.throw(/locale/);
        expect(() => el.setLocale(null)).to.throw(/locale/);
    });

    it('setTheme принимает только dark|light', async () => {
        const el = await makeHost();
        expect(() => el.setTheme('cosmic')).to.throw(/dark.*light/);
    });

    it('switchCompany требует company_id', async () => {
        const el = await makeHost();
        expect(() => el.switchCompany('')).to.throw(/company_id/);
    });

    it('helpers выпускают correct CoreEvents', async () => {
        const el = await makeHost();
        const events = captureBusEvents();
        el.setLocale('en');
        el.setTheme('light');
        el.switchCompany('c1');
        expect(events.find((e) => e.type === CoreEvents.I18N_LOCALE_REQUESTED).payload).to.deep.equal({ locale: 'en' });
        expect(events.find((e) => e.type === CoreEvents.THEME_SET_REQUESTED).payload).to.deep.equal({ mode: 'light' });
        expect(events.find((e) => e.type === CoreEvents.AUTH_COMPANY_SWITCH_REQUESTED).payload).to.deep.equal({ company_id: 'c1' });
    });
});

describe('PlatformElement: useEvent', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('useEvent невалидный type — throw', async () => {
        const el = await makeHost();
        expect(() => el.useEvent('invalid', () => {})).to.throw();
    });

    it('useEvent: handler вызывается на dispatch', async () => {
        const el = await makeHost();
        let received = null;
        el.useEvent('test/foo/bar', (ev) => { received = ev; });
        getPlatformBus().dispatch('test/foo/bar', { x: 1 });
        expect(received.payload).to.deep.equal({ x: 1 });
    });
});

describe('PlatformElement: t (i18n)', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('t без key — throw', async () => {
        const el = await makeHost();
        expect(() => el.t('')).to.throw(/key required/);
    });

    it('t возвращает key, если bundle отсутствует', async () => {
        const el = await makeHost();
        // bundle для 'ru' не загружен — translate вернёт сам key
        expect(el.t('some.key')).to.equal('some.key');
    });
});
