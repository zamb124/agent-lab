/**
 * Мини-выбор при дропе code-ноды: пустая или каталог шаблонов.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';

export class FlowsCodeNodeDropModal extends PlatformModal {
    static modalKind = 'flows.code_node_drop';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        onNew: { type: Object, attribute: false },
        onChooseTemplates: { type: Object, attribute: false },
    };

    static styles = [
        ...(PlatformModal.styles ? [PlatformModal.styles] : []),
        css`
            .body {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            .hint {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .choice-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: var(--space-3);
            }
            .choice-card {
                aspect-ratio: 1;
                max-width: 100%;
                margin: 0 auto;
                width: 100%;
                box-sizing: border-box;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                padding: var(--space-4);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                cursor: pointer;
                transition: background var(--duration-fast), border-color var(--duration-fast),
                    transform var(--duration-fast);
                text-align: center;
            }
            .choice-card:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
                transform: translateY(-1px);
            }
            .choice-card:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }
            .choice-card-icon {
                width: 56px;
                height: 56px;
                border-radius: var(--radius-lg);
                display: flex;
                align-items: center;
                justify-content: center;
                color: #fff;
                flex-shrink: 0;
            }
            .choice-card-label {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                line-height: 1.3;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.onNew = null;
        this.onChooseTemplates = null;
    }

    _emitAfterClose(fn) {
        this.close();
        if (typeof fn === 'function') {
            queueMicrotask(() => {
                fn();
            });
        }
    }

    _onNew() {
        this._emitAfterClose(this.onNew);
    }

    _onTemplates() {
        this._emitAfterClose(this.onChooseTemplates);
    }

    _cardKeydown(e, handler) {
        if (e.key !== 'Enter' && e.key !== ' ') {
            return;
        }
        e.preventDefault();
        handler.call(this);
    }

    renderHeader() {
        return this.t('code_node_drop_modal.title');
    }

    renderBody() {
        return html`
            <div class="body">
                <p class="hint">${this.t('code_node_drop_modal.hint')}</p>
                <div class="choice-grid">
                    <div
                        class="choice-card"
                        role="button"
                        tabindex="0"
                        aria-label=${this.t('code_node_drop_modal.action_blank')}
                        @click=${this._onNew}
                        @keydown=${(e) => this._cardKeydown(e, this._onNew)}
                    >
                        <div
                            class="choice-card-icon"
                            style="background: linear-gradient(135deg, #82E0AA 0%, #76D7C4 100%);"
                        >
                            <platform-icon name="code" size="28"></platform-icon>
                        </div>
                        <div class="choice-card-label">${this.t('code_node_drop_modal.action_blank')}</div>
                    </div>
                    <div
                        class="choice-card"
                        role="button"
                        tabindex="0"
                        aria-label=${this.t('code_node_drop_modal.action_templates')}
                        @click=${this._onTemplates}
                        @keydown=${(e) => this._cardKeydown(e, this._onTemplates)}
                    >
                        <div
                            class="choice-card-icon"
                            style="background: linear-gradient(135deg, #5DADE2 0%, #5499C7 100%);"
                        >
                            <platform-icon name="layers" size="28"></platform-icon>
                        </div>
                        <div class="choice-card-label">${this.t('code_node_drop_modal.action_templates')}</div>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('flows-code-node-drop-modal', FlowsCodeNodeDropModal);
registerModalKind(FlowsCodeNodeDropModal.modalKind, 'flows-code-node-drop-modal');
