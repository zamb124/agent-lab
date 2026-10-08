/**
 * platform-echarts-host — Apache ECharts в Lit (lazy script, ResizeObserver, dispose).
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';

const ECHARTS_URL = '/static/core/assets/js/echarts/echarts.min.js';

let _echartsPromise = null;

function loadEcharts() {
    if (typeof window !== 'undefined' && window.echarts) {
        return Promise.resolve(window.echarts);
    }
    if (_echartsPromise) {
        return _echartsPromise;
    }
    _echartsPromise = new Promise((resolve, reject) => {
        const existing = document.querySelector(`script[data-platform-echarts="1"]`);
        if (existing && window.echarts) {
            resolve(window.echarts);
            return;
        }
        const script = document.createElement('script');
        script.src = ECHARTS_URL;
        script.async = true;
        script.dataset.platformEcharts = '1';
        script.onload = () => {
            if (!window.echarts) {
                reject(new Error('echarts global missing after load'));
                return;
            }
            resolve(window.echarts);
        };
        script.onerror = () => reject(new Error(`echarts load failed: ${ECHARTS_URL}`));
        document.head.appendChild(script);
    });
    return _echartsPromise;
}

function platformEchartsTheme() {
    const styles = getComputedStyle(document.documentElement);
    const pick = (name, fallback) => {
        const value = styles.getPropertyValue(name).trim();
        return value.length > 0 ? value : fallback;
    };
    return {
        color: [
            pick('--accent', '#3b82f6'),
            pick('--success', '#22c55e'),
            pick('--warning', '#f59e0b'),
            pick('--danger', '#ef4444'),
            pick('--info', '#06b6d4'),
        ],
        backgroundColor: 'transparent',
        textStyle: {
            color: pick('--text-primary', '#e2e8f0'),
            fontFamily: pick('--font-sans', 'system-ui, sans-serif'),
        },
        title: {
            textStyle: { color: pick('--text-primary', '#e2e8f0') },
            subtextStyle: { color: pick('--text-secondary', '#94a3b8') },
        },
        legend: {
            textStyle: { color: pick('--text-secondary', '#94a3b8') },
        },
        categoryAxis: {
            axisLine: { lineStyle: { color: pick('--glass-border-subtle', '#334155') } },
            axisLabel: { color: pick('--text-secondary', '#94a3b8') },
            splitLine: { lineStyle: { color: pick('--glass-border-subtle', '#1e293b') } },
        },
        valueAxis: {
            axisLine: { lineStyle: { color: pick('--glass-border-subtle', '#334155') } },
            axisLabel: { color: pick('--text-secondary', '#94a3b8') },
            splitLine: { lineStyle: { color: pick('--glass-border-subtle', '#1e293b') } },
        },
    };
}

export class PlatformEchartsHost extends PlatformElement {
    static properties = {
        option: { type: Object, attribute: false },
        suspended: { type: Boolean, reflect: true },
        compact: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex: 1;
                min-width: 0;
                min-height: 0;
                height: 100%;
                width: 100%;
            }
            :host([compact]) {
                flex: none;
                height: 280px;
            }
            .chart {
                flex: 1;
                min-width: 0;
                min-height: 0;
                width: 100%;
                height: 100%;
            }
            .state {
                display: flex;
                flex: 1;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                padding: var(--space-4);
            }
            .state-error {
                color: var(--danger);
            }
        `,
    ];

    constructor() {
        super();
        this.option = null;
        this.suspended = false;
        this.compact = false;
        this._chart = null;
        this._resizeObserver = null;
        this._loadError = '';
        this._bootToken = 0;
    }

    updated(changed) {
        if (changed.has('option') || changed.has('suspended')) {
            void this._syncChart();
        }
    }

    connectedCallback() {
        super.connectedCallback();
        void this._syncChart();
    }

    disconnectedCallback() {
        this._teardown();
        super.disconnectedCallback();
    }

    _teardown() {
        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
            this._resizeObserver = null;
        }
        if (this._chart) {
            this._chart.dispose();
            this._chart = null;
        }
    }

    async _syncChart() {
        const token = ++this._bootToken;
        if (this.suspended) {
            return;
        }
        const option = this.option;
        if (!option || typeof option !== 'object') {
            this._loadError = 'echarts option required';
            this.requestUpdate();
            return;
        }
        this._loadError = '';
        await this.updateComplete;
        if (token !== this._bootToken) {
            return;
        }
        const root = this.renderRoot?.querySelector('.chart');
        if (!root) {
            return;
        }
        try {
            const echarts = await loadEcharts();
            if (token !== this._bootToken) {
                return;
            }
            if (!this._chart) {
                this._chart = echarts.init(root, null, { renderer: 'canvas' });
                this._resizeObserver = new ResizeObserver(() => {
                    if (this._chart && !this.suspended) {
                        this._chart.resize();
                    }
                });
                this._resizeObserver.observe(root);
            }
            const themed = {
                ...platformEchartsTheme(),
                ...option,
            };
            this._chart.setOption(themed, { notMerge: true });
            this._chart.resize();
        } catch (error) {
            this._loadError = error instanceof Error ? error.message : String(error);
            this.requestUpdate();
            this.emit('editor-error', { code: 'echarts_init_failed', message: this._loadError });
        }
    }

    exportPngDataUrl() {
        if (!this._chart) {
            throw new Error('echarts instance not ready');
        }
        return this._chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#0f172a' });
    }

    render() {
        if (this._loadError) {
            return html`<div class="state state-error">${this._loadError}</div>`;
        }
        if (!this.option) {
            return html`<div class="state">No chart option</div>`;
        }
        return html`<div class="chart" part="chart"></div>`;
    }
}

customElements.define('platform-echarts-host', PlatformEchartsHost);
