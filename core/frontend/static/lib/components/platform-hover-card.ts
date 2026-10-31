/**
 * Карточка-предпросмотр по наведению.
 *
 * Общий каркас для всех hover-превью платформы: рамка, отступы, появление,
 * положение относительно якоря и удержание открытой, пока курсор внутри
 * карточки. Содержимое задаёт вызывающий компонент через слот — так карточки
 * задачи, сущности CRM и страницы wiki отличаются только наполнением.
 *
 * @example
 * <platform-hover-card ?open=${this._open} .anchor=${this._anchorRect}
 *                      @hover-card-enter=${this._cancelClose}
 *                      @hover-card-leave=${this._scheduleClose}>
 *     ...содержимое...
 * </platform-hover-card>
 */

import { css, html } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';

import { PlatformElement } from '../platform-element/index.js';
import './platform-popover.js';
import type { PlatformPopover, PopoverAnchor } from './platform-popover.js';

export const HOVER_CARD_WIDTH = 320;
export const HOVER_CARD_GAP = 10;
export const HOVER_CARD_VIEWPORT_PADDING = 12;

export class PlatformHoverCard extends PlatformElement {
    static override properties: PropertyDeclarations = {
        open: { type: Boolean, reflect: true },
        /** Элемент, прямоугольник или точка — см. `resolveAnchorRect`. */
        anchor: { attribute: false },
        placement: { type: String },
        width: { type: Number },
    };

    declare open: boolean;
    declare anchor: PopoverAnchor;
    declare placement: string;
    declare width: number;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: contents;
            }

            .card {
                box-sizing: border-box;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3);
                color: var(--text-primary);
                font-family: var(--font-sans);
            }
        `,
    ];

    constructor() {
        super();
        this.open = false;
        this.anchor = null;
        this.placement = 'bottom-start';
        this.width = HOVER_CARD_WIDTH;
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (this.open) {
            this.renderRoot?.querySelector<PlatformPopover>('platform-popover')?.reposition();
        }
    }

    _onEnter(): void {
        this.emit('hover-card-enter');
    }

    _onLeave(): void {
        this.emit('hover-card-leave');
    }

    override render(): TemplateResult {
        return html`
            <platform-popover
                trigger="manual"
                role="tooltip"
                placement=${this.placement}
                offset=${HOVER_CARD_GAP}
                viewport-padding=${HOVER_CARD_VIEWPORT_PADDING}
                dismiss-on-outside
                .anchor=${this.anchor}
                ?open=${this.open}
                @popover-dismiss=${() => this.emit('hover-card-dismiss')}
            >
                <div
                    class="card"
                    part="card"
                    style=${`width:${this.width}px;max-width:min(${this.width}px, calc(100vw - 24px))`}
                    @pointerenter=${this._onEnter}
                    @pointerleave=${this._onLeave}
                >
                    <slot></slot>
                </div>
            </platform-popover>
        `;
    }
}

customElements.define('platform-hover-card', PlatformHoverCard);
