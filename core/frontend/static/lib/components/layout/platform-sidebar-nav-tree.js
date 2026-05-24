/**
 * PlatformSidebarNavTree — иерархическое меню для shell-сайдбара (доменно-нейтральное).
 * Хост передаёт дерево узлов и вызывает navigate() по событию pick.
 *
 * Модель узла (лист): id, label, icon?, routeKey, search? (строка query с ведущим ?).
 * Модель узла (группа): id, label, icon?, children[] (routeKey на группе не задаётся).
 */
import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { sidebarNavItemStyles } from '../../styles/shared/sidebar.styles.js';
import {
    readSidebarNavTreeExpanded,
    writeSidebarNavTreeExpanded,
} from '../../utils/sidebar-nav-tree-preference.js';
import '../platform-icon.js';

function _normalizeSearch(search) {
    if (search === undefined || search === null) return '';
    if (typeof search !== 'string') {
        throw new Error('PlatformSidebarNavTree: search must be a string');
    }
    if (search.length === 0) return '';
    if (!search.startsWith('?')) {
        throw new Error('PlatformSidebarNavTree: search must start with ?');
    }
    return search;
}

export class PlatformSidebarNavTree extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        nodes: { type: Array },
        activeItemId: { type: String, attribute: 'active-item-id' },
        /** Совпадение с текущим URL: pathname без base + search */
        activePath: { type: String, attribute: 'active-path' },
        collapsed: { type: Boolean, reflect: true },
        /**
         * Непустая строка: читать/писать свёрнутые группы в localStorage
         * (`sidebar-nav-tree-preference`). Смена scope перезагружает состояние.
         */
        storageScope: { type: String, attribute: 'storage-scope' },
    };

    static styles = [
        PlatformElement.styles,
        sidebarNavItemStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                width: 100%;
                min-width: 0;
            }
            :host([collapsed]) .nav-tree-children,
            :host([collapsed]) .nav-item-label {
                display: none;
            }
            :host([collapsed]) .nav-item {
                justify-content: center;
                padding: var(--space-2);
            }
            :host([collapsed]) .nav-tree-group {
                margin: 0;
            }
            .nav-tree-group {
                margin-bottom: var(--space-2);
            }
            .nav-tree-group-toggle:disabled {
                cursor: default;
                opacity: 0.7;
            }
            .nav-tree-children {
                display: flex;
                flex-direction: column;
                gap: 2px;
                padding-left: var(--space-2);
                border-left: var(--sidebar-nav-tree-children-border, 1px solid var(--glass-border-subtle));
                margin-left: var(--space-3);
            }
            .nav-tree-leaf .nav-item {
                padding-left: var(--space-2);
            }
        `,
    ];

    constructor() {
        super();
        this.nodes = [];
        this.activeItemId = '';
        this.activePath = '';
        this.collapsed = false;
        this.storageScope = '';
        this._expanded = Object.create(null);
    }

    willUpdate(changedProperties) {
        if (changedProperties.has('storageScope')) {
            const scope = this.storageScope;
            if (typeof scope === 'string' && scope.trim().length > 0) {
                this._expanded = Object.assign(
                    Object.create(null),
                    readSidebarNavTreeExpanded(scope.trim()),
                );
            } else {
                this._expanded = Object.create(null);
            }
        }
        super.willUpdate(changedProperties);
    }

    _isLeafActive(node) {
        if (typeof node.id !== 'string' || node.id.length === 0) return false;
        if (this.activeItemId !== '' && node.id === this.activeItemId) return true;
        if (typeof this.activePath !== 'string' || this.activePath.length === 0) return false;
        const rk = node.routeKey;
        const sch = _normalizeSearch(node.search);
        if (typeof rk !== 'string' || rk.length === 0) return false;
        const tail = `${rk}${sch}`;
        if (this.activePath === tail) return true;
        if (sch.length > 0 && this.activePath.endsWith(sch) && this.activePath.includes(rk)) return true;
        return false;
    }

    _toggleGroup(id) {
        if (typeof id !== 'string' || id.length === 0) return;
        if (this.collapsed) return;
        const curExpanded = this._expanded[id] !== false;
        const nextExpanded = !curExpanded;
        const next = { ...this._expanded };
        if (nextExpanded) {
            delete next[id];
        } else {
            next[id] = false;
        }
        this._expanded = next;
        this.requestUpdate();
        const scope = this.storageScope;
        if (typeof scope === 'string' && scope.trim().length > 0) {
            writeSidebarNavTreeExpanded(scope.trim(), this._expanded);
        }
    }

    _onLeafClick(node) {
        if (!node || typeof node.routeKey !== 'string' || node.routeKey.length === 0) {
            throw new Error('PlatformSidebarNavTree: leaf requires routeKey');
        }
        const search = _normalizeSearch(node.search);
        this.emit('pick', {
            id: node.id,
            routeKey: node.routeKey,
            search,
        });
    }

    _renderLeaf(node) {
        const icon = typeof node.icon === 'string' && node.icon.length > 0 ? node.icon : 'chevron-right';
        const active = this._isLeafActive(node);
        return html`
            <div class="nav-tree-leaf">
                <button
                    type="button"
                    class="nav-item ${active ? 'active' : ''}"
                    @click=${() => this._onLeafClick(node)}
                >
                    <div class="nav-item-icon">
                        <platform-icon name=${icon} size="18"></platform-icon>
                    </div>
                    <span class="nav-item-label">${node.label}</span>
                </button>
            </div>
        `;
    }

    _renderGroup(node) {
        const id = node.id;
        const children = Array.isArray(node.children) ? node.children : [];
        const expanded = this._expanded[id] !== false;
        const groupIconRaw = typeof node.icon === 'string' && node.icon.length > 0 ? node.icon : '';
        const icon = groupIconRaw.length > 0 ? groupIconRaw : 'chevron-right';
        return html`
            <div class="nav-tree-group">
                <div class="nav-tree-leaf">
                    <button
                        type="button"
                        class="nav-item nav-tree-group-toggle"
                        ?disabled=${this.collapsed}
                        @click=${() => this._toggleGroup(id)}
                    >
                        <div class="nav-item-icon">
                            <platform-icon name=${icon} size="18"></platform-icon>
                        </div>
                        <span class="nav-item-label">${node.label}${expanded ? ' \u2212' : ' +'}</span>
                    </button>
                </div>
                ${expanded
                    ? html`<div class="nav-tree-children">${children.map((ch) => this._renderNode(ch))}</div>`
                    : null}
            </div>
        `;
    }

    _renderNode(node) {
        if (!node || typeof node !== 'object') {
            throw new Error('PlatformSidebarNavTree: invalid node');
        }
        const children = Array.isArray(node.children) ? node.children : [];
        const hasChildren = children.length > 0;
        const hasRoute = typeof node.routeKey === 'string' && node.routeKey.length > 0;
        if (hasChildren && hasRoute) {
            throw new Error(`PlatformSidebarNavTree: node ${node.id} cannot have both children and routeKey`);
        }
        if (!hasChildren && !hasRoute) {
            throw new Error(`PlatformSidebarNavTree: node ${node.id} must be leaf (routeKey) or group (children)`);
        }
        if (hasChildren) return this._renderGroup(node);
        return this._renderLeaf(node);
    }

    render() {
        const nodes = Array.isArray(this.nodes) ? this.nodes : [];
        return html`${nodes.map((n) => this._renderNode(n))}`;
    }
}

customElements.define('platform-sidebar-nav-tree', PlatformSidebarNavTree);
