/**
 * Interface editor toolbar: undo/redo, target surface, viewport presets +
 * custom size, overlay toggles (grid/baseline/rulers/guides/snap), zoom with
 * fit, parity badge, preview / run / open on device / publish.
 */
import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

export class FlowsInterfaceToolbar extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        state: { attribute: false },
        parity: { attribute: false },
        canUndo: { type: Boolean, attribute: 'can-undo' },
        canRedo: { type: Boolean, attribute: 'can-redo' },
        canPublish: { type: Boolean, attribute: 'can-publish' },
    };

    static styles = [PlatformElement.styles, css`
        :host { display: block; }
        .bar {
            display: flex; align-items: center; gap: 4px; padding: 8px 12px;
            border-bottom: 1px solid var(--border-subtle);
            background: var(--glass-solid-medium); overflow-x: auto;
        }
        .group {
            display: flex; align-items: center; gap: 2px; padding-right: 10px; margin-right: 2px;
            border-right: 1px solid var(--border-subtle); flex-shrink: 0;
        }
        .group:last-of-type { border-right: none; padding-right: 0; margin-right: 0; }
        .group--selects { gap: 6px; }
        select, input {
            height: 28px; border: 1px solid var(--border-subtle); border-radius: var(--radius-md);
            background: var(--bg-elevated); color: inherit; padding: 0 8px; font: inherit; font-size: 12px;
        }
        input.size { width: 56px; }
        .x { color: var(--text-tertiary); font-size: 11px; }
        .spacer { flex: 1; min-width: 8px; }
        .badge {
            white-space: nowrap; padding: 4px 9px; border-radius: 999px;
            background: color-mix(in srgb, var(--success), transparent 86%);
            color: var(--success); font-size: 11px; font-weight: 700; flex-shrink: 0;
        }
        .badge[data-ok="false"] {
            background: color-mix(in srgb, var(--warning), transparent 86%);
            color: var(--warning);
        }
        .publish-blocked { color: var(--error); font-size: 11px; white-space: nowrap; }
        .run-label { margin-inline-start: 2px; }
    `];

    constructor() {
        super();
        this.state = {};
        this.parity = { exact: false, label: '' };
        this.canUndo = false;
        this.canRedo = false;
        this.canPublish = true;
    }

    _toggleIcon({ label, icon, key, eventName }) {
        const active = this.state?.[key] === true;
        return html`<platform-button
            density="compact"
            variant=${active ? 'secondary' : 'ghost'}
            icon-only
            title=${label}
            aria-label=${label}
            aria-pressed=${active ? 'true' : 'false'}
            @click=${() => this.emit(eventName, {})}
        ><platform-icon name=${icon} size="15"></platform-icon></platform-button>`;
    }

    _iconAction({ label, icon, eventName, variant = 'ghost' }) {
        return html`<platform-button
            density="compact"
            variant=${variant}
            icon-only
            title=${label}
            aria-label=${label}
            @click=${() => this.emit(eventName, {})}
        ><platform-icon name=${icon} size="15"></platform-icon></platform-button>`;
    }

    render() {
        const s = this.state || {};
        const isCustomViewport = s.viewportProfile === 'custom';
        const previewLabel = s.previewMode
            ? this.t('interface_editor.mode_edit')
            : this.t('interface_editor.mode_preview');
        const runLabel = s.runMode
            ? this.t('interface_editor.run_stop')
            : this.t('interface_editor.run_with_flow');
        return html`<div class="bar">
            <div class="group">
                <platform-button density="compact" variant="ghost" icon-only
                    title=${this.t('interface_editor.undo')}
                    aria-label=${this.t('interface_editor.undo')}
                    ?disabled=${!this.canUndo}
                    @click=${() => this.emit('undo', {})}
                ><platform-icon name="undo" size="15"></platform-icon></platform-button>
                <platform-button density="compact" variant="ghost" icon-only
                    title=${this.t('interface_editor.redo')}
                    aria-label=${this.t('interface_editor.redo')}
                    ?disabled=${!this.canRedo}
                    @click=${() => this.emit('redo', {})}
                ><platform-icon name="redo" size="15"></platform-icon></platform-button>
            </div>
            <div class="group group--selects">
                <select
                    data-canon="combobox"
                    aria-label=${this.t('interface_editor.target_surface')}
                    .value=${s.targetSurface || 'page'}
                    @change=${(event) => this.emit('target-change', { target: event.target.value })}
                >
                    <option value="page">${this.t('interface_editor.target_page')}</option>
                    <option value="panel">${this.t('interface_editor.target_panel')}</option>
                    <option value="drawer">${this.t('interface_editor.target_drawer')}</option>
                    <option value="inline">${this.t('interface_editor.target_inline')}</option>
                </select>
                <select
                    data-canon="combobox"
                    aria-label=${this.t('interface_editor.viewport')}
                    .value=${s.viewportProfile || 'desktop-wide'}
                    @change=${(event) => this.emit('viewport-change', { profile: event.target.value })}
                >
                    <option value="mobile-compact">390 × 844</option>
                    <option value="tablet-medium">768 × 1024</option>
                    <option value="desktop-wide">1440 × 960</option>
                    <option value="embed-inline">420 × 680</option>
                    <option value="custom">${this.t('interface_editor.viewport_custom')}</option>
                </select>
                ${isCustomViewport ? html`
                    <input class="size" type="number" data-canon="inline-edit" min="280" max="3840"
                        aria-label=${this.t('interface_editor.viewport_width')}
                        .value=${String(s.customWidth || 1440)}
                        @change=${(event) => this.emit('viewport-change', {
                            profile: 'custom',
                            width: Number(event.target.value),
                            height: Number(s.customHeight || 900),
                        })}
                    >
                    <span class="x">×</span>
                    <input class="size" type="number" data-canon="inline-edit" min="280" max="3840"
                        aria-label=${this.t('interface_editor.viewport_height')}
                        .value=${String(s.customHeight || 900)}
                        @change=${(event) => this.emit('viewport-change', {
                            profile: 'custom',
                            width: Number(s.customWidth || 1440),
                            height: Number(event.target.value),
                        })}
                    >
                ` : nothing}
            </div>
            <div class="group">
                ${this._toggleIcon({
                    label: this.t('interface_editor.toggle_grid'),
                    icon: 'apps',
                    key: 'gridVisible',
                    eventName: 'grid-toggle',
                })}
                ${this._toggleIcon({
                    label: this.t('interface_editor.toggle_baseline'),
                    icon: 'baseline',
                    key: 'baselineVisible',
                    eventName: 'baseline-toggle',
                })}
                ${this._toggleIcon({
                    label: this.t('interface_editor.toggle_rulers'),
                    icon: 'ruler',
                    key: 'rulersVisible',
                    eventName: 'rulers-toggle',
                })}
                ${this._toggleIcon({
                    label: this.t('interface_editor.toggle_guides'),
                    icon: 'guides',
                    key: 'guidesVisible',
                    eventName: 'guides-toggle',
                })}
                ${this._toggleIcon({
                    label: this.t('interface_editor.toggle_snap'),
                    icon: 'magnet',
                    key: 'snapEnabled',
                    eventName: 'snap-toggle',
                })}
                ${this._toggleIcon({
                    label: this.t('interface_editor.toggle_data_flow'),
                    icon: 'circular-connection',
                    key: 'dataFlowVisible',
                    eventName: 'data-flow-toggle',
                })}
            </div>
            <div class="group group--selects">
                <select
                    data-canon="combobox"
                    aria-label=${this.t('interface_editor.zoom')}
                    .value=${String(s.zoom || 1)}
                    @change=${(event) => this.emit('zoom-change', { zoom: event.target.value })}
                >
                    <option value="fit">${this.t('interface_editor.zoom_fit')}</option>
                    <option value="0.5">50%</option>
                    <option value="0.75">75%</option>
                    <option value="1">100%</option>
                    <option value="1.25">125%</option>
                    <option value="1.5">150%</option>
                    <option value="2">200%</option>
                </select>
            </div>
            <div class="group">
                ${this._iconAction({
                    label: this.t('interface_editor.templates'),
                    icon: 'layers',
                    eventName: 'templates-open',
                })}
            </div>
            <div class="spacer"></div>
            ${this.canPublish ? nothing : html`<span class="publish-blocked">${this.t('interface_editor.publish_blocked')}</span>`}
            <span class="badge" data-ok=${this.parity?.exact ? 'true' : 'false'}>${this.parity?.label || ''}</span>
            ${this._iconAction({
                label: previewLabel,
                icon: s.previewMode ? 'edit' : 'eye',
                eventName: 'preview-toggle',
            })}
            <platform-button
                density="compact"
                variant="primary"
                title=${runLabel}
                aria-label=${runLabel}
                @click=${() => this.emit('run-toggle', {})}
            >
                <platform-icon name=${s.runMode ? 'stop' : 'play'} size="15"></platform-icon>
                <span class="run-label">${runLabel}</span>
            </platform-button>
            ${this._iconAction({
                label: this.t('interface_editor.open_on_device'),
                icon: 'monitor',
                eventName: 'open-device',
                variant: 'secondary',
            })}
        </div>`;
    }
}

if (!customElements.get('flows-interface-toolbar')) {
    customElements.define('flows-interface-toolbar', FlowsInterfaceToolbar);
}
