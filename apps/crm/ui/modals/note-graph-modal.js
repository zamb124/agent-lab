import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import '../components/mini-graph-preview.js';

export class NoteGraphModal extends PlatformModal {
    static properties = {
        entityId: { type: String },
    };

    static styles = [
        PlatformModal.styles,
        css`
            .graph-modal-body {
                width: 100%;
                box-sizing: border-box;
                display: flex;
                flex-direction: column;
                overflow: hidden;
                min-height: min(360px, 45vh);
                height: min(520px, 62vh);
            }

            .modal.fullscreen .graph-modal-body,
            .modal.full .graph-modal-body {
                flex: 1 1 auto;
                min-height: 0;
                height: auto;
                max-height: none;
            }

            mini-graph-preview {
                display: block;
                width: 100%;
                flex: 1 1 auto;
                min-height: 0;
                align-self: stretch;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'xl';
        this.entityId = '';
    }

    renderHeader() {
        return this.i18n.t('entity_card.graph_section');
    }

    renderBody() {
        if (typeof this.entityId !== 'string' || this.entityId.trim().length === 0) {
            return html``;
        }
        const id = this.entityId.trim();
        return html`
            <div class="graph-modal-body">
                <mini-graph-preview
                    .entityId=${id}
                    .maxDepth=${5}
                    .fillContainer=${true}
                    width="100%"
                    height="100%"
                ></mini-graph-preview>
            </div>
        `;
    }
}

customElements.define('note-graph-modal', NoteGraphModal);
