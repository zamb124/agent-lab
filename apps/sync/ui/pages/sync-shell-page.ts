/**
 * sync-shell-page — экран `/sync` без выбранного канала.
 *
 * Desktop (>=768px): сетка крупных карточек `<sync-channel-picker>` — основная
 * навигация уже в боковой панели слева, поэтому главная даёт другой ракурс
 * (визуальные плитки).
 *
 * Mobile (<=767px): боковая панель скрыта целиком (см. sidebar.styles.js),
 * поэтому страница рендерит ровно тот же `<sync-chat-list>`, что внутри
 * `<sync-sidebar>`. UX главного экрана совпадает с UX десктопной боковой
 * панели по требованию пользователя (mobile shell 2026).
 */

import { html, css } from 'lit';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '../components/sync-channel-picker.js';
import '../components/sync-chat-list.js';

export class SyncShellPage extends PlatformPage {
    static override properties: PropertyDeclarations = {
        _isMobile: { state: true },
    };
    declare _isMobile: unknown;

    static override styles: CSSResultGroup = css`
        :host {
            display: flex;
            flex-direction: column;
            flex: 1;
            min-height: 0;
            height: 100%;
        }
        .chat-list-host {
            flex: 1;
            min-height: 0;
            height: 100%;
            display: flex;
            flex-direction: column;
        }
        sync-chat-list { flex: 1; min-height: 0; }
    `;
    private _mediaQuery: MediaQueryList | null;
    private _mediaListener: (e: MediaQueryListEvent) => void;

    constructor() {
        super();
        this._isMobile = false;
        this._mediaQuery = null;
        this._mediaListener = (e: MediaQueryListEvent) => { this._isMobile = e.matches; };
        this.useEvent('sync/calls/adhoc_create_requested', () => this._onAdhocCall());
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
            this._mediaQuery = window.matchMedia('(max-width: 767px)');
            this._isMobile = this._mediaQuery.matches;
            this._mediaQuery.addEventListener('change', this._mediaListener);
        }
    }

    override disconnectedCallback(): void {
        if (this._mediaQuery !== null) {
            this._mediaQuery.removeEventListener('change', this._mediaListener);
            this._mediaQuery = null;
        }
        super.disconnectedCallback();
    }

    _onAdhocCall() {
        this.openModal('sync.channel_create', { adhocCall: true });
    }

    override render(): TemplateResult {
        if (this._isMobile) {
            return html`
                <div class="chat-list-host">
                    <sync-chat-list mode="page"></sync-chat-list>
                </div>
            `;
        }
        return html`<sync-channel-picker></sync-channel-picker>`;
    }
}

customElements.define('sync-shell-page', SyncShellPage);
