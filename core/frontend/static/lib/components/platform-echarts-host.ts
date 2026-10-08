/**
 * platform-echarts-host — Apache ECharts в Lit (lazy script, ResizeObserver, dispose).
 */
import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from '../lit-shim.js';
import { PlatformElement } from '../platform-element/index.js';

const ECHARTS_URL = '/static/core/assets/js/echarts/echarts.min.js';

interface EchartsInstance {
    setOption(option: unknown, opts?: { notMerge?: boolean }): void;
    resize(): void;
    dispose(): void;
    getDataURL(opts: { type: string; pixelRatio?: number; backgroundColor?: string }): string;
}

interface EchartsApi {
    init(el: HTMLElement, theme?: unknown, opts?: { renderer?: string }): EchartsInstance;
}

type EchartsWindow = Window & { echarts?: EchartsApi };

let _echartsPromise: Promise<EchartsApi> | null = null;

function loadEcharts(): Promise<EchartsApi> {
    const w = window as EchartsWindow;
    if (typeof window !== 'undefined' && w.echarts) {
        return Promise.resolve(w.echarts);
    }
    if (_echartsPromise) {
        return _echartsPromise;
    }
    _echartsPromise = new Promise<EchartsApi>((resolve, reject) => {
        const existing = document.querySelector(`script[data-platform-echarts="1"]`);
        if (existing && w.echarts) {
            resolve(w.echarts);
            return;
        }
        const script = document.createElement('script');
        script.src = ECHARTS_URL;
        script.async = true;
        script.dataset.platformEcharts = '1';
        script.onload = () => {
            if (!w.echarts) {
                reject(new Error('echarts global missing after load'));
                return;
            }
            resolve(w.echarts);
        };
        script.onerror = () => reject(new Error(`echarts load failed: ${ECHARTS_URL}`));
        document.head.appendChild(script);
    });
    return _echartsPromise;
}

function platformEchartsTheme() {
    const styles = getComputedStyle(document.documentElement);
    const pick = (name: string, fallback: string): string => {
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
    static override properties: PropertyDeclarations = {
        option: { type: Object, attribute: false },
        suspended: { type: Boolean, reflect: true },
        compact: { type: Boolean, reflect: true },
    };
    declare option: Record<string, unknown> | null;
    declare suspended: boolean;
    declare compact: boolean;

    static override styles: CSSResultGroup = [
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

    private _chart: EchartsInstance | null;
    private _resizeObserver: ResizeObserver | null;
    private _loadError: string;
    private _bootToken: number;

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

    override updated(changed: PropertyValues<this>): void {
        if (changed.has('option') || changed.has('suspended')) {
            void this._syncChart();
        }
    }

    override connectedCallback(): void {
        super.connectedCallback();
        void this._syncChart();
    }

    override disconnectedCallback(): void {
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
                this._chart = echarts.init(root as HTMLElement, undefined, { renderer: 'canvas' });
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

    override render(): TemplateResult {
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
