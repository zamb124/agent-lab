/**
 * Секция главной: три публичных демо-агента (lawyer, doctor, psy) + тот же drawer, что на digital-workers.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/embed-chat/platform-embed-chat-drawer.js';
import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/glass-spinner.js';

const HOME_DEMO_FLOW_ORDER = Object.freeze(['lawyer', 'doctor', 'psy']);

export class LandingHomeDemoAgents extends PlatformElement {
    static i18nNamespace = 'landing';

    static properties = {
        _drawerSpec: { state: true },
        _drawerOpen: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
                box-sizing: border-box;
            }
            .wrap {
                max-width: 1200px;
                margin: 0 auto;
                padding: var(--space-8) 20px;
                box-sizing: border-box;
            }
            .head {
                text-align: center;
                margin-bottom: var(--space-8);
            }
            h2 {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: clamp(1.5rem, 4vw, 2.25rem);
                font-weight: 600;
                margin: 0 0 var(--space-3);
                line-height: 1.2;
            }
            .lede {
                font-family: 'Fira Sans', sans-serif;
                font-size: var(--text-md);
                line-height: 1.6;
                color: rgba(255, 255, 255, 0.72);
                max-width: 40rem;
                margin: 0 auto;
            }
            .toolbar {
                display: flex;
                justify-content: center;
                margin-top: var(--space-4);
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
                min-height: 160px;
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
            throw new Error('landing_home_demo_agents: window.location.origin required');
        }
        this._flowsBaseUrl = new URL('/flows', window.location.origin).href;
    }

    connectedCallback() {
        super.connectedCallback();
        this._load.run(null);
    }

    _onDrawerOpenChanged(e) {
        const d = e.detail;
        if (d && typeof d.open === 'boolean') {
            this._drawerOpen = d.open;
        }
    }

    _getDemoAuthHeaders = async () => {
        const spec = this._drawerSpec;
        if (!spec || typeof spec.embed_id !== 'string' || spec.embed_id === '') {
            throw new Error('landing_home_demo_agents: drawer embed context missing');
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
            throw new Error('landing_home_demo_agents: session token missing');
        }
        return { Authorization: `Bearer ${result.token}` };
    };

    _tryAgent(card) {
        if (typeof card.embed_id !== 'string' || card.embed_id === '') {
            throw new Error('landing_home_demo_agents: card.embed_id required');
        }
        if (typeof card.flow_id !== 'string' || card.flow_id === '') {
            throw new Error('landing_home_demo_agents: card.flow_id required');
        }
        if (typeof card.branch_id !== 'string' || card.branch_id === '') {
            throw new Error('landing_home_demo_agents: card.branch_id required');
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

    _allItemsList() {
        const raw = this._load.lastResult;
        if (raw === null || typeof raw !== 'object') {
            return [];
        }
        const items = raw.items;
        if (!Array.isArray(items)) {
            throw new Error('landing_home_demo_agents: items must be array');
        }
        return items;
    }

    _filteredItems() {
        const all = this._allItemsList();
        if (all.length === 0) {
            return [];
        }
        const byFlow = new Map();
        for (const card of all) {
            if (card === null || typeof card !== 'object') {
                continue;
            }
            const fid = card.flow_id;
            if (typeof fid !== 'string') {
                continue;
            }
            if (HOME_DEMO_FLOW_ORDER.includes(fid)) {
                byFlow.set(fid, card);
            }
        }
        const out = [];
        for (const fid of HOME_DEMO_FLOW_ORDER) {
            const c = byFlow.get(fid);
            if (c !== undefined) {
                out.push(c);
            }
        }
        return out;
    }

    render() {
        const busy = this._load.busy;
        const err = this._load.error;
        const allItems = this._allItemsList();
        const items = this._filteredItems();

        return html`
            <div class="wrap">
                <header class="head">
                    <h2>${this.t('home_demo_agents.title')}</h2>
                    <p class="lede">${this.t('home_demo_agents.subtitle')}</p>
                    <div class="toolbar">
                        <glass-button variant="secondary" size="sm" @click=${() => this.navigate('digital-workers')}>
                            ${this.t('home_demo_agents.view_all')}
                        </glass-button>
                    </div>
                </header>

                ${busy && allItems.length === 0
                    ? html`<div class="state-center"><glass-spinner></glass-spinner></div>`
                    : ''}
                ${err !== null && allItems.length === 0
                    ? html`<div class="state-center err">${this.t('digital_workers.load_error')}</div>`
                    : ''}
                ${!busy && err === null && allItems.length === 0
                    ? html`<div class="state-center">${this.t('digital_workers.empty')}</div>`
                    : ''}
                ${!busy && err === null && allItems.length > 0 && items.length === 0
                    ? html`<div class="state-center">${this.t('home_demo_agents.filter_empty')}</div>`
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
                                              <h3 class="card-title">${card.name}</h3>
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

customElements.define('landing-home-demo-agents', LandingHomeDemoAgents);
