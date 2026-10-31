/**
 * platform-icon: загрузка через события icon/ui_asset/load_requested.
 */

import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-icon.js';
import { getPlatformBus } from '@platform/lib/events/index.js';
import { ICON_EVENTS } from '@platform/lib/events/reducers/icon.js';
import { shadow, type TestEl } from '../helpers/dom.js';

describe('platform-icon', () => {
    beforeEach(() => { resetPlatformState(); bootstrapTestBus(); });

    it('диспатчит UI_LOAD_REQUESTED при появлении name', async () => {
        const events: any[] = [];
        getPlatformBus().subscribeAny((e: any) => events.push(e));
        await fixture<TestEl>(html`<platform-icon name="plus"></platform-icon>`);
        const req = events.find((e) => e.type === ICON_EVENTS.UI_LOAD_REQUESTED);
        expect(req).to.exist;
        expect(req.payload.name).to.equal('plus');
    });

    it('после UI_LOADED отображает svg', async () => {
        const el = await fixture<TestEl>(html`<platform-icon name="plus"></platform-icon>`);
        getPlatformBus().dispatch(ICON_EVENTS.UI_LOADED, { name: 'plus', svg: '<svg id="x"></svg>' });
        await elementUpdated(el);
        expect(shadow(el).innerHTML).to.contain('id="x"');
    });

    it('переключение name на уже кешированную иконку отображает новый svg', async () => {
        const bus = getPlatformBus();
        bus.dispatch(ICON_EVENTS.UI_LOADED, { name: 'plus', svg: '<svg id="plus"></svg>' });
        bus.dispatch(ICON_EVENTS.UI_LOADED, { name: 'minus', svg: '<svg id="minus"></svg>' });
        const el = await fixture<TestEl>(html`<platform-icon name="plus"></platform-icon>`);
        await elementUpdated(el);
        expect(shadow(el).innerHTML).to.contain('id="plus"');
        el.name = 'minus';
        await elementUpdated(el);
        expect(shadow(el).innerHTML).to.contain('id="minus"');
        expect(shadow(el).innerHTML).to.not.contain('id="plus"');
    });

    it('size меняет CSS-переменную', async () => {
        const el = await fixture<TestEl>(html`<platform-icon name="plus" size="32"></platform-icon>`);
        await elementUpdated(el);
        expect(el.style.getPropertyValue('--icon-size')).to.equal('32px');
    });
});
