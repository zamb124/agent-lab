/**
 * platform-icon: загрузка через события icon/ui_asset/load_requested.
 */

import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-icon.js';
import { getPlatformBus } from '@platform/lib/events/index.js';
import { ICON_EVENTS } from '@platform/lib/events/reducers/icon.js';

describe('platform-icon', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('диспатчит UI_LOAD_REQUESTED при появлении name', async () => {
        const events = [];
        getPlatformBus().subscribeAny((e) => events.push(e));
        await fixture(html`<platform-icon name="plus"></platform-icon>`);
        const req = events.find((e) => e.type === ICON_EVENTS.UI_LOAD_REQUESTED);
        expect(req).to.exist;
        expect(req.payload.name).to.equal('plus');
    });

    it('после UI_LOADED отображает svg', async () => {
        const el = await fixture(html`<platform-icon name="plus"></platform-icon>`);
        getPlatformBus().dispatch(ICON_EVENTS.UI_LOADED, { name: 'plus', svg: '<svg id="x"></svg>' });
        await elementUpdated(el);
        expect(el.shadowRoot.innerHTML).to.contain('id="x"');
    });

    it('size меняет CSS-переменную', async () => {
        const el = await fixture(html`<platform-icon name="plus" size="32"></platform-icon>`);
        await elementUpdated(el);
        expect(el.style.getPropertyValue('--icon-size')).to.equal('32px');
    });
});
