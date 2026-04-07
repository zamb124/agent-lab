import { LitElement, html, css } from 'lit';

export class EmbedUiFileCard extends LitElement {
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
        .meta {
            flex: 1;
            min-width: 0;
        }
        .name {
            font-size: 14px;
            font-weight: 500;
            color: var(--embed-chat-text, rgba(255, 255, 255, 0.92));
            margin: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .mime {
            font-size: 11px;
            color: var(--embed-chat-muted, rgba(255, 255, 255, 0.5));
            margin: 2px 0 0 0;
        }
        a {
            font-size: 13px;
            color: var(--embed-chat-accent, #99a6f9);
        }
    `;

    render() {
        const href = this.url || this.preview_url || '#';
        return html`
            <div class="wrap">
                <div class="meta">
                    <p class="name">${this.name || this.file_id || 'File'}</p>
                    ${this.mime_type ? html`<p class="mime">${this.mime_type}</p>` : ''}
                </div>
                ${this.url ? html`<a href=${this.url} target="_blank" rel="noopener noreferrer">Open</a>` : ''}
            </div>
        `;
    }
}

customElements.define('embed-ui-file-card', EmbedUiFileCard);
