/**
 * flows-canvas-help-modal — справка по горячим клавишам и UX-фишкам канваса.
 *
 * Показывает таблицу keyboard shortcuts (canvas.hotkeys.*) и пояснения
 * фишек: drag, multi-select, pan, sticky notes, minimap, smart guides.
 */

import { html, css } from 'lit';
import { PlatformLightModal } from '@platform/lib/components/glass-light-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';

const SHORTCUTS = Object.freeze([
    { keys: 'Space + Drag',   labelKey: 'canvas.hotkeys.space_drag' },
    { keys: 'Ctrl/Cmd + A',   labelKey: 'canvas.hotkeys.select_all' },
    { keys: 'Ctrl/Cmd + D',   labelKey: 'canvas.hotkeys.duplicate' },
    { keys: 'Del / Backspace', labelKey: 'canvas.hotkeys.delete' },
    { keys: 'F2 / Enter',     labelKey: 'canvas.hotkeys.rename' },
    { keys: 'Esc',            labelKey: 'canvas.hotkeys.clear_selection' },
    { keys: '↑ ↓ ← →',        labelKey: 'canvas.hotkeys.arrows' },
    { keys: 'Shift + S',      labelKey: 'canvas.hotkeys.sticky_note' },
    { keys: 'Shift + Drag',   labelKey: 'canvas.hotkeys.box_select' },
    { keys: 'Ctrl + Wheel',   labelKey: 'canvas.hotkeys.zoom' },
]);

export class FlowsCanvasHelpModal extends PlatformLightModal {
    static modalKind = 'flows.canvas_help';
    static i18nNamespace = 'flows';

    static styles = [
        ...(PlatformLightModal.styles ? [PlatformLightModal.styles] : []),
        css`
            :host {
                --modal-width: min(560px, calc(100vw - 32px));
            }
            .help-section { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3); }
            .section-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                text-transform: uppercase;
                letter-spacing: 0.06em;
            }
            .row {
                display: grid;
                grid-template-columns: 140px 1fr;
                gap: var(--space-3);
                align-items: center;
                font-size: var(--text-sm);
            }
            kbd {
                display: inline-block;
                padding: 2px 6px;
                border-radius: var(--radius-sm);
                background: var(--glass-solid-medium);
                border: 1px solid var(--border-subtle);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                color: var(--text-primary);
            }
            .feature {
                display: flex; flex-direction: column; gap: 2px;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                background: var(--glass-tint-subtle);
            }
            .feature-title { font-weight: var(--font-semibold); color: var(--text-primary); font-size: var(--text-sm); }
            .feature-hint { font-size: var(--text-xs); color: var(--text-secondary); }
        `,
    ];

    renderHeader() {
        return html`<h3>${this.t('canvas.help.title')}</h3>`;
    }

    renderBody() {
        return html`
            <div class="help-section">
                <div class="section-title">${this.t('canvas.help.section_shortcuts')}</div>
                ${SHORTCUTS.map((s) => html`
                    <div class="row">
                        <kbd>${s.keys}</kbd>
                        <span>${this.t(s.labelKey)}</span>
                    </div>
                `)}
            </div>
            <div class="help-section">
                <div class="section-title">${this.t('canvas.help.section_features')}</div>
                <div class="feature">
                    <span class="feature-title">${this.t('canvas.help.feature_smart_guides_title')}</span>
                    <span class="feature-hint">${this.t('canvas.help.feature_smart_guides_hint')}</span>
                </div>
                <div class="feature">
                    <span class="feature-title">${this.t('canvas.help.feature_minimap_title')}</span>
                    <span class="feature-hint">${this.t('canvas.help.feature_minimap_hint')}</span>
                </div>
                <div class="feature">
                    <span class="feature-title">${this.t('canvas.help.feature_sticky_title')}</span>
                    <span class="feature-hint">${this.t('canvas.help.feature_sticky_hint')}</span>
                </div>
                <div class="feature">
                    <span class="feature-title">${this.t('canvas.help.feature_drop_resource_title')}</span>
                    <span class="feature-hint">${this.t('canvas.help.feature_drop_resource_hint')}</span>
                </div>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <platform-button variant="primary" @click=${() => this.close()}>
                ${this.t('canvas.help.action_close')}
            </platform-button>
        `;
    }
}

customElements.define('flows-canvas-help-modal', FlowsCanvasHelpModal);
registerModalKind(FlowsCanvasHelpModal.modalKind, 'flows-canvas-help-modal');
