/**
 * <scramble-text> — scramble/shuffle reveal заголовков (TextShuffle из
 * quantumwallet.tech): при входе во вьюпорт каждая буква прокручивает
 * случайные глифы и садится на финальный символ со stagger по словам.
 *
 * Реальный текст остаётся в DOM (sr-only спан) — SEO и скринридеры видят
 * финальную строку сразу. prefers-reduced-motion — текст без анимации.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { hasPlatformBus } from '@platform/lib/events/bus-singleton.js';
import { isI18nBundleReady } from '@platform/lib/events/effects/i18n.effect.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';

const GLYPHS = 'AEKMNOTXYZАБВГДЕЁЖЗИКЛМНОПРСТУФХ0123456789';
const CHAR_MS = 420;
const STAGGER_MS = 38;
const GLYPH_MS = 52;

export class ScrambleText extends PlatformElement {
    static override properties: PropertyDeclarations = {
        text: { type: String },
        delay: { type: Number },
        _revealed: { state: true },
    };

    declare text: string;
    declare delay: number;
    declare _revealed: boolean;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host { display: inline; }
            .scramble-word {
                display: inline-block;
                white-space: nowrap;
            }
            .scramble-sr {
                position: absolute;
                width: 1px;
                height: 1px;
                padding: 0;
                margin: -1px;
                overflow: hidden;
                clip: rect(0 0 0 0);
                white-space: nowrap;
                border: 0;
            }
            .scramble-live { opacity: 0; }
            .scramble-live.on { opacity: 1; }
        `,
    ];

    private _observer: IntersectionObserver | null = null;
    private _i18nReady: SelectController<boolean> | null = null;
    private _pendingStart = false;
    private _raf = 0;
    /* _chars идёт вразнобой с _finals: пробелам спанов нет — null-заглушка. */
    private _chars: (HTMLSpanElement | null)[] = [];
    private _finals: string[] = [];

    constructor() {
        super();
        this.text = '';
        this.delay = 0;
        this._revealed = false;
    }

    override firstUpdated(): void {
        if (hasPlatformBus()) {
            this._i18nReady = this.select((s) => isI18nBundleReady(s.i18n));
        }
        const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (reduced) {
            this._revealed = true;
            return;
        }
        this._observer = new IntersectionObserver(
            (entries) => {
                for (const entry of entries) {
                    if (entry.isIntersecting) {
                        this._pendingStart = true;
                        this._maybeStart();
                        this._observer?.disconnect();
                        this._observer = null;
                    }
                }
            },
            { threshold: 0.35 },
        );
        this._observer.observe(this);
    }

    override disconnectedCallback(): void {
        if (this._observer !== null) {
            this._observer.disconnect();
            this._observer = null;
        }
        cancelAnimationFrame(this._raf);
        super.disconnectedCallback();
    }

    override updated(changed: PropertyValues<this>): void {
        /* Ключ может прийти до загрузки i18n-бандла и смениться позже —
           перестраиваем спаны полностью; при revealed сразу финальный текст. */
        if (changed.has('text')) {
            this._buildChars();
            if (this._revealed) {
                this._chars.forEach((span, i) => {
                    if (span !== null) {
                        const ch = this._finals[i];
                        span.textContent = ch === undefined ? '' : ch;
                    }
                });
            }
        }
        this._maybeStart();
    }

    /* Не запускаем анимацию, пока бандл i18n не подгрузился: иначе заголовок
       тасует сырой ключ перевода. _i18nReady перерендерит компонент, когда
       бандл придёт, — updated() дозовёт старт. */
    private _maybeStart(): void {
        if (!this._pendingStart || this._revealed) {
            return;
        }
        if (this._i18nReady !== null && !this._i18nReady.value) {
            return;
        }
        this._pendingStart = false;
        this._start();
    }

    private _buildChars(): void {
        this._chars = [];
        this._finals = this.text.split('');
        const host = this.renderRoot.querySelector('.scramble-live');
        if (!(host instanceof HTMLElement)) {
            return;
        }
        host.textContent = '';
        let word: HTMLSpanElement | null = null;
        this._finals.forEach((ch) => {
            if (ch === ' ') {
                word = null;
                host.appendChild(document.createTextNode(' '));
                this._chars.push(null);
                return;
            }
            if (word === null) {
                word = document.createElement('span');
                word.className = 'scramble-word';
                host.appendChild(word);
            }
            const span = document.createElement('span');
            span.textContent = ch;
            word.appendChild(span);
            this._chars.push(span);
        });
    }

    private _start(): void {
        this._revealed = true;
        const start = performance.now() + this.delay;
        const finals = this._finals;
        const chars = this._chars;
        const tick = (now: number): void => {
            let done = true;
            for (let i = 0; i < chars.length; i++) {
                const span = chars[i];
                const final = finals[i];
                if (span === null || span === undefined || final === undefined) {
                    continue;
                }
                const localStart = start + i * STAGGER_MS;
                if (now < localStart) {
                    done = false;
                    continue;
                }
                const elapsed = now - localStart;
                if (elapsed >= CHAR_MS) {
                    span.textContent = final;
                    continue;
                }
                done = false;
                if (elapsed % GLYPH_MS < 34 || span.textContent === '') {
                    const g = GLYPHS[Math.floor(Math.random() * GLYPHS.length)];
                    span.textContent = g === undefined ? final : g;
                }
            }
            if (!done) {
                this._raf = requestAnimationFrame(tick);
            } else {
                this._chars.forEach((span, i) => {
                    if (span !== null) {
                        const ch = finals[i];
                        span.textContent = ch === undefined ? '' : ch;
                    }
                });
            }
        };
        this._raf = requestAnimationFrame(tick);
    }

    override render(): TemplateResult {
        return html`
            <span class="scramble-sr">${this.text}</span>
            <span class=${this._revealed ? 'scramble-live on' : 'scramble-live'} aria-hidden="true"></span>
        `;
    }
}

customElements.define('scramble-text', ScrambleText);
