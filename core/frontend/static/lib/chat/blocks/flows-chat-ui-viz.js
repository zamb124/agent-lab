/**
 * Inline viz preview in flows chat (block type=viz).
 */
import { html, css } from '../../lit-shim.js';
import { PlatformElement } from '../../platform-element/index.js';
import '../../components/platform-viz-host.js';

export class FlowsChatUiViz extends PlatformElement {
    static properties = {
        file_id: { type: String },
        kind: { type: String },
        engine: { type: String },
        title: { type: String },
        spec: { type: Object },
        document: { type: Object },
    };

    static styles = css`
        :host {
            display: block;
            margin: 4px 0;
        }
        .header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 6px;
        }
        .label {
            flex: 1;
            min-width: 0;
            font-size: 13px;
            font-weight: 600;
            color: var(--flows-chat-text, rgba(255, 255, 255, 0.92));
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        button {
            border: 0;
            background: transparent;
            padding: 0;
            font-family: inherit;
            font-size: 12px;
            color: var(--flows-chat-accent, #99a6f9);
            cursor: pointer;
            text-decoration: underline;
        }
        platform-viz-host {
            display: block;
            width: 100%;
        }
    `;

    _document() {
        if (this.document && typeof this.document === 'object') {
            return this.document;
        }
        const kind = typeof this.kind === 'string' && this.kind.length > 0 ? this.kind : 'chart';
        const engine = typeof this.engine === 'string' && this.engine.length > 0 ? this.engine : 'echarts';
        const title = typeof this.title === 'string' && this.title.length > 0 ? this.title : 'Visualization';
        const spec = this.spec && typeof this.spec === 'object' ? this.spec : null;
        if (!spec) {
            return null;
        }
        return {
            schema_version: 1,
            kind,
            engine,
            title,
            spec,
        };
    }

    _open() {
        if (!this.file_id) {
            return;
        }
        const doc = this._document();
        const title = doc?.title || this.title || 'visualization';
        this.openFile(
            {
                file_id: this.file_id,
                original_name: title.endsWith('.viz') ? title : `${title}.viz`,
                content_type: 'application/vnd.platform.viz+json',
            },
            { source: 'flows_chat_viz' },
        );
    }

    render() {
        const doc = this._document();
        if (!doc) {
            return html`<div class="label">Invalid viz block</div>`;
        }
        return html`
            <div class="header">
                <div class="label">${doc.title}</div>
                ${this.file_id
                    ? html`<button type="button" @click=${this._open}>Open</button>`
                    : ''}
            </div>
            <platform-viz-host
                compact
                .document=${doc}
                .fileId=${this.file_id || ''}
                ?show-toolbar=${false}
            ></platform-viz-host>
        `;
    }
}

customElements.define('flows-chat-ui-viz', FlowsChatUiViz);
