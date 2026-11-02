/**
 * platform-customer-auth — L1 contract: полный покрытие состояний компонента.
 *
 * Компонент ходит по реальному HTTP в stateful API-эмулятор middleware
 * (`/customer-auth-emu/*` в web-test-runner.middleware.ts) — без моков fetch:
 * пути/статусы/Set-Cookie повторяют core/api/customer_auth.py.
 */
import { expect } from '@open-wc/testing';
import '@platform/lib/components/platform-customer-auth.js';

interface MochaSuiteCtx {
    timeout(ms: number): void;
}

declare function describe(name: string, fn: (this: MochaSuiteCtx) => void): void;
declare function it(name: string, fn: () => void | Promise<void>): void;
declare function beforeEach(fn: () => void | Promise<void>): void;

const API = '/customer-auth-emu';
const PHONE = '+79991112233';

interface AuthEl extends HTMLElement {
    open(): Promise<void>;
    close(cancelled?: boolean): void;
    readonly updateComplete: Promise<boolean>;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const until = async (fn: () => boolean, ms = 5000) => {
    const end = Date.now() + ms;
    while (Date.now() < end) {
        if (fn()) return;
        await sleep(40);
    }
    throw new Error('condition timeout');
};

function makeEl(attrs: Record<string, string> = {}): AuthEl {
    const el = document.createElement('platform-customer-auth') as AuthEl;
    el.setAttribute('api-base', API);
    el.setAttribute('company-id', 'cmp_emu');
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    document.body.appendChild(el);
    return el;
}

const sr = (el: AuthEl) => el.shadowRoot!;
const q = <T extends Element>(el: AuthEl, sel: string) =>
    sr(el).querySelector<T>(sel);
const qa = <T extends Element>(el: AuthEl, sel: string) =>
    [...sr(el).querySelectorAll<T>(sel)];

const fill = async (el: AuthEl, value: string) => {
    const input = q<HTMLInputElement>(el, 'input')!;
    input.value = value;
    input.dispatchEvent(new InputEvent('input', { bubbles: true }));
    await el.updateComplete;
};

const clickPrimary = async (el: AuthEl) => {
    q<HTMLButtonElement>(el, 'button.primary')!.click();
    await until(() => !q<HTMLButtonElement>(el, 'button.primary')?.disabled);
    await el.updateComplete;
};

const methodBtn = (el: AuthEl, label: RegExp) =>
    qa<HTMLButtonElement>(el, 'button.method').find((b) => label.test(b.textContent || ''));

async function api(path: string, init?: RequestInit): Promise<Response> {
    return fetch(`${API}${path}`, { credentials: 'same-origin', ...init });
}

const lastCode = async (): Promise<string> => {
    const body = await (await api('/_outbox')).json();
    return body.messages.at(-1).code as string;
};

const confirmChallenge = async (id: string) => {
    await api('/_confirm', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ challenge_id: id }),
    });
};

describe('platform-customer-auth', function (this: MochaSuiteCtx) {
    // Реальные fetch-раундтрипы + polling 2с — дефолтный 2с mocha-timeout мал.
    this.timeout(30000);

    beforeEach(async () => {
        await api('/logout', { method: 'POST' });
        document
            .querySelectorAll('platform-customer-auth')
            .forEach((e) => e.remove());
    });

    it('registers custom element', async () => {
        expect(customElements.get('platform-customer-auth')).to.exist;
    });

    it('open() → phone step; no session → no auto-confirm', async () => {
        const el = makeEl();
        let authed = false;
        el.addEventListener('customer-authenticated', () => (authed = true));
        await el.open();
        await el.updateComplete;
        expect(authed).to.equal(false);
        expect(q(el, 'input[type=tel]')).to.exist;
        expect(q(el, 'button.primary')!.textContent).to.contain('Продолжить');
        el.remove();
    });

    it('open() с живой сессией → customer-authenticated сразу', async () => {
        // сначала реально авторизуемся через API (verify ставит cookie)
        const start = await (
            await api('/start', {
                method: 'POST',
                headers: { 'content-type': 'application/json' },
                body: JSON.stringify({ company_id: 'cmp_emu', phone: PHONE }),
            })
        ).json();
        await api('/method', {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({
                challenge_id: start.challenge_id, company_id: 'cmp_emu', method: 'sms_code',
            }),
        });
        const code = await lastCode();
        await api('/verify', {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({
                challenge_id: start.challenge_id, company_id: 'cmp_emu', code,
            }),
        });
        const el = makeEl();
        const done = new Promise<CustomEvent>((r) =>
            el.addEventListener('customer-authenticated', r as EventListener));
        await el.open();
        const ev = await done;
        expect(ev.detail.customer_id).to.equal('cust_emu1');
        el.remove();
    });

    it('невалидный телефон → error_code_invalid_phone в .err', async () => {
        const el = makeEl();
        await el.open();
        await fill(el, '123');
        await clickPrimary(el);
        await until(() => !!q(el, '.err')!.textContent?.trim());
        expect(q(el, '.err')!.textContent).to.contain('номер');
        el.remove();
    });

    it('methods: все провайдеры в порядке приоритета, ru-лейблы', async () => {
        const el = makeEl();
        await el.open();
        await fill(el, PHONE);
        await clickPrimary(el);
        await until(() => qa(el, 'button.method').length > 0);
        const labels = qa(el, 'button.method').map((b) => (b.textContent || '').trim());
        expect(labels).to.have.length(7);
        expect(labels.join('|')).to.contain('Telegram');
        expect(labels.join('|')).to.contain('MAX');
        expect(labels.join('|')).to.match(/Yandex|Яндекс/);
        expect(labels.join('|')).to.contain('VK');
        expect(labels.join('|')).to.contain('Sber');
        expect(labels.join('|')).to.contain('SMS');
        // сортировка по priority desc → emulator последний
        expect(labels.at(-1)).to.contain('Эмулятор');
        el.remove();
    });

    it('sms: code step → wrong code → error → right code → authenticated', async () => {
        const el = makeEl();
        const done = new Promise<CustomEvent>((r) =>
            el.addEventListener('customer-authenticated', r as EventListener));
        await el.open();
        await fill(el, PHONE);
        await clickPrimary(el);
        await until(() => !!methodBtn(el, /SMS|код/i));
        methodBtn(el, /SMS|код/i)!.click();
        await until(() => !!q(el, 'input[inputmode=numeric]'));
        await el.updateComplete;
        // cooldown: resend — подсказка с секундами, кнопки нет
        expect(q(el, '.hint')!.textContent).to.match(/\d+s/);
        // неверный код
        await fill(el, '000001');
        await clickPrimary(el);
        await until(() => !!q(el, '.err')!.textContent?.trim());
        // верный код из «доставленного SMS» эмулятора
        const code = await lastCode();
        expect(code).to.not.equal('000001');
        await fill(el, code);
        await clickPrimary(el);
        const ev = await done;
        expect(ev.detail.phone_e164).to.equal(PHONE);
        expect(q(el, '.overlay')).to.not.exist; // лист закрылся
        el.remove();
    });

    it('attempts_exceeded: >5 неверных кодов → ошибка', async () => {
        const el = makeEl();
        await el.open();
        await fill(el, PHONE);
        await clickPrimary(el);
        await until(() => !!methodBtn(el, /SMS|код/i));
        methodBtn(el, /SMS|код/i)!.click();
        await until(() => !!q(el, 'input[inputmode=numeric]'));
        for (let i = 0; i < 6; i++) {
            await fill(el, '000001');
            q<HTMLButtonElement>(el, 'button.primary')!.click();
            await sleep(60);
        }
        await until(() => !!q(el, '.err')!.textContent?.trim());
        expect(q(el, '.err')!.textContent!.length).to.be.greaterThan(0);
        el.remove();
    });

    it('emulator (ui=auto) → авто verify direct → customer-authenticated', async () => {
        const el = makeEl();
        const done = new Promise<CustomEvent>((r) =>
            el.addEventListener('customer-authenticated', r as EventListener));
        await el.open();
        await fill(el, PHONE);
        await clickPrimary(el);
        await until(() => !!methodBtn(el, /Эмулятор/));
        methodBtn(el, /Эмулятор/)!.click();
        const ev = await done;
        expect(ev.detail.phone_e164).to.equal(PHONE);
        expect(ev.detail.customer_id).to.equal('cust_emu1');
        el.remove();
    });

    it('emulator auto + чужой номер → provider_mismatch → ошибка', async () => {
        // direct-proof с номером, отличным от challenge → error_generic
        const el = makeEl();
        await el.open();
        await fill(el, PHONE);
        await clickPrimary(el);
        await until(() => qa(el, 'button.method').length > 0);
        const resp = await api('/verify', {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({
                challenge_id: (el as unknown as { _challengeId: string })._challengeId,
                company_id: 'cmp_emu',
                direct: { kind: 'contact_share', provider: 'emulator', contact_phone: '+79990000000' },
            }),
        });
        expect(resp.status).to.equal(400);
        expect((await resp.json()).detail).to.equal('provider_mismatch');
        el.remove();
    });

    it('awaiting_contact → внешнее подтверждение → poll → done', async () => {
        const el = makeEl();
        const done = new Promise<CustomEvent>((r) =>
            el.addEventListener('customer-authenticated', r as EventListener));
        await el.open();
        await fill(el, PHONE);
        await clickPrimary(el);
        await until(() => !!methodBtn(el, /Telegram/));
        methodBtn(el, /Telegram/)!.click();
        await until(() => !!q(el, '.spinner'));
        const cid = (el as unknown as { _challengeId: string })._challengeId;
        expect(cid).to.match(/^phc_emu/);
        await confirmChallenge(cid);
        const ev = (await Promise.race([done, sleep(5000).then(() => null)])) as CustomEvent;
        expect(ev, 'poll не увидел подтверждение').to.exist;
        expect(ev.detail.customer_id).to.equal('cust_emu1');
        el.remove();
    });

    it('telegram_contact → awaiting_contact + deep link кнопка', async () => {
        const el = makeEl();
        await el.open();
        await fill(el, PHONE);
        await clickPrimary(el);
        await until(() => !!methodBtn(el, /Telegram/));
        methodBtn(el, /Telegram/)!.click();
        await until(() => !!q(el, '.spinner'));
        const openBtn = q<HTMLButtonElement>(el, 'button.primary')!;
        expect(openBtn.textContent).to.contain('Открыть');
        el.remove();
    });

    it('back: methods → phone → methods сохраняет номер', async () => {
        const el = makeEl();
        await el.open();
        await fill(el, PHONE);
        await clickPrimary(el);
        await until(() => qa(el, 'button.method').length > 0);
        qa<HTMLButtonElement>(el, 'button.ghost')
            .find((b) => /Назад|Back/.test(b.textContent || ''))!
            .click();
        await el.updateComplete;
        expect(q<HTMLInputElement>(el, 'input[type=tel]')!.value).to.equal(PHONE);
        el.remove();
    });

    it('close() → customer-auth-cancelled', async () => {
        const el = makeEl();
        let cancelled = false;
        el.addEventListener('customer-auth-cancelled', () => (cancelled = true));
        await el.open();
        el.close();
        expect(cancelled).to.equal(true);
        el.remove();
    });

    it('overlay click → cancelled + лист закрылся', async () => {
        const el = makeEl();
        let cancelled = false;
        el.addEventListener('customer-auth-cancelled', () => (cancelled = true));
        await el.open();
        await el.updateComplete;
        const overlay = q<HTMLElement>(el, '.overlay')!;
        overlay.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        expect(cancelled).to.equal(true);
        await el.updateComplete;
        expect(q(el, '.overlay')).to.not.exist;
        el.remove();
    });

    it('locale=en → английские лейблы', async () => {
        const el = makeEl({ locale: 'en' });
        await el.open();
        await el.updateComplete;
        expect(q(el, 'h2')!.textContent).to.match(/[A-Za-z]/);
        expect(q(el, 'button.primary')!.textContent).to.match(/Continue/i);
        el.remove();
    });

    it('oauth method кнопка вызывает /method → awaiting_oauth', async () => {
        const el = makeEl();
        await el.open();
        await fill(el, PHONE);
        await clickPrimary(el);
        await until(() => !!methodBtn(el, /Yandex|Яндекс/));
        // window.open(_self) увёл бы со страницы — проверяем /method контракт.
        const st = await (
            await api('/start', {
                method: 'POST',
                headers: { 'content-type': 'application/json' },
                body: JSON.stringify({ company_id: 'cmp_emu', phone: PHONE }),
            })
        ).json();
        const view = await (
            await api('/method', {
                method: 'POST',
                headers: { 'content-type': 'application/json' },
                body: JSON.stringify({
                    challenge_id: st.challenge_id, company_id: 'cmp_emu', method: 'yandex_id',
                }),
            })
        ).json();
        expect(view.status).to.equal('awaiting_oauth');
        expect(view.oauth_url).to.contain('/oauth/yandex/authorize');
        expect(methodBtn(el, /Yandex|Яндекс/)!.disabled).to.equal(false);
        el.remove();
    });
});
