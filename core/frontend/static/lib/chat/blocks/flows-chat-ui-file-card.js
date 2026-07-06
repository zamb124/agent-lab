import { html, css } from '../../lit-shim.js';
import { PlatformElement } from '../../platform-element/index.js';
import '../../components/platform-icon.js';
import { resolveFileIconKey } from '../../utils/file-icons.js';

export class FlowsChatUiFileCard extends PlatformElement {
    static properties = {
        name: { type: String },
        file_id: { type: String, attribute: 'file-id' },
        mime_type: { type: String, attribute: 'mime-type' },
        url: { type: String },
        preview_url: { type: String, attribute: 'preview-url' },
    };

    static styles = css`
        :host {
            display: block;
        }
        .wrap {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 4px 0;
        }
        platform-icon[file-icon] {
            flex: 0 0 auto;
        }
        .meta {
            flex: 1;
            min-width: 0;
        }
        .name {
            font-size: 14px;
            font-weight: 500;
            color: var(--flows-chat-text, rgba(255, 255, 255, 0.92));
            margin: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .mime {
            font-size: 11px;
            color: var(--flows-chat-muted, rgba(255, 255, 255, 0.5));
            margin: 2px 0 0 0;
        }
        a,
        button {
            border: 0;
            background: transparent;
            padding: 0;
            font-family: inherit;
            font-size: 13px;
            color: var(--flows-chat-accent, #99a6f9);
            cursor: pointer;
            text-decoration: underline;
        }
    `;

    _open() {
        if (this.file_id) {
            this.openFile({
                file_id: this.file_id,
                original_name: this.name,
                content_type: this.mime_type,
                url: this.url,
            }, { source: 'flows_chat_file_card' });
            return;
        }
        if (this.url && typeof window !== 'undefined') {
            window.open(this.url, '_blank', 'noopener');
        }
    }

    render() {
        const label = this.name || this.file_id || 'File';
        return html`
            <div class="wrap">
                <platform-icon file-icon name=${resolveFileIconKey(label, this.mime_type)} size="24"></platform-icon>
                <div class="meta">
                    <p class="name">${label}</p>
                    ${this.mime_type ? html`<p class="mime">${this.mime_type}</p>` : ''}
                </div>
                ${this.file_id || this.url
                    ? html`<button type="button" @click=${this._open}>Open</button>`
                    : ''}
            </div>
        `;
    }
}

customElements.define('flows-chat-ui-file-card', FlowsChatUiFileCard);
