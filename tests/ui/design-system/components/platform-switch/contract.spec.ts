/**
 * platform-switch — L1 contract: регистрация, переключение, подпись как часть
 * зоны нажатия.
 */
import { fixture, html, expect, elementUpdated, oneEvent } from '../../../../frontend_core/browser/helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../../../../frontend_core/browser/helpers/reset.js';
import '@platform/lib/components/platform-switch.js';

describe('platform-switch', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('registers custom element', async () => {
        expect(customElements.get('platform-switch')).to.exist;
    });

    it('переключается по нажатию и отдаёт новое значение', async () => {
        const el = await fixture(html`<platform-switch label="Доступ по ссылке"></platform-switch>`);
        await elementUpdated(el);

        const changed = oneEvent(el, 'change');
        el.shadowRoot.querySelector('.switch').click();
        const event = await changed;

        expect(event.detail.value).to.equal(true);
        expect(el.checked).to.equal(true);
    });

    it('клик по подписи переключает так же, как по самому тумблеру', async () => {
        const el = await fixture(html`<platform-switch label="Доступ по ссылке"></platform-switch>`);
        await elementUpdated(el);

        el.shadowRoot.querySelector('.label').click();
        await elementUpdated(el);

        expect(el.checked).to.equal(true);
    });

    it('выключенный тумблер не реагирует ни на тумблер, ни на подпись', async () => {
        const el = await fixture(html`<platform-switch disabled label="Доступ по ссылке"></platform-switch>`);
        await elementUpdated(el);

        el.shadowRoot.querySelector('.switch').click();
        el.shadowRoot.querySelector('.label').click();
        await elementUpdated(el);

        expect(el.checked).to.equal(false);
    });
});
