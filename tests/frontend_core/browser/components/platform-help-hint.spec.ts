/**
 * platform-help-hint — открытие по наведению и фокусу, содержимое, закрытие.
 */

import { fixture, html, expect, elementUpdated, aTimeout } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-help-hint.js';
import {q, qs, shadow, type TestEl} from '../helpers/dom.js';

async function mountHint(props: any = {}) {
    const el = await fixture<TestEl>(html`
        <platform-help-hint
            text=${props.text ?? 'Пояснение к полю'}
            summary=${props.summary ?? ''}
            details=${props.details ?? ''}
            doc-href=${props.docHref ?? ''}
            doc-label=${props.docLabel ?? ''}
            ?wide=${props.wide === true}
        ></platform-help-hint>
    `);
    await elementUpdated(el);
    return el;
}

function rootOf(el: any) {
    return qs(shadow(el), '.hint-root');
}

function bubbleOf(el: any) {
    return q(shadow(el), '.platform-help-hint-portal-bubble');
}

async function openHint(el: any) {
    rootOf(el).dispatchEvent(new MouseEvent('mouseenter', { bubbles: false }));
    await elementUpdated(el);
    await aTimeout(0);
    await elementUpdated(el);
}

describe('platform-help-hint', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    it('по умолчанию рисует кнопку и не показывает пузырёк', async () => {
        const el = await mountHint();

        expect(q(shadow(el), '.hint-btn')).to.exist;
        expect(bubbleOf(el)).to.be.null;
        expect(rootOf(el).getAttribute('aria-expanded')).to.equal('false');
    });

    it('наведение показывает пузырёк с текстом', async () => {
        const el = await mountHint({ text: 'Что это значит' });

        await openHint(el);

        expect(bubbleOf(el)).to.exist;
        expect(bubbleOf(el)!.textContent).to.contain('Что это значит');
        expect(rootOf(el).getAttribute('aria-expanded')).to.equal('true');
    });

    it('фокус на триггере тоже показывает пузырёк', async () => {
        const el = await mountHint();

        rootOf(el).dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
        await elementUpdated(el);
        await aTimeout(0);
        await elementUpdated(el);

        expect(bubbleOf(el)).to.exist;
    });

    it('summary и details выводятся отдельными блоками', async () => {
        const el = await mountHint({ summary: 'Кратко', details: 'Подробно про поле' });

        await openHint(el);

        expect(qs(shadow(el), '.platform-help-hint-portal-summary').textContent.trim())
            .to.equal('Кратко');
        expect(qs(shadow(el), '.platform-help-hint-portal-body').textContent.trim())
            .to.equal('Подробно про поле');
    });

    it('ссылка на документацию открывается в новой вкладке', async () => {
        const el = await mountHint({ docHref: '/guide', docLabel: 'Документация' });

        await openHint(el);

        const link = qs(shadow(el), '.platform-help-hint-portal-link');
        expect(link).to.exist;
        expect(link.textContent.trim()).to.equal('Документация');
        expect(link.getAttribute('target')).to.equal('_blank');
        expect(link.getAttribute('rel')).to.contain('noopener');
    });

    it('со ссылкой пузырёк получает роль диалога, без неё — подсказки', async () => {
        const withLink = await mountHint({ docHref: '/guide', docLabel: 'Документация' });
        await openHint(withLink);
        expect(qs(shadow(withLink), 'platform-popover').getAttribute('role'))
            .to.equal('dialog');

        const plain = await mountHint();
        await openHint(plain);
        expect(qs(shadow(plain), 'platform-popover').getAttribute('role'))
            .to.equal('tooltip');
    });

    it('широкий режим помечается модификатором', async () => {
        const el = await mountHint({ wide: true, text: '{"json": true}' });

        await openHint(el);

        expect(bubbleOf(el)!.classList.contains('platform-help-hint-portal-bubble--wide')).to.be.true;
    });

    it('Escape закрывает пузырёк', async () => {
        const el = await mountHint();
        await openHint(el);

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        await elementUpdated(el);

        expect(bubbleOf(el)).to.be.null;
    });

    it('уход курсора закрывает пузырёк с задержкой', async () => {
        const el = await mountHint();
        await openHint(el);

        rootOf(el).dispatchEvent(new MouseEvent('mouseleave', { bubbles: false }));
        await aTimeout(260);
        await elementUpdated(el);

        expect(bubbleOf(el)).to.be.null;
    });

    it('пузырёк показывается в top layer', async () => {
        const el = await mountHint();
        await openHint(el);

        expect(qs(shadow(el), 'platform-popover').matches(':popover-open')).to.be.true;
    });
});
