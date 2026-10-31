/**
 * platform-bottom-sheet-stack: двухфазный close lifecycle для mobile shell.
 */

import { html as litHtml } from 'lit';
import { fixture, html, expect, elementUpdated, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import '@platform/lib/components/platform-bottom-sheet-stack.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { registerBottomSheetKind } from '@platform/lib/utils/bottom-sheet-registry.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import {q, qs, type TestEl} from '../helpers/dom.js';

let releaseCloseMotion: (() => void) | null = null;

class TestStackSheet extends PlatformElement {
    static override properties = {
        open: { type: Boolean, reflect: true },
        closing: { type: Boolean, reflect: true },
        _sheetId: { state: true },
        title: { type: String },
    };
    constructor() {
        super();
        (this as TestEl).open = false;
        (this as TestEl).closing = false;
        (this as TestEl).title = '';
        (this as TestEl).closeMotionRequested = false;
    }
    requestPlatformClose() {
        (this as TestEl).closeMotionRequested = true;
        (this as TestEl).closing = true;
        (this as TestEl).open = false;
        return new Promise<void>((resolve) => {
            releaseCloseMotion = resolve;
        });
    }
    override render() { return litHtml`<div class="s">${(this as TestEl).title}</div>`; }
}
customElements.define('frontend-core-stack-sheet', TestStackSheet);
registerBottomSheetKind('platform.stack_sheet_test', 'frontend-core-stack-sheet');

describe('platform-bottom-sheet-stack', () => {
    beforeEach(() => {
        releaseCloseMotion = null;
        resetPlatformState();
        bootstrapTestBus();
    });

    it('создаёт sheet по kind при UI_BOTTOM_SHEET_OPEN_REQUESTED', async () => {
        const stack = await fixture<TestEl>(html`<platform-bottom-sheet-stack></platform-bottom-sheet-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_BOTTOM_SHEET_OPEN_REQUESTED, {
            kind: 'platform.stack_sheet_test',
            props: { title: 'Sheet' },
        });
        await elementUpdated(stack);
        const sheet = qs(stack!, 'frontend-core-stack-sheet');
        expect(sheet).to.exist;
        expect(sheet.title).to.equal('Sheet');
        expect(sheet.open).to.be.true;
        expect(sheet._sheetId).to.match(/^bs_/);
    });

    it('close_requested держит sheet в DOM до завершения close motion', async () => {
        const stack = await fixture<TestEl>(html`<platform-bottom-sheet-stack></platform-bottom-sheet-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_BOTTOM_SHEET_OPEN_REQUESTED, {
            kind: 'platform.stack_sheet_test',
            props: {},
        });
        await elementUpdated(stack);
        const sheetId = qs(stack!, 'frontend-core-stack-sheet')._sheetId;
        getPlatformBus().dispatch(CoreEvents.UI_BOTTOM_SHEET_CLOSE_REQUESTED, { id: sheetId });
        await elementUpdated(stack);
        const closingSheet = qs(stack!, 'frontend-core-stack-sheet');
        expect(closingSheet).to.exist;
        expect(closingSheet.open).to.be.false;
        expect(closingSheet.closing).to.be.true;
        expect(closingSheet.closeMotionRequested).to.be.true;

        releaseCloseMotion?.();
        await waitUntil(
            () => q(stack!, 'frontend-core-stack-sheet') === null,
            'sheet removed after close motion',
        );
        expect((getPlatformBus().getState() as Record<string, any>).bottomSheets.stack.find((s: any) => s.id === sheetId)).to.be.undefined;
    });
});
