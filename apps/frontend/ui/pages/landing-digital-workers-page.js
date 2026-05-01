/**
 * Публичный каталог демо-агентов: карточки + пробный чат через platform-embed-chat-drawer.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/embed-chat/platform-embed-chat-drawer.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/glass-spinner.js';

export class LandingDigitalWorkersPage extends PlatformPage {
    static i18nNamespace = 'landing';

    static properties = {
        _drawerSpec: { state: true },
        _drawerOpen: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: block;
                width: 100%;
                box-sizing: border-box;
                min-height: var(--app-vh, 100vh);
                background: var(--landing-bg, #0f0f0f);
                color: var(--landing-text, #ffffff);
            }
            .wrap {
                max-width: 1200px;
                margin: 0 auto;
                padding: 24px 20px 80px;
                box-sizing: border-box;
            }
            platform-breadcrumbs {
                display: block;
                margin-bottom: var(--space-6);
            }
            .head {
                text-align: center;
                margin-bottom: var(--space-8);
            }
            h1 {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: clamp(2rem, 5vw, 3rem);
                font-weight: 600;
                margin: 0 0 var(--space-4);
                line-height: 1.15;
            }
            .lede {
                font-family: 'Fira Sans', sans-serif;
                font-size: var(--text-lg);
                line-height: 1.6;
                color: rgba(255, 255, 255, 0.72);
                max-width: 42rem;
                margin: 0 auto;
            }
            .disclaimer {
                font-family: 'Fira Sans', sans-serif;
                font-size: var(--text-sm);
                line-height: 1.6;
                color: rgba(255, 255, 255, 0.55);
                max-width: 48rem;
                margin: 0 auto var(--space-10);
                padding: var(--space-4);
                border-radius: var(--radius-md);
                border: 1px solid rgba(255, 255, 255, 0.12);
                background: rgba(255, 255, 255, 0.04);
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: var(--space-6);
            }
            .card-image {
                width: 100%;
                aspect-ratio: 16 / 10;
                object-fit: cover;
                border-radius: var(--radius-md);
                display: block;
                background: rgba(255, 255, 255, 0.06);
            }
            .card-body {
                padding: var(--space-4) 0 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                flex: 1;
            }
            .card-title {
                font-size: var(--text-lg);
                font-weight: 600;
                margin: 0;
            }
            .card-desc {
                font-size: var(--text-sm);
                color: rgba(255, 255, 255, 0.65);
                margin: 0;
                line-height: 1.5;
                flex: 1;
            }
            .card-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-top: var(--space-2);
            }
            .state-center {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-4);
                min-height: 200px;
                font-family: 'Fira Sans', sans-serif;
                color: rgba(255, 255, 255, 0.7);
            }
            .err {
                color: #f87171;
                text-align: center;
                max-width: 36rem;
            }
        `,
    ];

    constructor() {
        super();
        this._drawerSpec = null;
        this._drawerOpen = false;
        this._load = this.useOp('frontend/landing_agents_load');
        this._session = this.useOp('frontend/landing_demo_session');
        if (typeof window === 'undefined' || typeof window.location.origin !== 'string') {
            throw new Error('landing_digital_workers_page: window.location.origin required');
        }
        this._flowsBaseUrl = new URL('/flows', window.location.origin).href;
    }

    _onDrawerOpenChanged(e) {
        const d = e.detail;
        if (d && typeof d.open === 'boolean') {
            this._drawerOpen = d.open;
        }
    }

    connectedCallback() {
        super.connectedCallback();
        this._load.run(null);
    }

    _getDemoAuthHeaders = async () => {
        const spec = this._drawerSpec;
        if (!spec || typeof spec.embed_id !== 'string' || spec.embed_id === '') {
            throw new Error('landing_digital_workers: drawer embed context missing');
        }
        const result = await this._session.run({ embed_id: spec.embed_id });
        if (result === null) {
            const msg = this._session.error;
            if (typeof msg === 'string' && msg !== '') {
                this.toast('digital_workers.session_error', {
                    type: 'error',
                    vars: { detail: msg },
                });
            } else {
                this.toast('digital_workers.session_error_generic', { type: 'error' });
            }
            return {};
        }
        if (typeof result.token !== 'string' || result.token === '') {
            throw new Error('landing_digital_workers: session token missing');
        }
        return { Authorization: `Bearer ${result.token}` };
    };

    _tryAgent(card) {
        if (typeof card.embed_id !== 'string' || card.embed_id === '') {
            throw new Error('landing_digital_workers: card.embed_id required');
        }
        if (typeof card.flow_id !== 'string' || card.flow_id === '') {
            throw new Error('landing_digital_workers: card.flow_id required');
        }
        if (typeof card.branch_id !== 'string' || card.branch_id === '') {
            throw new Error('landing_digital_workers: card.branch_id required');
        }
        const title =
            typeof card.assistant_title === 'string' && card.assistant_title.trim() !== ''
                ? card.assistant_title.trim()
                : card.name;
        const theme = card.theme === 'light' || card.theme === 'dark' || card.theme === 'auto' ? card.theme : 'dark';
        const locale =
            card.interface_locale === 'ru' || card.interface_locale === 'en' ? card.interface_locale : 'auto';
        this._drawerSpec = {
            embed_id: card.embed_id,
            flow_id: card.flow_id,
            branch_id: card.branch_id,
            assistant_title: title,
            theme,
            interface_locale: locale,
        };
        this._drawerOpen = true;
        this.requestUpdate();
    }

    _hire() {
        this.openModal('auth.login');
    }

    _itemsList() {
        const raw = this._load.lastResult;
        if (raw === null || typeof raw !== 'object') {
            return [];
        }
        const items = raw.items;
        if (!Array.isArray(items)) {
            throw new Error('landing_digital_workers: items must be array');
        }
        return items;
    }

    render() {
        const busy = this._load.busy;
        const err = this._load.error;
        const items = this._itemsList();

        return html`
            <landing-header></landing-header>
            <div class="wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
                <header class="head">
                    <h1>${this.t('digital_workers.title')}</h1>
                    <p class="lede">${this.t('digital_workers.subtitle')}</p>
                </header>
                <p class="disclaimer">${this.t('digital_workers.disclaimer')}</p>

                ${busy && items.length === 0
                    ? html`<div class="state-center"><glass-spinner></glass-spinner></div>`
                    : ''}
                ${err !== null && items.length === 0
                    ? html`<div class="state-center err">${this.t('digital_workers.load_error')}</div>`
                    : ''}
                ${!busy && err === null && items.length === 0
                    ? html`<div class="state-center">${this.t('digital_workers.empty')}</div>`
                    : ''}

                ${items.length > 0
                    ? html`
                          <div class="grid">
                              ${items.map(
                                  (card) => html`
                                      <glass-card>
                                          <img
                                              class="card-image"
                                              src=${card.landing_card_image_url}
                                              alt=""
                                              loading="lazy"
                                          />
                                          <div class="card-body">
                                              <h2 class="card-title">${card.name}</h2>
                                              <p class="card-desc">
                                                  ${typeof card.greeting_message === 'string' && card.greeting_message !== ''
                                                      ? card.greeting_message
                                                      : this.t('digital_workers.card_fallback_desc')}
                                              </p>
                                              <div class="card-actions">
                                                  <glass-button
                                                      variant="primary"
                                                      size="sm"
                                                      @click=${() => this._tryAgent(card)}
                                                  >
                                                      ${this.t('digital_workers.cta_try')}
                                                  </glass-button>
                                                  <glass-button variant="secondary" size="sm" @click=${this._hire}>
                                                      ${this.t('digital_workers.cta_hire')}
                                                  </glass-button>
                                              </div>
                                          </div>
                                      </glass-card>
                                  `,
                              )}
                          </div>
                      `
                    : ''}
            </div>
            <platform-embed-chat-drawer
                flows-base-url=${this._flowsBaseUrl}
                flow-id=${this._drawerSpec ? this._drawerSpec.flow_id : ''}
                embed-id=${this._drawerSpec ? this._drawerSpec.embed_id : ''}
                branch-id=${this._drawerSpec ? this._drawerSpec.branch_id : ''}
                assistant-title=${this._drawerSpec ? this._drawerSpec.assistant_title : ''}
                theme=${this._drawerSpec ? this._drawerSpec.theme : 'dark'}
                locale=${this._drawerSpec ? this._drawerSpec.interface_locale : 'auto'}
                ?show-launcher=${false}
                ?use-credentials=${false}
                .open=${this._drawerOpen}
                .getAuthToken=${this._getDemoAuthHeaders}
                @humanitec-embed-drawer-open-changed=${this._onDrawerOpenChanged}
            ></platform-embed-chat-drawer>
        `;
    }
}

customElements.define('landing-digital-workers-page', LandingDigitalWorkersPage);
