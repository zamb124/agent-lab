/**
 * PlatformButton — унифицированная кнопка платформы
 * Варианты: primary (violet), accent (orange), secondary, danger, ghost
 */
import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import './platform-spinner.js';

export class PlatformButton extends PlatformElement {
    static override styles: CSSResultGroup = css`
        :host {
            display: inline-flex;
            max-width: 100%;
            box-sizing: border-box;
        }

        :host([icon-only]) {
            flex: 0 0 auto;
        }

        :host([block]) {
            display: flex;
            width: 100%;
            max-width: 100%;
            min-width: 0;
            box-sizing: border-box;
        }

        :host([block]) button {
            width: 100%;
            max-width: 100%;
            min-width: 0;
            justify-content: flex-start;
            white-space: normal;
            text-align: left;
            border-radius: var(--radius-md);
            overflow: hidden;
        }

        button {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: var(--space-2);
            padding: var(--btn-padding);
            font-size: var(--btn-font-size);
            font-weight: var(--btn-font-weight);
            font-family: inherit;
            line-height: var(--btn-line-height);
            border-radius: var(--btn-radius);
            border: none;
            cursor: pointer;
            transition: var(--motion-transition-interactive);
            white-space: nowrap;
            box-sizing: border-box;
            min-width: 0;
            max-width: 100%;
        }

        button ::slotted(span) {
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        :host([density="compact"]) {
            --btn-padding: 6px 16px;
            --btn-font-size: var(--text-sm);
        }

        :host([density="dense"]) {
            --btn-padding: 4px 12px;
            --btn-font-size: var(--text-xs);
        }

        :host([icon-only]) button {
            width: var(--platform-button-icon-size, 36px);
            min-width: var(--platform-button-icon-size, 36px);
            height: var(--platform-button-icon-size, 36px);
            padding: 0;
            border-radius: var(--platform-button-icon-radius, var(--radius-full));
            line-height: 1;
        }

        :host([icon-only][density="compact"]) {
            --platform-button-icon-size: 32px;
        }

        :host([icon-only][density="dense"]) {
            --platform-button-icon-size: 28px;
        }
        
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        /* Primary — violet */
        button.primary {
            color: var(--platform-btn-primary-text);
            -webkit-text-fill-color: currentColor;
            background: var(--platform-btn-primary-bg);
            box-shadow: var(--platform-btn-primary-shadow);
        }

        button.primary:hover:not(:disabled) {
            color: var(--platform-btn-primary-text);
            background: var(--platform-btn-primary-bg-hover);
            box-shadow: var(--platform-btn-primary-shadow-hover);
        }

        ::slotted(*) {
            -webkit-text-fill-color: currentColor;
        }

        /* Accent — orange */
        button.accent {
            color: var(--platform-btn-accent-text);
            background: var(--platform-btn-accent-bg);
            box-shadow: var(--platform-btn-accent-shadow);
        }

        button.accent:hover:not(:disabled) {
            background: var(--platform-btn-accent-bg-hover);
            box-shadow: var(--platform-btn-accent-shadow-hover);
        }
        
        /* Secondary */
        button.secondary {
            color: var(--platform-btn-secondary-text);
            background: var(--platform-btn-secondary-bg);
            border: none;
        }
        
        button.secondary:hover:not(:disabled) {
            background: var(--platform-btn-secondary-bg-hover);
            box-shadow: var(--platform-btn-secondary-shadow-hover);
        }
        
        /* Danger */
        button.danger {
            color: white;
            background: var(--error);
        }
        
        button.danger:hover:not(:disabled) {
            background: #e11d48;
            box-shadow: 0 0 10px rgba(244, 63, 94, 0.4);
        }

        button.ghost-danger {
            color: var(--error);
            background: transparent;
        }

        button.ghost-danger:hover:not(:disabled) {
            color: var(--error);
            background: var(--error-bg);
        }
        
        /* Ghost */
        button.ghost {
            color: var(--text-secondary);
            background: transparent;
        }
        
        button.ghost:hover:not(:disabled) {
            color: var(--text-primary);
            background: var(--glass-tint-subtle);
        }
        
        /* Светлая тема */
        :host-context([data-theme="light"]) button.secondary {
            color: var(--platform-btn-secondary-text);
            background: var(--platform-btn-secondary-bg);
        }
        
        :host-context([data-theme="light"]) button.secondary:hover:not(:disabled) {
            background: var(--platform-btn-secondary-bg-hover);
        }
        
        :host-context([data-theme="light"]) button.ghost {
            color: var(--text-secondary);
        }
        
        :host-context([data-theme="light"]) button.ghost:hover:not(:disabled) {
            color: var(--text-primary);
            background: var(--glass-tint-subtle);
        }

        :host-context([data-theme="light"]) button.ghost-danger {
            color: var(--error);
        }

        :host-context([data-theme="light"]) button.ghost-danger:hover:not(:disabled) {
            color: var(--error);
            background: var(--error-bg);
        }
    `;

    static override properties: PropertyDeclarations = {
        variant: { type: String },
        disabled: { type: Boolean },
        loading: { type: Boolean },
        type: { type: String },
        density: { type: String, reflect: true },
        iconOnly: { type: Boolean, attribute: 'icon-only', reflect: true },
        block: { type: Boolean, reflect: true },
        ariaLabel: { type: String, attribute: 'aria-label' },
        primary: { type: Boolean, reflect: true },
        accent: { type: Boolean, reflect: true },
        secondary: { type: Boolean, reflect: true },
        danger: { type: Boolean, reflect: true },
        ghost: { type: Boolean, reflect: true },
    };

    declare variant: string;
    declare disabled: boolean;
    declare loading: boolean;
    declare type: string;
    declare density: string;
    declare iconOnly: boolean;
    declare block: boolean;
    declare ariaLabel: string;
    declare primary: boolean;
    declare accent: boolean;
    declare secondary: boolean;
    declare danger: boolean;
    declare ghost: boolean;

    constructor() {
        super();
        this.variant = 'primary';
        this.disabled = false;
        this.loading = false;
        this.type = 'button';
        this.density = 'default';
        this.iconOnly = false;
        this.block = false;
        this.ariaLabel = '';
        this.primary = false;
        this.accent = false;
        this.secondary = false;
        this.danger = false;
        this.ghost = false;
    }

    static override get observedAttributes(): string[] {
        return [...super.observedAttributes, 'size', 'busy'];
    }

    override attributeChangedCallback(name: string, old: string | null, value: string | null): void {
        if (value !== null && name === 'size') {
            throw new Error(
                'platform-button: "size" attribute is not supported — use density="compact" or density="dense"',
            );
        }
        if (value !== null && name === 'busy') {
            throw new Error(
                'platform-button: "busy" attribute is not supported — use the "loading" property',
            );
        }
        super.attributeChangedCallback(name, old, value);
    }

    override willUpdate(changedProps: PropertyValues<this>): void {
        super.willUpdate(changedProps);
        if (changedProps.has('density')) {
            const v = this.density;
            if (v !== 'default' && v !== 'compact' && v !== 'dense') {
                throw new Error(
                    `platform-button: density must be "default", "compact" or "dense", got "${v}"`,
                );
            }
        }
    }

    _isGhostVariant(): boolean {
        return this.ghost || this.variant === 'ghost';
    }

    _effectiveVariant(): string {
        if (this.danger && this._isGhostVariant()) {
            return 'ghost-danger';
        }
        if (this.danger) {
            return 'danger';
        }
        if (this.accent) return 'accent';
        if (this.secondary) {
            return 'secondary';
        }
        if (this._isGhostVariant()) {
            return 'ghost';
        }
        if (this.primary) return 'primary';
        return this.variant;
    }

    override render(): TemplateResult {
        const label =
            typeof this.ariaLabel === 'string' && this.ariaLabel.length > 0
                ? this.ariaLabel
                : (typeof this.title === 'string' && this.title.length > 0 ? this.title : '');
        return html`
            <button 
                type="${this.type}"
                class="${this._effectiveVariant()}"
                aria-label=${label.length > 0 ? label : nothing}
                title=${label.length > 0 ? label : nothing}
                ?disabled=${this.disabled || this.loading}
            >
                ${this.loading ? html`<platform-spinner size="xs"></platform-spinner>` : ''}
                <slot></slot>
            </button>
        `;
    }
}

customElements.define('platform-button', PlatformButton);
