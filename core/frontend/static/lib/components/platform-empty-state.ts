/**
 * platform-empty-state — единый примитив пустого состояния и загрузки списка.
 *
 * `loading` → вращающийся спиннер вместо иконки; `icon`/`title`/`hint` — empty;
 * default-слот — действия (кнопка создания). Появление — motion-токены,
 * уважает prefers-reduced-motion.
 */
import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import './platform-icon.js';
import './platform-spinner.js';

export class PlatformEmptyState extends PlatformElement {
    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                padding: var(--space-8) var(--space-6);
                text-align: center;
                animation: platform-empty-state-enter
                    var(--motion-duration-enter, 180ms)
                    var(--motion-ease-decelerate, cubic-bezier(0.22, 1, 0.36, 1))
                    both;
            }
            @keyframes platform-empty-state-enter {
                from {
                    opacity: 0;
                    transform: translateY(var(--motion-enter-offset-y, 8px));
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            .icon {
                color: var(--text-tertiary);
                opacity: 0.8;
            }
            .title {
                font-size: var(--text-base);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }
            .hint {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                max-width: 320px;
            }
            .actions {
                margin-top: var(--space-2);
                display: flex;
                gap: var(--space-3);
                flex-wrap: wrap;
                justify-content: center;
            }
            .actions:empty {
                display: none;
            }
            @media (prefers-reduced-motion: reduce) {
                :host {
                    animation: none;
                }
            }
        `,
    ];

    static override properties: PropertyDeclarations = {
        icon: { type: String },
        title: { type: String },
        hint: { type: String },
        loading: { type: Boolean, reflect: true },
    };

    declare icon: string;
    declare title: string;
    declare hint: string;
    declare loading: boolean;

    constructor() {
        super();
        this.icon = '';
        this.title = '';
        this.hint = '';
        this.loading = false;
    }

    override render(): TemplateResult {
        return html`
            ${this.loading
                ? html`<platform-spinner size="lg"></platform-spinner>`
                : this.icon
                  ? html`<platform-icon class="icon" name=${this.icon} size="64"></platform-icon>`
                  : null}
            ${this.title ? html`<div class="title">${this.title}</div>` : ''}
            ${this.hint ? html`<div class="hint">${this.hint}</div>` : ''}
            <div class="actions"><slot></slot></div>
        `;
    }
}

customElements.define('platform-empty-state', PlatformEmptyState);
