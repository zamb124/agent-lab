/**
 * Мини-выбор при дропе code-ноды: пустая или каталог шаблонов.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-picker-card.js';
import type {CSSResultGroup, PropertyDeclarations} from 'lit';

export class FlowsCodeNodeDropModal extends PlatformModal {
    static modalKind = 'flows.code_node_drop';
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        onNew: { type: Object, attribute: false },
        onChooseTemplates: { type: Object, attribute: false },
    }
    declare onNew: Record<string, any> | null;
    declare onChooseTemplates: Record<string, any> | null;
;

    static override styles: CSSResultGroup = [
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
            platform-picker-card {
                min-width: 0;
            }
            .picker-card-icon {
                width: 56px;
                height: 56px;
                border-radius: var(--radius-lg);
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--flows-avatar-text);
            }
            .picker-card-icon[data-variant='code'] {
                background: var(--flows-preset-code-gradient);
            }
            .picker-card-icon[data-variant='templates'] {
                background: var(--flows-preset-multi-gradient);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.onNew = null;
        this.onChooseTemplates = null;
    }

    _emitAfterClose(fn: any) {
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

    override renderHeader() {
        return this.t('code_node_drop_modal.title');
    }

    override renderBody() {
        return html`
            <div class="body">
                <p class="hint">${this.t('code_node_drop_modal.hint')}</p>
                <div class="choice-grid">
                    <platform-picker-card
                        value="blank"
                        title=${this.t('code_node_drop_modal.action_blank')}
                        @select=${this._onNew}
                    >
                        <div slot="icon" class="picker-card-icon" data-variant="code">
                            <platform-icon name="code" size="28"></platform-icon>
                        </div>
                    </platform-picker-card>
                    <platform-picker-card
                        value="templates"
                        title=${this.t('code_node_drop_modal.action_templates')}
                        @select=${this._onTemplates}
                    >
                        <div slot="icon" class="picker-card-icon" data-variant="templates">
                            <platform-icon name="layers" size="28"></platform-icon>
                        </div>
                    </platform-picker-card>
                </div>
            </div>
        `;
    }
}

customElements.define('flows-code-node-drop-modal', FlowsCodeNodeDropModal);
registerModalKind(FlowsCodeNodeDropModal.modalKind, 'flows-code-node-drop-modal');
