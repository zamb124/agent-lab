/**
 * platform-field-enum внутри glass-modal: список должен открываться по focus/chevron.
 * Регресс: popover в top layer не показывался в trigger editor.
 */

import { fixture, html, expect, elementUpdated, aTimeout } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-modal-stack.js';
import '@platform/lib/components/fields/platform-field.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';

const ENUM_VALUES = [
    { value: 'flows/flow/updated', label: 'flows/flow/updated — Flow updated' },
    { value: 'crm/entity/created', label: 'crm/entity/created — Entity created' },
    { value: 'sync/message/created', label: 'sync/message/created — Message created' },
];

class EnumHostModal extends PlatformFormModal {
    static modalKind = 'platform.enum_host_test';
    static i18nNamespace = 'platform';

    renderBody() {
        return html`
            <platform-field
                type="enum"
                mode="edit"
                .value=${''}
                .config=${{ values: ENUM_VALUES }}
            ></platform-field>
        `;
    }
}

if (!customElements.get('frontend-core-enum-host-modal')) {
    customElements.define('frontend-core-enum-host-modal', EnumHostModal);
    registerModalKind(EnumHostModal.modalKind, 'frontend-core-enum-host-modal');
}

function enumParts(modal) {
    const field = modal.shadowRoot.querySelector('platform-field');
    expect(field, 'platform-field').to.exist;
    const pfEnum = field.shadowRoot.querySelector('platform-field-enum');
    expect(pfEnum, 'platform-field-enum').to.exist;
    const input = pfEnum.shadowRoot.querySelector('input.field-pill-enum-input');
    const chevron = pfEnum.shadowRoot.querySelector('.field-pill-enum-chevron');
    const popover = pfEnum.shadowRoot.querySelector('platform-popover');
    return { field, pfEnum, input, chevron, popover };
}

describe('platform-field-enum inside glass-modal', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus();
    });

    async function openModal() {
        const stack = await fixture(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, {
            kind: EnumHostModal.modalKind,
            props: {},
        });
        await elementUpdated(stack);
        const modal = document.querySelector('frontend-core-enum-host-modal');
        expect(modal, 'modal mounted').to.exist;
        await elementUpdated(modal);
        return modal;
    }

    it('focus открывает popover со всеми опциями', async () => {
        const modal = await openModal();
        const { input, pfEnum, popover } = enumParts(modal);

        input.focus();
        await elementUpdated(pfEnum);
        await elementUpdated(popover);
        await aTimeout(50);

        expect(pfEnum._listOpen, '_listOpen after focus').to.equal(true);
        expect(popover.open, 'popover.open').to.equal(true);
        expect(popover.matches(':popover-open'), ':popover-open').to.equal(true);

        const rows = pfEnum.shadowRoot.querySelectorAll('[data-enum-value]');
        expect(rows.length, 'options visible').to.be.at.least(ENUM_VALUES.length);
        const display = getComputedStyle(popover).display;
        expect(display, 'popover display').to.not.equal('none');
        const rect = popover.getBoundingClientRect();
        expect(rect.height, 'popover height').to.be.greaterThan(8);
        expect(rect.width, 'popover width').to.be.greaterThan(8);
    });

    it('chevron открывает полный список', async () => {
        const modal = await openModal();
        const { chevron, pfEnum, popover } = enumParts(modal);

        chevron.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
        chevron.click();
        await elementUpdated(pfEnum);
        await elementUpdated(popover);
        await aTimeout(50);

        expect(pfEnum._listOpen, '_listOpen after chevron').to.equal(true);
        expect(popover.matches(':popover-open'), ':popover-open after chevron').to.equal(true);
        expect(popover.anchor, 'anchor set before open').to.be.instanceOf(HTMLElement);

        const values = Array.from(pfEnum.shadowRoot.querySelectorAll('[data-enum-value]'))
            .map((li) => li.getAttribute('data-enum-value'));
        expect(values).to.include('flows/flow/updated');
        expect(values).to.include('crm/entity/created');
        expect(values).to.include('');

        const rect = popover.getBoundingClientRect();
        const anchorRect = popover.anchor.getBoundingClientRect();
        expect(rect.top, 'list below or near anchor').to.be.at.least(anchorRect.top - 8);
        expect(Math.abs(rect.left - anchorRect.left), 'aligned to anchor').to.be.at.most(24);
    });

    it('повторный config object не закрывает открытый список', async () => {
        const modal = await openModal();
        const { input, field, pfEnum, popover } = enumParts(modal);

        input.focus();
        await elementUpdated(pfEnum);
        expect(popover.matches(':popover-open')).to.equal(true);

        field.config = { values: [...ENUM_VALUES] };
        field.requestUpdate();
        await elementUpdated(field);
        await elementUpdated(pfEnum);
        await aTimeout(50);

        expect(pfEnum._listOpen, 'stays open after config replace').to.equal(true);
        expect(popover.matches(':popover-open'), 'popover stays open').to.equal(true);
    });

    it('список остаётся открытым 350ms после focus (нет мгновенного dismiss)', async () => {
        const modal = await openModal();
        const { input, pfEnum, popover } = enumParts(modal);

        input.focus();
        await elementUpdated(pfEnum);
        await aTimeout(350);

        expect(pfEnum._listOpen, '_listOpen still true').to.equal(true);
        expect(popover.matches(':popover-open'), 'still :popover-open').to.equal(true);
    });
});
