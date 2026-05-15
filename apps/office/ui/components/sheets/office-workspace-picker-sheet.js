/**
 * office-workspace-picker-sheet — bottom-sheet выбора рабочего пространства Документов
 * (mobile shell 2026).
 *
 * Заменяет на мобиле выпадающий список namespace из крышки `office-sidebar`. Контент —
 * список namespaces текущей компании, тап → setPlatformNamespaceSelection. На уровне
 * платформы tabs bottom-nav обращаются к этому sheet через `{ sheet: 'office.workspace_picker' }`.
 *
 * kind: 'office.workspace_picker'
 */

import { html, css } from 'lit';
import { PlatformBottomSheet } from '@platform/lib/components/layout/platform-bottom-sheet.js';
import { registerBottomSheetKind } from '@platform/lib/utils/bottom-sheet-registry.js';
import {
    getPlatformNamespaceSidebarSelection,
    setPlatformNamespaceSelection,
} from '@platform/lib/utils/platform-namespace.js';
import { namespacesResource } from '../../events/resources/namespaces.resource.js';
import '@platform/lib/components/platform-icon.js';

const FACTORY_NAME = namespacesResource.name;

export class OfficeWorkspacePickerSheet extends PlatformBottomSheet {
    static bottomSheetKind = 'office.workspace_picker';
    static i18nNamespace = 'documents';

    static styles = [
        PlatformBottomSheet.styles,
        css`
            .ws-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .ws-item {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
                text-align: left;
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }

            .ws-item:hover {
                background: var(--glass-tint-medium);
                border-color: var(--glass-border-medium);
            }

            .ws-item:active {
                transform: scale(0.98);
            }

            .ws-item.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
                font-weight: var(--font-semibold);
            }

            .ws-icon {
                color: var(--accent);
                display: inline-flex;
            }
        `,
    ];

    constructor() {
        super();
        this.snap = 'half';
        this._namespaces = this.useResource(FACTORY_NAME);
        this._authSel = this.select((s) => s.auth.user);
        this._namespaceSelectionByCompany = this.select(
            (s) => s.ui.namespace.selectionByCompany,
        );
    }

    connectedCallback() {
        super.connectedCallback();
        this.heading = this.t('workspace_picker.title');
        this._namespaces.load(null);
    }

    _currentSelection() {
        const user = this._authSel.value;
        const map = this._namespaceSelectionByCompany.value || {};
        if (!user || typeof user.company_id !== 'string') return null;
        const cid = user.company_id.trim();
        if (cid.length === 0) return null;
        if (Object.prototype.hasOwnProperty.call(map, cid)) {
            const entry = map[cid];
            return entry === 'all' ? null : entry;
        }
        const sidebar = getPlatformNamespaceSidebarSelection(cid);
        return sidebar === 'all' ? null : sidebar;
    }

    _select(value) {
        const user = this._authSel.value;
        if (!user || typeof user.company_id !== 'string') {
            throw new Error('office-workspace-picker-sheet: cannot change namespace without active company_id');
        }
        setPlatformNamespaceSelection(user.company_id, value);
        this._requestClose();
    }

    renderBody() {
        const items = Array.isArray(this._namespaces.items) ? this._namespaces.items : [];
        const current = this._currentSelection();
        return html`
            <div class="ws-list">
                ${items.map((ns) => {
                    const name = typeof ns.name === 'string' ? ns.name : '';
                    const title = typeof ns.title === 'string' && ns.title.length > 0 ? ns.title : name;
                    const active = current === name;
                    return html`
                        <button
                            type="button"
                            class="ws-item ${active ? 'active' : ''}"
                            @click=${() => this._select(name)}
                        >
                            <span>${title}</span>
                            ${active
                                ? html`<span class="ws-icon"><platform-icon name="check" size="18"></platform-icon></span>`
                                : ''}
                        </button>
                    `;
                })}
            </div>
        `;
    }
}

customElements.define('office-workspace-picker-sheet', OfficeWorkspacePickerSheet);
registerBottomSheetKind(
    OfficeWorkspacePickerSheet.bottomSheetKind,
    'office-workspace-picker-sheet',
);
