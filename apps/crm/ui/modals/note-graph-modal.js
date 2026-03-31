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
                min-height: 320px;
                box-sizing: border-box;
            }

            mini-graph-preview {
                display: block;
                width: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'xl';
        this.entityId = '';
    }

    renderHeader() {
        return 'Граф связей';
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
                    width="100%"
                    height="520px"
                ></mini-graph-preview>
            </div>
        `;
    }
}

customElements.define('note-graph-modal', NoteGraphModal);
