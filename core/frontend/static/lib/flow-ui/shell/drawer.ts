import { LitElement, html, nothing, type PropertyValues } from 'lit';
import '../components/platform-flow-ui.js';
import { resolveAgentIdentityImageSrc } from '../runtime/agent-identity-image.js';
import {
    clampCluster,
    createDefaultGeometry,
    DRAG_THRESHOLD_PX,
    gesturesAllowed,
    LAUNCHER_NAV_GAP_PX,
    MOBILE_MAX_WIDTH_PX,
    moveCluster,
    resizeFromSouthEast,
    VIEWPORT_MARGIN_DESKTOP_PX,
    VIEWPORT_MARGIN_MOBILE_PX,
    type DrawerViewport,
    type PlacedDrawerGeometry,
} from './drawer-geometry.js';
import { FLOW_UI_DRAWER_MOVE_START } from './drawer-move.js';
import { flowUIDrawerStyles } from './drawer.styles.js';
import {
    FLOW_UI_TOGGLE_EVENT,
    readEmbedDrawerGeometry,
    readLaraDrawerGeometry,
    writeEmbedDrawerGeometry,
    writeLaraDrawerGeometry,
} from './preferences.js';
import { flowUIText, resolveFlowUILocale } from '../utils/text.js';
import { isPlainRecord } from '../../events/payload.js';

function customDetail(event: Event): unknown {
    if (!(event instanceof CustomEvent)) return undefined;
    return event.detail;
}

function movePoint(detail: unknown): { clientX: number; clientY: number; pointerId: number } {
    if (!isPlainRecord(detail)) {
        throw new Error('flow-ui-drawer: move detail is required');
    }
    const clientX = detail.clientX;
    const clientY = detail.clientY;
    const pointerId = detail.pointerId;
    if (typeof clientX !== 'number' || !Number.isFinite(clientX)) {
        throw new Error('flow-ui-drawer: move detail.clientX must be a finite number');
    }
    if (typeof clientY !== 'number' || !Number.isFinite(clientY)) {
        throw new Error('flow-ui-drawer: move detail.clientY must be a finite number');
    }
    if (typeof pointerId !== 'number' || !Number.isFinite(pointerId)) {
        throw new Error('flow-ui-drawer: move detail.pointerId must be a finite number');
    }
    return { clientX, clientY, pointerId };
}

interface DrawerGesture {
    type: 'move' | 'resize' | 'launcher';
    pointerId: number;
    startX: number;
    startY: number;
    startCluster: PlacedDrawerGeometry | null;
    didMove: boolean;
    seOffsetX: number;
    seOffsetY: number;
}

export class FlowUIDrawer extends LitElement {
    declare open: boolean;
    declare expanded: boolean;
    declare config: Record<string, unknown>;
    declare _cluster: PlacedDrawerGeometry | null;
    declare _dragging: boolean;
    declare _identityImageUrl: string | null;
    declare _unavailable: boolean;
    private _boundToggleEventName: string | null;
    private _loadedPersistKey: string | null;
    private _gesture: DrawerGesture | null;
    private _toggle: (event: Event) => void;
    private _onExpandToggle: (event: Event) => void;
    private _onDrawerClose: () => void;
    private _onMoveStart: (event: Event) => void;
    private _onWindowPointerMove: (event: PointerEvent) => void;
    private _onWindowPointerUp: (event: PointerEvent) => void;
    private _onViewportResize: () => void;
    private _onIdentityChanged: (event: Event) => void;

    static override properties = {
        open: { type: Boolean, reflect: true },
        expanded: { type: Boolean, reflect: true },
        config: { attribute: false },
        _cluster: { state: true },
        _dragging: { state: true },
        _identityImageUrl: { state: true },
        _unavailable: { state: true },
    };

    static override styles = flowUIDrawerStyles;

    constructor() {
        super();
        this.open = false;
        this.expanded = false;
        this.config = {};
        this._cluster = null;
        this._dragging = false;
        this._identityImageUrl = null;
        this._unavailable = false;
        this._boundToggleEventName = null;
        this._loadedPersistKey = null;
        this._gesture = null;
        this._toggle = (event: Event) => {
            const detail = customDetail(event);
            if (isPlainRecord(detail) && Object.prototype.hasOwnProperty.call(detail, 'open')) {
                this.open = detail.open === true;
                return;
            }
            this.open = !this.open;
        };
        this._onExpandToggle = (event: Event) => {
            const detail = customDetail(event);
            if (isPlainRecord(detail) && Object.prototype.hasOwnProperty.call(detail, 'expanded')) {
                this.expanded = detail.expanded === true;
                return;
            }
            this.expanded = !this.expanded;
        };
        this._onDrawerClose = () => {
            this.open = false;
        };
        this._onMoveStart = (event: Event) => {
            this._beginMoveFromDetail(customDetail(event));
        };
        this._onWindowPointerMove = (event: PointerEvent) => {
            this._handlePointerMove(event);
        };
        this._onWindowPointerUp = (event: PointerEvent) => {
            this._handlePointerUp(event);
        };
        this._onViewportResize = () => {
            this._reclampToViewport(true);
        };
        this._onIdentityChanged = (event: Event) => {
            const detail = customDetail(event);
            if (!isPlainRecord(detail)) throw new Error('flow-ui-drawer: flow-ui-identity-changed detail required');
            const imageUrl = detail.image_url;
            if (imageUrl !== null && typeof imageUrl !== 'string') throw new Error('flow-ui-drawer: image_url must be string or null');
            this._identityImageUrl = imageUrl;
        };
    }

    override connectedCallback() {
        super.connectedCallback();
        this._bindToggleListener();
        this.addEventListener('flow-ui-drawer-expand-toggle', this._onExpandToggle);
        this.addEventListener('flow-ui-drawer-close', this._onDrawerClose);
        this.addEventListener(FLOW_UI_DRAWER_MOVE_START, this._onMoveStart);
        this.addEventListener('flow-ui-identity-changed', this._onIdentityChanged);
        globalThis.addEventListener('resize', this._onViewportResize);
        this._syncGeometryFromStore();
    }

    override disconnectedCallback() {
        this.removeEventListener('flow-ui-drawer-close', this._onDrawerClose);
        this.removeEventListener('flow-ui-drawer-expand-toggle', this._onExpandToggle);
        this.removeEventListener(FLOW_UI_DRAWER_MOVE_START, this._onMoveStart);
        this.removeEventListener('flow-ui-identity-changed', this._onIdentityChanged);
        globalThis.removeEventListener('resize', this._onViewportResize);
        this._unbindToggleListener();
        this._detachGestureListeners();
        super.disconnectedCallback();
    }

    override updated(changedProperties: PropertyValues<this>) {
        if (changedProperties.has('config')) {
            this._bindToggleListener();
            const persistKey = this._persistIdentityKey();
            if (persistKey !== this._loadedPersistKey) {
                this._syncGeometryFromStore();
            }
        }
        if (changedProperties.has('open')) {
            if (this.open !== true) {
                this.expanded = false;
            } else if (this._cluster !== null) {
                this._cluster = clampCluster(this._cluster, this._readViewport());
            }
            this.dispatchEvent(new CustomEvent('flow-ui-drawer-open-changed', {
                detail: { open: this.open === true },
                bubbles: true,
                composed: true,
            }));
        }
        if (changedProperties.has('expanded')) {
            if (this.expanded !== true && this._cluster !== null) {
                this._cluster = clampCluster(this._cluster, this._readViewport());
            }
            this.dispatchEvent(new CustomEvent('flow-ui-drawer-expanded-changed', {
                detail: { expanded: this.expanded === true },
                bubbles: true,
                composed: true,
            }));
        }
        this._syncHostAttributes();
    }

    _toggleEventName() {
        const name = this.config?.toggleEventName;
        if (name === null || name === undefined || name === '') return FLOW_UI_TOGGLE_EVENT;
        if (typeof name !== 'string') throw new Error('flow-ui-drawer: config.toggleEventName must be a string');
        return name;
    }

    _unbindToggleListener() {
        if (this._boundToggleEventName === null) return;
        globalThis.removeEventListener(this._boundToggleEventName, this._toggle);
        this._boundToggleEventName = null;
    }

    _bindToggleListener() {
        if (!this.isConnected) return;
        const next = this._toggleEventName();
        if (this._boundToggleEventName === next) return;
        this._unbindToggleListener();
        this._boundToggleEventName = next;
        globalThis.addEventListener(next, this._toggle);
    }

    private _credentials(config: Record<string, unknown>): string {
        if (typeof config.credentials !== 'string' || config.credentials.trim() === '') return 'include';
        return config.credentials;
    }

    _launcherPosition() {
        const position = this.config.launcherPosition;
        if (position === undefined || position === null || position === '') return 'bottom-right';
        if (position !== 'bottom-left' && position !== 'bottom-right') {
            throw new Error(
                `flow-ui-drawer: invalid launcherPosition ${JSON.stringify(position)}`,
            );
        }
        return position;
    }

    _readViewport() {
        const width = globalThis.innerWidth;
        const height = globalThis.innerHeight;
        if (typeof width !== 'number' || !Number.isFinite(width) || width <= 0) throw new Error('flow-ui-drawer: window.innerWidth is required');
        if (typeof height !== 'number' || !Number.isFinite(height) || height <= 0) throw new Error('flow-ui-drawer: window.innerHeight is required');
        return {
            width,
            height,
            margin: width <= MOBILE_MAX_WIDTH_PX
                ? VIEWPORT_MARGIN_MOBILE_PX
                : VIEWPORT_MARGIN_DESKTOP_PX,
            bottomInset: this._bottomNavInset(),
        };
    }

    private _bottomNavInset(): number {
        const root = this.getRootNode();
        const nav = root instanceof Document || root instanceof ShadowRoot
            ? root.querySelector('platform-bottom-nav')
            : null;
        if (!(nav instanceof HTMLElement)) return 0;
        const rect = nav.getBoundingClientRect();
        if (rect.height <= 0 || rect.top >= globalThis.innerHeight) return 0;
        return globalThis.innerHeight - rect.top + LAUNCHER_NAV_GAP_PX;
    }

    _gesturesEnabled() {
        if (this.expanded === true) return false;
        return gesturesAllowed(this._readViewport());
    }

    _persistIdentity() {
        const config = this.config;
        if (!config || typeof config !== 'object') return { kind: 'none', id: '' };
        const embedId = typeof config.embedId === 'string' ? config.embedId.trim() : '';
        if (embedId !== '') return { kind: 'embed', id: embedId };
        const branchId = typeof config.branchId === 'string' ? config.branchId.trim() : '';
        if (branchId !== '') return { kind: 'lara', id: branchId };
        return { kind: 'none', id: '' };
    }

    _persistIdentityKey() {
        const identity = this._persistIdentity();
        return `${identity.kind}:${identity.id}`;
    }

    _loadStoredGeometry() {
        const identity = this._persistIdentity();
        if (identity.kind === 'embed') return readEmbedDrawerGeometry(identity.id);
        if (identity.kind === 'lara') return readLaraDrawerGeometry(identity.id);
        return null;
    }

    _persistGeometry() {
        if (this._cluster === null) throw new Error('flow-ui-drawer: cluster is required to persist');
        if (this._gesturesEnabled() !== true) return;
        const identity = this._persistIdentity();
        if (identity.kind === 'embed') {
            writeEmbedDrawerGeometry(identity.id, this._cluster);
            return;
        }
        if (identity.kind === 'lara') {
            writeLaraDrawerGeometry(identity.id, this._cluster);
        }
    }

    _syncGeometryFromStore() {
        const viewport = this._readViewport();
        const stored = this._loadStoredGeometry();
        if (stored === null) {
            this._cluster = clampCluster(
                createDefaultGeometry(this._launcherPosition(), viewport),
                viewport,
            );
        } else {
            this._cluster = clampCluster(stored, viewport);
        }
        this._loadedPersistKey = this._persistIdentityKey();
    }

    private _reclampToViewport(persist: boolean) {
        if (this._cluster === null) {
            this._syncGeometryFromStore();
            return;
        }
        this._cluster = clampCluster(this._cluster, this._readViewport());
        if (persist === true && this._gesturesEnabled() === true) {
            this._persistGeometry();
        }
    }

    _syncHostAttributes() {
        const position = this._launcherPosition();
        if (this.getAttribute('data-embed-position') !== position) {
            this.setAttribute('data-embed-position', position);
        }
        const gestures = this._gesturesEnabled() === true ? 'on' : 'off';
        if (this.getAttribute('data-drawer-gestures') !== gestures) {
            this.setAttribute('data-drawer-gestures', gestures);
        }
        if (this._dragging === true) {
            if (this._gesture === null) throw new Error('flow-ui-drawer: gesture is required while dragging');
            this.setAttribute('data-drawer-dragging', this._gesture.type);
        } else if (this.hasAttribute('data-drawer-dragging')) {
            this.removeAttribute('data-drawer-dragging');
        }
        this._applyClusterCssVars();
    }

    _applyClusterCssVars() {
        this.style.setProperty('--drawer-bottom-inset', `${this._bottomNavInset()}px`);
        const cluster = this._cluster;
        if (cluster === null) return;
        this.style.setProperty('--drawer-panel-width', `${cluster.panelWidth}px`);
        this.style.setProperty('--drawer-panel-height', `${cluster.panelHeight}px`);
    }

    private _clusterStyle(kind: 'launcher' | 'panel'): string {
        const cluster = this._cluster;
        if (cluster === null || this._gesturesEnabled() !== true) return '';
        if (kind === 'launcher') return `left:${cluster.launcherLeft}px;top:${cluster.launcherTop}px`;
        return `left:${cluster.panelLeft}px;top:${cluster.panelTop}px;width:${cluster.panelWidth}px;height:${cluster.panelHeight}px`;
    }

    _attachGestureListeners() {
        globalThis.addEventListener('pointermove', this._onWindowPointerMove);
        globalThis.addEventListener('pointerup', this._onWindowPointerUp);
        globalThis.addEventListener('pointercancel', this._onWindowPointerUp);
    }

    _detachGestureListeners() {
        globalThis.removeEventListener('pointermove', this._onWindowPointerMove);
        globalThis.removeEventListener('pointerup', this._onWindowPointerUp);
        globalThis.removeEventListener('pointercancel', this._onWindowPointerUp);
        if (this._gesture !== null && typeof this.releasePointerCapture === 'function') {
            if (this.hasPointerCapture(this._gesture.pointerId)) {
                this.releasePointerCapture(this._gesture.pointerId);
            }
        }
        this._gesture = null;
        this._dragging = false;
    }

    private _capturePointer(pointerId: unknown) {
        if (typeof pointerId !== 'number' || !Number.isFinite(pointerId)) throw new Error('flow-ui-drawer: pointerId must be a finite number');
        if (typeof this.setPointerCapture !== 'function') return;
        this.setPointerCapture(pointerId);
    }

    private _beginGesture(type: DrawerGesture['type'], event: PointerEvent, offsets: { seOffsetX: unknown; seOffsetY: unknown }) {
        if (offsets === null || typeof offsets !== 'object' || Array.isArray(offsets)) throw new Error('flow-ui-drawer: gesture offsets are required');
        if (typeof offsets.seOffsetX !== 'number' || !Number.isFinite(offsets.seOffsetX)) throw new Error('flow-ui-drawer: seOffsetX must be a finite number');
        if (typeof offsets.seOffsetY !== 'number' || !Number.isFinite(offsets.seOffsetY)) throw new Error('flow-ui-drawer: seOffsetY must be a finite number');
        if (this._cluster === null) {
            this._syncGeometryFromStore();
        }
        const startCluster = this._cluster;
        if (startCluster === null) throw new Error('flow-ui-drawer: cluster is required');
        this._gesture = {
            type,
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            startCluster,
            didMove: false,
            seOffsetX: offsets.seOffsetX,
            seOffsetY: offsets.seOffsetY,
        };
        this._dragging = true;
        this._capturePointer(event.pointerId);
        this._attachGestureListeners();
    }

    private _beginMoveFromDetail(detail: unknown) {
        if (this._gesturesEnabled() !== true) return;
        const point = movePoint(detail);
        if (this._cluster === null) {
            this._syncGeometryFromStore();
        }
        const moveClusterStart = this._cluster;
        if (moveClusterStart === null) throw new Error('flow-ui-drawer: cluster is required');
        this._gesture = {
            type: 'move',
            pointerId: point.pointerId,
            startX: point.clientX,
            startY: point.clientY,
            startCluster: moveClusterStart,
            didMove: false,
            seOffsetX: 0,
            seOffsetY: 0,
        };
        this._dragging = true;
        this._capturePointer(point.pointerId);
        this._attachGestureListeners();
    }

    private _onLauncherPointerDown(event: PointerEvent) {
        if (event.button !== 0) return;
        if (this._gesturesEnabled() !== true) {
            this._gesture = {
                type: 'launcher',
                pointerId: event.pointerId,
                startX: event.clientX,
                startY: event.clientY,
                startCluster: this._cluster,
                didMove: false,
                seOffsetX: 0,
                seOffsetY: 0,
            };
            this._attachGestureListeners();
            return;
        }
        event.preventDefault();
        this._beginGesture('launcher', event, { seOffsetX: 0, seOffsetY: 0 });
    }

    private _onResizePointerDown(event: PointerEvent) {
        if (event.button !== 0) return;
        if (this._gesturesEnabled() !== true || this.open !== true) return;
        event.preventDefault();
        event.stopPropagation();
        if (this._cluster === null) {
            this._syncGeometryFromStore();
        }
        const cluster = this._cluster;
        if (cluster === null) throw new Error('flow-ui-drawer: cluster is required');
        this._beginGesture('resize', event, {
            seOffsetX: cluster.panelLeft + cluster.panelWidth - event.clientX,
            seOffsetY: cluster.panelTop + cluster.panelHeight - event.clientY,
        });
    }

    private _handlePointerMove(event: PointerEvent) {
        const gesture = this._gesture;
        if (gesture === null || event.pointerId !== gesture.pointerId) return;
        if (this._gesturesEnabled() !== true) return;
        const dx = event.clientX - gesture.startX;
        const dy = event.clientY - gesture.startY;
        if (gesture.didMove !== true && Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return;
        gesture.didMove = true;
        if (this._gesturesEnabled() !== true) return;
        const startCluster = gesture.startCluster;
        if (startCluster === null) return;
        if (gesture.type === 'resize') {
            this._cluster = resizeFromSouthEast(
                startCluster,
                event.clientX + gesture.seOffsetX,
                event.clientY + gesture.seOffsetY,
                this._readViewport(),
            );
        } else {
            this._cluster = moveCluster(startCluster, dx, dy, this._readViewport());
        }
        this.requestUpdate();
    }

    private _handlePointerUp(event: PointerEvent) {
        const gesture = this._gesture;
        if (gesture === null || event.pointerId !== gesture.pointerId) return;
        const didMove = gesture.didMove === true;
        const type = gesture.type;
        this._detachGestureListeners();
        this.requestUpdate();
        if (type === 'launcher' && didMove !== true) {
            this.open = !this.open;
            return;
        }
        if (didMove === true && this._gesturesEnabled() === true) {
            this._persistGeometry();
        }
    }

    override render() {
        const c = this.config;
        if (!c || typeof c !== 'object') throw new Error('flow-ui-drawer: config is required');
        if (typeof c.baseUrl !== 'string' || c.baseUrl.trim() === '') throw new Error('flow-ui-drawer: config.baseUrl is required');
        const companyId = typeof c.companyId === 'string' ? c.companyId : '';
        const voiceBaseUrl = typeof c.voiceBaseUrl === 'string' ? c.voiceBaseUrl : '';
        const platformUiOrigin = typeof c.platformUiOrigin === 'string' ? c.platformUiOrigin.trim().replace(/\/+$/, '') : '';
        if (platformUiOrigin !== '') {
            this.setAttribute('platform-ui-origin', platformUiOrigin);
        }
        const logoSrc = resolveAgentIdentityImageSrc({
            imageUrl: this._identityImageUrl,
            platformUiOrigin,
        });
        const locale = resolveFlowUILocale(typeof c.locale === 'string' ? c.locale : 'ru');
        const cluster = this._cluster;
        const gesturesOn = this._gesturesEnabled() === true;
        return html`<div
            class="panel"
            style=${gesturesOn && cluster !== null ? this._clusterStyle('panel') : ''}
        ><platform-flow-ui
            embed-id=${typeof c.embedId === 'string' ? c.embedId : ''}
            flow-id=${typeof c.flowId === 'string' ? c.flowId : ''}
            branch-id=${c.branchId || 'default'}
            base-url=${c.baseUrl}
            context-id=${typeof c.contextId === 'string' ? c.contextId : ''}
            company-id=${companyId}
            voice-base-url=${voiceBaseUrl}
            platform-ui-origin=${platformUiOrigin}
            display="drawer"
            profile=${c.profile || 'embed_public'}
            theme=${c.theme || 'auto'}
            locale=${c.locale || 'ru'}
            credentials=${this._credentials(c)}
            assistant-title=${typeof c.assistantTitle === 'string' ? c.assistantTitle : ''}
            ?drawer-expanded=${this.expanded === true}
            .getRequestHeaders=${c.getRequestHeaders}
            .getExtraMetadataVariables=${c.getExtraMetadataVariables}
            @flow-ui-unavailable=${() => { this._unavailable = true; this.open = false; }}
        ></platform-flow-ui>${this.open === true && gesturesOn === true
            ? html`<button
                type="button"
                class="resize-handle"
                aria-label=${flowUIText(locale, 'resize_aria')}
                title=${flowUIText(locale, 'resize_aria')}
                @pointerdown=${this._onResizePointerDown}
            ></button>`
            : nothing}</div>${c.showLauncher === false || this._unavailable === true
            ? html``
            : html`<button
                type="button"
                class="launcher"
                style=${gesturesOn && cluster !== null ? this._clusterStyle('launcher') : ''}
                aria-label=${this.open ? 'Close assistant' : 'Open assistant'}
                @pointerdown=${this._onLauncherPointerDown}
            ><img src=${logoSrc} alt="" aria-hidden="true"></button>`}`;
    }
}

if (!customElements.get('flow-ui-drawer')) customElements.define('flow-ui-drawer', FlowUIDrawer);
