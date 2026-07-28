/**
 * platform-resizable-split — перетаскивание границы, клавиатура, сохранение ширины.
 */

import { fixture, html, expect, oneEvent, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';
import '@platform/lib/components/platform-resizable-split.js';

const STORAGE_KEY = platformStorageKey('wiki', 'split.tree');

async function mountSplit(props = {}) {
    const el = await fixture(html`
        <platform-resizable-split
            storage-key=${props.storageKey ?? ''}
            storage-scope="wiki"
            side=${props.side ?? 'left'}
            min-size=${props.minSize ?? 180}
            max-size=${props.maxSize ?? 480}
        >
            <nav slot="side">дерево</nav>
            <main>контент</main>
        </platform-resizable-split>
    `);
    await elementUpdated(el);
    return el;
}

function handleOf(el) {
    return el.shadowRoot.querySelector('.handle');
}

function sideWidth(el) {
    return el.shadowRoot.querySelector('.side').getBoundingClientRect().width;
}

describe('platform-resizable-split', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
        window.localStorage.removeItem(STORAGE_KEY);
    });

    it('рисует обе панели и разделитель', async () => {
        const el = await mountSplit();

        expect(el.shadowRoot.querySelector('.side')).to.exist;
        expect(el.shadowRoot.querySelector('.main')).to.exist;
        expect(handleOf(el).getAttribute('role')).to.equal('separator');
    });

    it('ширина боковой панели соответствует size', async () => {
        const el = await mountSplit();
        el.size = 300;
        await elementUpdated(el);

        expect(Math.round(sideWidth(el))).to.equal(300);
    });

    it('перетаскивание меняет ширину', async () => {
        const el = await mountSplit();
        el.size = 260;
        await elementUpdated(el);

        handleOf(el).dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: 300 }));
        window.dispatchEvent(new PointerEvent('pointermove', { clientX: 360 }));
        await elementUpdated(el);

        expect(el.size).to.equal(320);
    });

    it('перетаскивание не выходит за пределы min и max', async () => {
        const el = await mountSplit({ minSize: 200, maxSize: 400 });
        el.size = 260;
        await elementUpdated(el);

        handleOf(el).dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: 300 }));
        window.dispatchEvent(new PointerEvent('pointermove', { clientX: 900 }));
        await elementUpdated(el);
        expect(el.size).to.equal(400);

        window.dispatchEvent(new PointerEvent('pointermove', { clientX: 0 }));
        await elementUpdated(el);
        expect(el.size).to.equal(200);
    });

    it('перетаскивание эмитит split-resize', async () => {
        const el = await mountSplit();
        el.size = 260;
        await elementUpdated(el);

        const resized = oneEvent(el, 'split-resize');
        handleOf(el).dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: 300 }));
        window.dispatchEvent(new PointerEvent('pointermove', { clientX: 330 }));
        const event = await resized;

        expect(event.detail.size).to.equal(290);
    });

    it('стрелки двигают границу с клавиатуры', async () => {
        const el = await mountSplit();
        el.size = 260;
        await elementUpdated(el);

        handleOf(el).dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
        await elementUpdated(el);
        expect(el.size).to.equal(276);

        handleOf(el).dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
        await elementUpdated(el);
        expect(el.size).to.equal(260);
    });

    it('для правой панели направление стрелок зеркальное', async () => {
        const el = await mountSplit({ side: 'right' });
        el.size = 260;
        await elementUpdated(el);

        handleOf(el).dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
        await elementUpdated(el);

        expect(el.size).to.equal(276);
    });

    it('ширина сохраняется и восстанавливается по storage-key', async () => {
        const el = await mountSplit({ storageKey: 'tree' });
        el.size = 260;
        await elementUpdated(el);

        handleOf(el).dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: 300 }));
        window.dispatchEvent(new PointerEvent('pointermove', { clientX: 340 }));
        window.dispatchEvent(new PointerEvent('pointerup', {}));
        await elementUpdated(el);

        expect(window.localStorage.getItem(STORAGE_KEY)).to.equal('300');

        const restored = await mountSplit({ storageKey: 'tree' });
        expect(restored.size).to.equal(300);
    });

    it('без storage-key ширина не сохраняется', async () => {
        const el = await mountSplit();
        el.size = 260;
        await elementUpdated(el);

        handleOf(el).dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: 300 }));
        window.dispatchEvent(new PointerEvent('pointermove', { clientX: 340 }));
        window.dispatchEvent(new PointerEvent('pointerup', {}));
        await elementUpdated(el);

        expect(window.localStorage.getItem(STORAGE_KEY)).to.equal(null);
    });

    it('свёрнутое состояние сжимает панель до collapsed-size', async () => {
        const el = await mountSplit({ minSize: 200 });
        el.size = 300;
        el.collapsedSize = 72;
        el.collapsed = true;
        await elementUpdated(el);

        expect(Math.round(sideWidth(el))).to.equal(72);
    });

    it('разворачивание возвращает прежнюю ширину', async () => {
        const el = await mountSplit();
        el.size = 320;
        el.collapsed = true;
        await elementUpdated(el);

        el.collapsed = false;
        await elementUpdated(el);

        expect(el.size).to.equal(320);
        expect(Math.round(sideWidth(el))).to.equal(320);
    });

    it('в свёрнутом виде границу не перетащить', async () => {
        const el = await mountSplit();
        el.size = 300;
        el.collapsed = true;
        await elementUpdated(el);

        handleOf(el).dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, clientX: 72 }));
        window.dispatchEvent(new PointerEvent('pointermove', { clientX: 400 }));
        handleOf(el).dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
        await elementUpdated(el);

        expect(el.size).to.equal(300);
    });

    it('значения доступности отражают текущую ширину', async () => {
        const el = await mountSplit({ minSize: 200, maxSize: 400 });
        el.size = 240;
        await elementUpdated(el);

        const handle = handleOf(el);
        expect(handle.getAttribute('aria-valuenow')).to.equal('240');
        expect(handle.getAttribute('aria-valuemin')).to.equal('200');
        expect(handle.getAttribute('aria-valuemax')).to.equal('400');
    });
});
