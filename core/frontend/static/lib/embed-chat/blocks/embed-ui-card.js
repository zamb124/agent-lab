import { LitElement, html, css } from 'lit';

export class EmbedUiCard extends LitElement {
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
            color: var(--embed-card-text);
            margin: 0 0 4px 0;
        }
        .subtitle {
            font-size: 13px;
            color: var(--embed-card-muted);
            margin: 0;
        }
        .description {
            font-size: 13px;
            line-height: 1.45;
            color: var(--embed-card-text);
            margin: 10px 0 0 0;
            white-space: pre-wrap;
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

customElements.define('embed-ui-card', EmbedUiCard);
