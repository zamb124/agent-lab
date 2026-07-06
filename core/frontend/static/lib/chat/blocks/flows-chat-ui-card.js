import { LitElement, html, css } from '../../lit-shim.js';

export class FlowsChatUiCard extends LitElement {
    static properties = {
        title: { type: String },
        subtitle: { type: String },
        /** Короткая метка слева от заголовка (эмодзи или 1–2 символа). */
        icon: { type: String },
        /** Основной текст под заголовком (несколько строк). */
        description: { type: String },
        url: { type: String },
    };

    static styles = css`
        :host {
            display: block;
            --flows-chat-card-bg: var(--flows-chat-surface, rgba(255, 255, 255, 0.06));
            --flows-chat-card-border: var(--flows-chat-border, rgba(255, 255, 255, 0.12));
            --flows-chat-card-text: var(--flows-chat-text, rgba(255, 255, 255, 0.92));
            --flows-chat-card-muted: var(--flows-chat-muted, rgba(255, 255, 255, 0.55));
        }
        .card {
            border-radius: var(--flows-chat-radius, 8px);
            border: 1px solid var(--flows-chat-card-border);
            background: var(--flows-chat-card-bg);
            padding: 12px 14px;
        }
        .head {
            display: flex;
            align-items: flex-start;
            gap: 10px;
        }
        .icon {
            flex-shrink: 0;
            font-size: 20px;
            line-height: 1.2;
        }
        .head-text {
            flex: 1;
            min-width: 0;
        }
        .title {
            font-weight: 600;
            font-size: 15px;
            color: var(--flows-chat-card-text);
            margin: 0 0 4px 0;
        }
        .subtitle {
            font-size: 13px;
            color: var(--flows-chat-card-muted);
            margin: 0;
        }
        .description {
            font-size: 13px;
            line-height: 1.45;
            color: var(--flows-chat-card-text);
            margin: 10px 0 0 0;
            white-space: pre-wrap;
        }
        a.title {
            text-decoration: none;
            color: var(--flows-chat-accent, #99a6f9);
        }
        a.title:hover {
            text-decoration: underline;
        }
    `;

    render() {
        const titleContent = this.url
            ? html`<a class="title" href=${this.url} target="_blank" rel="noopener noreferrer">${this.title || ''}</a>`
            : html`<div class="title">${this.title || ''}</div>`;
        const icon =
            this.icon && String(this.icon).trim()
                ? html`<span class="icon" aria-hidden="true">${this.icon}</span>`
                : '';
        return html`
            <div class="card">
                <div class="head">
                    ${icon}
                    <div class="head-text">
                        ${titleContent}
                        ${this.subtitle ? html`<p class="subtitle">${this.subtitle}</p>` : ''}
                    </div>
                </div>
                ${this.description
                    ? html`<p class="description">${this.description}</p>`
                    : ''}
            </div>
        `;
    }
}

customElements.define('flows-chat-ui-card', FlowsChatUiCard);
