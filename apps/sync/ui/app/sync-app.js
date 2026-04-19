/**
 * SyncApp — PlatformApp для сервиса Sync.
 *
 * Все доменные операции описаны фабриками в `apps/sync/ui/events/resources/*.resource.js`.
 * Транспорт операций — `transport: 'ws'` (single-socket request-reply через
 * `/sync/api/ws/notifications`), REST — байт-в-байт зеркало для CLI / SDK /
 * гостевых сценариев. Push-события приходят через `platform:ui_events` и
 * автоматически диспатчатся в bus core ws-effect'ом.
 *
 * Маршруты задаются через `createRouterEffect`; рендер страниц — switch по
 * `routeKey` в `renderRoute`.
 */

import { html, css } from 'lit';
import { PlatformApp, renderPlatformAppShell } from '@platform/lib/base/PlatformApp.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import { createRouterEffect } from '@platform/lib/events/effects/router.effect.js';
import '@platform/lib/components/app-loader.js';
import '@platform/lib/components/layout/platform-island.js';
import '@platform/lib/components/platform-shell-page.js';

import { spacesResource } from '../events/resources/spaces.resource.js';
import { channelsResource, channelMarkReadOp, channelTypingOp, channelAddMemberOp,
         channelMembersListOp, channelNotificationsUpdateOp } from '../events/resources/channels.resource.js';
import { messagesResource } from '../events/resources/messages.resource.js';
import { threadsResource } from '../events/resources/threads.resource.js';
import { companyMembersResource, sharedChannelsOp } from '../events/resources/members.resource.js';
import { presenceResource } from '../events/resources/presence.resource.js';
import { callTokenOp, callStatusOp, callTurnOp, callRecordingsListOp,
         callInviteOp, callAcceptOp, callDeclineOp, callHangupOp,
         callRecordingStartOp, callRecordingStopOp, callAdminTransferOp,
         callSignalOp, callLinksScheduledResource, callLinkCreateOp,
         callLinkUpdateOp, callLinkRemoveOp, callJoinInfoOp,
         callJoinAcceptOp, callUiResource } from '../events/resources/calls.resource.js';
import { fileUploadOp } from '../events/resources/files.resource.js';
import { gitResourceUpsertOp, gitResourceGetOp } from '../events/resources/git-resources.resource.js';
import { createSyncPersistEffect } from '../events/sync-persist.effect.js';

const SYNC_ROUTES = [
    { key: 'shell',           path: '' },
    { key: 'channel',         path: 'c/:channelId' },
    { key: 'space',           path: 'space/:spaceId' },
    { key: 'calls_scheduled', path: 'calls/scheduled' },
    { key: 'settings',        path: 'settings' },
    { key: 'call_join',       path: 'join/:linkToken' },
];

export class SyncApp extends PlatformApp {
    static defaultI18nNamespace = 'sync';

    constructor() {
        super();
        this._incomingCallDispatched = new Set();
        this._wsEverConnected = false;
        this._authUserSel = this.select((s) => s.auth && s.auth.user ? s.auth.user : null);
        this._channelsSliceSel = this.select((s) => s.syncChannels);
        this.useEvent('sync/call/incoming', (event) => this._onIncomingCall(event));
        this.useEvent('sync/call/ended', (event) => this._onCallEnded(event));
        this.useEvent(CoreEvents.WS_CONNECTED, () => this._onWsConnected());
    }

    _resolveSelectedChannelId() {
        const slice = this._channelsSliceSel.value;
        if (!slice) return '';
        const id = slice.selectedChannelId;
        return typeof id === 'string' ? id : '';
    }

    _resolveMyUserId() {
        const me = this._authUserSel.value;
        if (!me || typeof me.user_id !== 'string') return '';
        return me.user_id;
    }

    _onWsConnected() {
        if (!this._wsEverConnected) {
            this._wsEverConnected = true;
            return;
        }
        // reconnect: redis pub/sub не хранит историю, нужно перезагрузить.
        this.dispatch(channelsResource.events.LIST_REQUESTED, null);
        const selectedChannelId = this._resolveSelectedChannelId();
        if (selectedChannelId !== '') {
            this.dispatch(messagesResource.events.REQUESTED, { channel_id: selectedChannelId, limit: 50 });
        }
    }

    _onIncomingCall(event) {
        const p = event && event.payload;
        if (!p || typeof p.call_id !== 'string') return;
        const myId = this._resolveMyUserId();
        if (typeof p.initiator_user_id === 'string' && p.initiator_user_id === myId) return;
        if (this._incomingCallDispatched.has(p.call_id)) return;
        this._incomingCallDispatched.add(p.call_id);
        const callType = typeof p.call_type === 'string' ? p.call_type : 'video';
        const channelId = typeof p.channel_id === 'string' ? p.channel_id : '';
        let callerUserId = '';
        if (typeof p.created_by_user_id === 'string') callerUserId = p.created_by_user_id;
        else if (typeof p.initiator_user_id === 'string') callerUserId = p.initiator_user_id;
        const callerDisplayName = typeof p.caller_display_name === 'string' ? p.caller_display_name : '';
        const channelDisplayName = typeof p.channel_display_name === 'string' ? p.channel_display_name : '';
        this.openModal('sync.call_incoming', {
            callId: p.call_id,
            callType,
            channelId,
            callerUserId,
            callerDisplayName,
            channelDisplayName,
        });
    }

    _onCallEnded(event) {
        const p = event && event.payload;
        if (p && typeof p.call_id === 'string') {
            this._incomingCallDispatched.delete(p.call_id);
        }
        this.closeModal('sync.call_incoming');
    }

    static factories = [
        spacesResource,
        channelsResource,
        channelMarkReadOp,
        channelTypingOp,
        channelAddMemberOp,
        channelMembersListOp,
        channelNotificationsUpdateOp,
        messagesResource,
        threadsResource,
        companyMembersResource,
        sharedChannelsOp,
        presenceResource,
        callTokenOp,
        callStatusOp,
        callTurnOp,
        callRecordingsListOp,
        callInviteOp,
        callAcceptOp,
        callDeclineOp,
        callHangupOp,
        callRecordingStartOp,
        callRecordingStopOp,
        callAdminTransferOp,
        callSignalOp,
        callLinksScheduledResource,
        callLinkCreateOp,
        callLinkUpdateOp,
        callLinkRemoveOp,
        callJoinInfoOp,
        callJoinAcceptOp,
        callUiResource,
        fileUploadOp,
        gitResourceUpsertOp,
        gitResourceGetOp,
    ];

    static styles = [
        PlatformApp.styles,
        css`
            :host {
                display: block;
                width: 100%;
                height: 100vh;
                background: var(--bg-gradient);
                padding-top: env(safe-area-inset-top, 0);
                padding-bottom: env(safe-area-inset-bottom, 0);
            }
            @media (max-width: 767px) {
                :host {
                    height: 100dvh;
                }
            }
        `,
    ];

    getBaseUrl() {
        return '/sync';
    }

    getRoutes() {
        return [];
    }

    getServiceEffects() {
        return [
            createRouterEffect({ baseUrl: '/sync', routes: SYNC_ROUTES }),
            createSyncPersistEffect(),
        ];
    }

    renderRoute(routeKey, params) {
        if (routeKey === 'call_join') {
            return html`<sync-call-join-page .linkToken=${params.linkToken}></sync-call-join-page>`;
        }
        return html`
            <platform-shell-page>
                <sync-sidebar slot="sidebar"></sync-sidebar>
                <platform-island slot="main">${this._renderInner(routeKey, params)}</platform-island>
            </platform-shell-page>
        `;
    }

    _renderInner(routeKey, params) {
        switch (routeKey) {
            case 'shell':
                return html`<sync-shell-page></sync-shell-page>`;
            case 'channel':
                return html`<sync-channel-page .channelId=${params.channelId}></sync-channel-page>`;
            case 'space':
                return html`<sync-space-page .spaceId=${params.spaceId}></sync-space-page>`;
            case 'calls_scheduled':
                return html`<sync-calls-scheduled-page></sync-calls-scheduled-page>`;
            case 'settings':
                return html`<sync-settings-page></sync-settings-page>`;
            default:
                return html`<sync-shell-page></sync-shell-page>`;
        }
    }

    render() {
        const shell = renderPlatformAppShell(this);
        if (shell !== null) return shell;
        if (!this._servicesInitialized || !this._authChecked) {
            return html`<app-loader></app-loader>`;
        }
        if (!this._isAuthenticated) {
            return html`<app-loader></app-loader>`;
        }
        return super.render();
    }
}

customElements.define('sync-app', SyncApp);
