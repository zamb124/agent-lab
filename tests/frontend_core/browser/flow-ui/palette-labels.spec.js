/**
 * The insert panel shows what the author gets, not the catalog type id: a Columns
 * preset reads as a row split into columns, and search works on the visible name.
 */

import { elementUpdated, expect, fixture, fixtureCleanup, html } from '../helpers/render.js';
import { bootstrapTestBus, resetPlatformState } from '../helpers/reset.js';
import { CoreEvents, getPlatformBus } from '@platform/lib/events/index.js';
import flowsRu from '../../../../core/i18n/translations/ru/flows.json' with { type: 'json' };
import '../../../../apps/flows/ui/components/interface-editor/flows-interface-palette.js';

function seedLocale(locale, bundle) {
    const bus = getPlatformBus();
    bus.dispatch(
        CoreEvents.I18N_LOCALE_LOADED,
        { locale, bundle: { flows: bundle } },
        { source: 'system' },
    );
    bus.dispatch(
        CoreEvents.I18N_LOCALE_CHANGED,
        { locale, default_namespace: 'flows' },
        { source: 'system' },
    );
}

function labels(palette) {
    return [...palette.shadowRoot.querySelectorAll('.item span')].map((node) => node.textContent.trim());
}

describe('flow-ui palette labels', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
        seedLocale('ru', flowsRu);
    });
    afterEach(() => fixtureCleanup());

    it('names entries in the active locale instead of showing type ids', async () => {
        const palette = await fixture(html`<flows-interface-palette></flows-interface-palette>`);
        await elementUpdated(palette);
        const visible = labels(palette);
        expect(visible).to.include('Карточка');
        expect(visible).to.include('Секция');
        expect(visible).to.include('Поле ввода');
        expect(visible).to.not.include('Card');
        expect(visible).to.not.include('TextField');
    });

    it('explains that a Columns preset builds a row of columns', async () => {
        const palette = await fixture(html`<flows-interface-palette></flows-interface-palette>`);
        await elementUpdated(palette);
        const visible = labels(palette);
        expect(visible).to.include('Ряд: 2 колонки');
        expect(visible).to.include('Ряд: 3 колонки');
        expect(visible).to.include('Ряд: 4 колонки');
        expect(visible).to.not.include('Columns2');
    });

    it('keeps the type id in the tooltip for orientation', async () => {
        const palette = await fixture(html`<flows-interface-palette></flows-interface-palette>`);
        await elementUpdated(palette);
        const titles = [...palette.shadowRoot.querySelectorAll('.item')]
            .map((node) => node.getAttribute('title'));
        expect(titles).to.include('Ряд: 2 колонки · Columns2');
        expect(titles).to.include('Карточка · Card');
    });

    it('searches by the visible name', async () => {
        const palette = await fixture(html`<flows-interface-palette></flows-interface-palette>`);
        await elementUpdated(palette);
        palette.query = 'колонки';
        await elementUpdated(palette);
        const visible = labels(palette);
        expect(visible).to.deep.equal(['Ряд: 2 колонки', 'Ряд: 3 колонки', 'Ряд: 4 колонки']);
    });
});
