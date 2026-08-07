/**
 * Publish problems: expandable full list with severity, click focuses the
 * offending component on the canvas, quick fix for a missing submit.
 */
import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

export class FlowsInterfaceProblemsPanel extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        problems: { attribute: false },
        _expanded: { state: true },
    };

    static styles = [PlatformElement.styles, css`
        :host {
            display: block;
            background: transparent;
            font-size: 11px;
        }
        .bar {
            display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
            min-height: 34px; padding: 5px 12px; justify-content: flex-end;
        }
        .ok { color: var(--success); }
        .count { color: var(--error); font-weight: 650; cursor: pointer; }
        .count[data-warn="true"] { color: var(--warning); }
        .item {
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 360px;
            color: inherit; cursor: pointer; text-align: left;
        }
        .item:hover { color: var(--accent); text-decoration: underline; }
        .count:focus-visible, .item:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
        .list {
            max-height: 180px; overflow: auto; border-top: 1px solid var(--border-subtle);
            padding: 6px 12px; display: grid; gap: 4px;
        }
        .row { display: flex; align-items: center; gap: 8px; min-width: 0; }
        .severity {
            flex-shrink: 0; width: 8px; height: 8px; border-radius: 50%;
            background: var(--error);
        }
        .severity[data-level="warning"] { background: var(--warning); }
        .row .item { max-width: none; flex: 1; }
        .code { color: var(--text-tertiary); flex-shrink: 0; }
    `];

    constructor() {
        super();
        this.problems = [];
        this._expanded = false;
    }

    get _needsSubmitFix() {
        return (this.problems || []).some((problem) => (
            problem.code === 'submit.missing'
            || problem.code === 'submit.unreachable'
            || problem.code === 'submit.form_unreachable'
        ));
    }

    _focus(problem) {
        if (!problem.componentId) return;
        this.emit('problem-focus', {
            componentId: problem.componentId,
            surfaceId: problem.surfaceId || null,
        });
    }

    _problemLink(problem) {
        return html`<span
            class="item"
            role="button"
            tabindex="0"
            @click=${() => this._focus(problem)}
            @keydown=${(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    this._focus(problem);
                }
            }}
        >${problem.message}</span>`;
    }

    render() {
        const problems = Array.isArray(this.problems) ? this.problems : [];
        if (!problems.length) {
            return html`<div class="bar"><span class="ok">${this.t('interface_editor.problems_none')}</span></div>`;
        }
        const errors = problems.filter((problem) => problem.severity === 'error');
        return html`
            <div class="bar">
                <span
                    class="count"
                    role="button"
                    tabindex="0"
                    data-warn=${errors.length === 0 ? 'true' : 'false'}
                    aria-expanded=${this._expanded ? 'true' : 'false'}
                    @click=${() => { this._expanded = !this._expanded; }}
                    @keydown=${(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            this._expanded = !this._expanded;
                        }
                    }}
                >${this.t('interface_editor.problems_count', { count: String(problems.length) })}</span>
                ${problems.slice(0, 2).map((problem) => this._problemLink(problem))}
                ${this._needsSubmitFix
                    ? html`<platform-button
                        density="compact"
                        variant="ghost"
                        @click=${() => this.emit('quick-fix-submit', {})}
                    >${this.t('interface_editor.problems_add_submit')}</platform-button>`
                    : nothing}
            </div>
            ${this._expanded ? html`<div class="list">
                ${problems.map((problem) => html`
                    <div class="row">
                        <span class="severity" data-level=${problem.severity}></span>
                        ${this._problemLink(problem)}
                        <span class="code">${problem.code}</span>
                    </div>
                `)}
            </div>` : nothing}
        `;
    }
}

if (!customElements.get('flows-interface-problems-panel')) {
    customElements.define('flows-interface-problems-panel', FlowsInterfaceProblemsPanel);
}
