/**
 * Browser: component kebab menu toggles schema boolean props via property-change.
 */

import { fixture, fixtureCleanup, html, expect, elementUpdated, oneEvent } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import flowsEn from '../../../../core/i18n/translations/en/flows.json' with { type: 'json' };
import '../../../../apps/flows/ui/components/interface-editor/flows-interface-component-menu.js';
import '@platform/lib/components/fields/platform-field.js';

function seedFlowsTranslations() {
    const bus = getPlatformBus();
    const prevEn = bus.getState().i18n.translations.en || {};
    bus.dispatch(
        CoreEvents.I18N_LOCALE_LOADED,
        { locale: 'en', bundle: { ...prevEn, flows: flowsEn } },
        { source: 'system' },
    );
    bus.dispatch(
        CoreEvents.I18N_LOCALE_CHANGED,
        { locale: 'en', default_namespace: 'flows' },
        { source: 'system' },
    );
}

describe('flows-interface-component-menu', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
        seedFlowsTranslations();
    });

    afterEach(() => {
        fixtureCleanup();
    });

    it('toggles Button disabled and emits property-change', async () => {
        const component = {
            component_id: 'btn_1',
            type: 'Button',
            properties: { label: 'Go', variant: 'primary', disabled: false },
            children: [],
        };
        const el = await fixture(html`
            <flows-interface-component-menu
                .x=${40}
                .y=${40}
                .component=${component}
                rootId="root"
                locale="en"
            ></flows-interface-component-menu>
        `);
        await elementUpdated(el);
        const menu = el.shadowRoot.querySelector('.menu');
        expect(menu).to.exist;
        const field = el.shadowRoot.querySelector('platform-field');
        expect(field).to.exist;
        setTimeout(() => {
            field.dispatchEvent(new CustomEvent('change', {
                detail: { value: true },
                bubbles: true,
                composed: true,
            }));
        });
        const event = await oneEvent(el, 'property-change');
        expect(event.detail).to.deep.equal({ name: 'disabled', value: true });
    });

    it('shows structural actions without quick props for Grid', async () => {
        const component = {
            component_id: 'grid_1',
            type: 'Grid',
            properties: {},
            children: [],
        };
        const el = await fixture(html`
            <flows-interface-component-menu
                .x=${10}
                .y=${10}
                .component=${component}
                rootId="root"
                locale="en"
            ></flows-interface-component-menu>
        `);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.options')).to.not.exist;
        const items = [...el.shadowRoot.querySelectorAll('.item')].map((node) => node.textContent.trim());
        expect(items).to.include('Duplicate');
        expect(items).to.include('Delete');
    });
});
