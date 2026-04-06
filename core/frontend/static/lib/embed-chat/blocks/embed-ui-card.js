import { LitElement, html, css } from 'lit';

export class EmbedUiCard extends LitElement {
    static properties = {
        title: { type: String },
        subtitle: { type: String },
        icon: { type: String },
        url: { type: String },
    };

    static styles = css`
        :host {
            display: block;
            --embed-card-bg: var(--embed-chat-surface, rgba(255, 255, 255, 0.06));
            --embed-card-border: var(--embed-chat-border, rgba(255, 255, 255, 0.12));
            --embed-card-text: var(--embed-chat-text, rgba(255, 255, 255, 0.92));
            --embed-card-muted: var(--embed-chat-muted, rgba(255, 255, 255, 0.55));
        }
        .card {
            border-radius: var(--embed-radius, 25px);
            border: 1px solid var(--embed-card-border);
            background: var(--embed-card-bg);
            padding: 12px 14px;
        }
        .title {
            font-weight: 600;
            font-size: 15px;
            color: var(--embed-card-text);
            margin: 0 0 4px 0;
        }
        .subtitle {
            font-size: 13px;
            color: var(--embed-card-muted);
            margin: 0;
        }
        a.title {
            text-decoration: none;
            color: var(--embed-chat-accent, #99a6f9);
        }
        a.title:hover {
            text-decoration: underline;
        }
    `;

    render() {
        const titleContent = this.url
            ? html`<a class="title" href=${this.url} target="_blank" rel="noopener noreferrer">${this.title || ''}</a>`
            : html`<div class="title">${this.title || ''}</div>`;
        return html`
            <div class="card">
                ${titleContent}
                ${this.subtitle ? html`<p class="subtitle">${this.subtitle}</p>` : ''}
            </div>
        `;
    }
}

customElements.define('embed-ui-card', EmbedUiCard);
