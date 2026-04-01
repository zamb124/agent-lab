/**
 * Список встреч компании: фильтры, карточки, детали — в канонической PlatformModal (safe area, портал).
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { SyncStore } from '../store/sync.store.js';
import { hueFromString } from '../utils/sync-hue.js';

export class MeetingsModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        _meetingsChannelFilter: { state: true },
        _meetingsDateFrom: { state: true },
        _meetingsDateTo: { state: true },
        _meetingDetailsById: { state: true },
        _meetingsDetailsLoadingId: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        buttonStyles,
        css`
            :host([open]) .modal.full .modal-content:has(.meetings-modal-body) {
                display: flex;
                flex-direction: column;
                overflow: hidden;
                min-height: 0;
                padding: 0;
                margin: 0 var(--modal-content-inset, 8px) var(--modal-content-inset, 8px);
            }

            .modal.full {
                width: min(1320px, min(95vw, 100% - 2rem));
                max-width: min(1320px, min(95vw, 100% - 2rem));
                height: min(88vh, min(980px, 100dvh - 2rem));
                max-height: min(94vh, 100dvh - 2rem);
            }

            .meetings-modal-body {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                padding: var(--space-3);
                box-sizing: border-box;
            }

            .meetings-controls {
                display: grid;
                grid-template-columns: minmax(220px, 320px) minmax(160px, 220px) minmax(160px, 220px) auto;
                gap: var(--space-2);
                padding-bottom: var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                flex-shrink: 0;
            }

            .meetings-select,
            .meetings-date {
                width: 100%;
                min-height: 40px;
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
                padding: 0 var(--space-3);
                outline: none;
                box-sizing: border-box;
            }

            .meetings-select:focus,
            .meetings-date:focus {
                border-color: var(--accent);
            }

            .filter-btn {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
                padding: 8px 12px;
                cursor: pointer;
                transition: background var(--duration-fast), border-color var(--duration-fast);
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            .filter-btn:hover {
                background: var(--glass-solid-medium);
                border-color: var(--accent);
            }

            .meetings-body {
                display: grid;
                grid-template-columns: minmax(340px, 460px) minmax(0, 1fr);
                gap: var(--space-3);
                padding-top: var(--space-3);
                min-height: 0;
                flex: 1;
            }

            .meetings-list {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-2);
                overflow: auto;
                min-height: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .meeting-card {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
                padding: var(--space-3);
                cursor: pointer;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                text-align: left;
                color: var(--text-primary);
                transition: border-color var(--duration-fast), background var(--duration-fast);
                font: inherit;
                box-sizing: border-box;
            }

            .meeting-card:hover {
                border-color: var(--glass-border-medium);
                background: var(--glass-solid-medium);
            }

            .meeting-card.active {
                border-color: var(--accent);
                background: var(--accent-subtle);
            }

            .meeting-card-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }

            .meeting-channel {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }

            .meeting-channel-badge {
                width: 24px;
                height: 24px;
                border-radius: 50%;
                color: #fff;
                font-size: 11px;
                font-weight: var(--font-semibold);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }

            .meeting-channel-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .meeting-meta {
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }

            .meeting-status {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 72px;
                padding: 2px 10px;
                border-radius: var(--radius-full);
                border: 1px solid var(--glass-border-subtle);
                font-size: 11px;
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }

            .meeting-status.done {
                color: rgb(22, 163, 74);
                border-color: rgba(22, 163, 74, 0.35);
                background: rgba(22, 163, 74, 0.12);
            }

            .meeting-status.pending {
                color: rgb(217, 119, 6);
                border-color: rgba(217, 119, 6, 0.35);
                background: rgba(217, 119, 6, 0.12);
            }

            .meeting-status.failed {
                color: rgb(220, 38, 38);
                border-color: rgba(220, 38, 38, 0.35);
                background: rgba(220, 38, 38, 0.12);
            }

            .meetings-detail {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-3);
                overflow: auto;
                min-height: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }

            .meetings-empty {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                padding: var(--space-2);
            }

            .detail-section-title {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .detail-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: var(--space-2) var(--space-3);
            }

            .detail-label {
                font-size: 11px;
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }

            .detail-value {
                font-size: var(--text-sm);
                color: var(--text-primary);
            }

            .detail-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }

            @media (max-width: 767px) {
                .modal.full {
                    width: min(95vw, 100% - 1rem);
                    max-width: min(95vw, 100% - 1rem);
                    height: min(92vh, 100dvh - 1rem);
                    max-height: min(92vh, 100dvh - 1rem);
                }

                .meetings-controls {
                    grid-template-columns: 1fr;
                }

                .meetings-body {
                    grid-template-columns: 1fr;
                }

                .detail-grid {
                    grid-template-columns: 1fr;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'full';
        this._meetingsChannelFilter = 'all';
        this._meetingsDateFrom = '';
        this._meetingsDateTo = '';
        this._meetingDetailsById = {};
        this._meetingsDetailsLoadingId = null;
        /** @type {(() => void) | null} */
        this._storeUnsub = null;
        /** @type {(() => void) | null} */
        this._i18nUnsub = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this.open = SyncStore.state.ui.meetingsPanelOpen === true;
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        this._storeUnsub = SyncStore.subscribe(() => {
            const nextOpen = SyncStore.state.ui.meetingsPanelOpen === true;
            if (this.open !== nextOpen) {
                this.open = nextOpen;
            }
            this.requestUpdate();
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._i18nUnsub?.();
        this._i18nUnsub = null;
        this._storeUnsub?.();
        this._storeUnsub = null;
    }

    close() {
        SyncStore.closeMeetingsPanel();
        super.close();
    }

    _localeTag() {
        const loc = this.i18n.getCurrentLocale();
        return loc === 'en' ? 'en-US' : 'ru-RU';
    }

    _meetingDateMs(meeting) {
        if (!meeting || typeof meeting !== 'object') {
            return null;
        }
        const iso = typeof meeting.created_at === 'string' && meeting.created_at !== ''
            ? meeting.created_at
            : meeting.updated_at;
        if (typeof iso !== 'string' || iso === '') {
            return null;
        }
        const parsed = Date.parse(iso);
        if (Number.isNaN(parsed)) {
            return null;
        }
        return parsed;
    }

    _filteredMeetings() {
        const meetings = SyncStore.state.meetings.list;
        const channelFilter = this._meetingsChannelFilter;
        const fromFilter = this._meetingsDateFrom;
        const toFilter = this._meetingsDateTo;
        const fromMs = fromFilter !== '' ? Date.parse(`${fromFilter}T00:00:00`) : null;
        const toMs = toFilter !== '' ? Date.parse(`${toFilter}T23:59:59.999`) : null;
        return meetings.filter((meeting) => {
            if (channelFilter !== 'all' && meeting.channel_id !== channelFilter) {
                return false;
            }
            const meetingDateMs = this._meetingDateMs(meeting);
            if (fromMs !== null && meetingDateMs !== null && meetingDateMs < fromMs) {
                return false;
            }
            if (toMs !== null && meetingDateMs !== null && meetingDateMs > toMs) {
                return false;
            }
            return true;
        });
    }

    _meetingChannelOptions(meetings) {
        const channelIds = new Set();
        for (const meeting of meetings) {
            if (typeof meeting.channel_id === 'string' && meeting.channel_id !== '') {
                channelIds.add(meeting.channel_id);
            }
        }
        const options = [];
        for (const channelId of channelIds) {
            const channel = SyncStore.state.channels.list.find((item) => item.id === channelId);
            const title = channel ? SyncStore.channelDisplayTitle(channel) : channelId;
            options.push({ channelId, title });
        }
        const loc = this.i18n.getCurrentLocale();
        options.sort((left, right) => left.title.localeCompare(right.title, loc));
        return options;
    }

    _formatMeetingDate(isoValue) {
        if (typeof isoValue !== 'string' || isoValue === '') {
            return this.i18n.t('empty_dash');
        }
        const date = new Date(isoValue);
        if (Number.isNaN(date.getTime())) {
            return this.i18n.t('empty_dash');
        }
        return new Intl.DateTimeFormat(this._localeTag(), {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        }).format(date);
    }

    _channelName(channelId) {
        if (typeof channelId !== 'string' || channelId === '') {
            return this.i18n.t('empty_dash');
        }
        const channel = SyncStore.state.channels.list.find((item) => item.id === channelId);
        if (!channel) {
            return channelId;
        }
        return SyncStore.channelDisplayTitle(channel);
    }

    _channelInitials(channelId) {
        const label = this._channelName(channelId).trim();
        if (label === '') {
            return '?';
        }
        return label.slice(0, 1).toUpperCase();
    }

    _statusLabel(exportStatus) {
        if (exportStatus === 'done') {
            return this.i18n.t('export_status.done', {});
        }
        if (exportStatus === 'pending') {
            return this.i18n.t('export_status.pending', {});
        }
        if (exportStatus === 'failed') {
            return this.i18n.t('export_status.failed', {});
        }
        return this.i18n.t('empty_dash');
    }

    _selectedMeeting() {
        const selected = SyncStore.state.meetings.selected;
        if (!selected || typeof selected.meeting_id !== 'string' || selected.meeting_id === '') {
            return null;
        }
        const details = this._meetingDetailsById[selected.meeting_id];
        if (details) {
            return details;
        }
        return selected;
    }

    _meetingParticipants(meetingDetails) {
        const segments = Array.isArray(meetingDetails?.segments) ? meetingDetails.segments : [];
        const participants = new Set();
        for (const segment of segments) {
            if (typeof segment.speaker_user_id === 'string' && segment.speaker_user_id !== '') {
                participants.add(segment.speaker_user_id);
                continue;
            }
            if (typeof segment.speaker_guest_name === 'string' && segment.speaker_guest_name !== '') {
                participants.add(segment.speaker_guest_name);
                continue;
            }
            if (typeof segment.speaker_identity === 'string' && segment.speaker_identity !== '') {
                participants.add(segment.speaker_identity);
            }
        }
        return [...participants];
    }

    _durationText(meetingDetails) {
        const startedAt = meetingDetails?.recording?.started_at;
        const endedAt = meetingDetails?.recording?.ended_at;
        if (typeof startedAt !== 'string' || typeof endedAt !== 'string') {
            return this.i18n.t('empty_dash');
        }
        const startedMs = Date.parse(startedAt);
        const endedMs = Date.parse(endedAt);
        if (Number.isNaN(startedMs) || Number.isNaN(endedMs) || endedMs <= startedMs) {
            return this.i18n.t('empty_dash');
        }
        const diffSeconds = Math.round((endedMs - startedMs) / 1000);
        const hours = Math.floor(diffSeconds / 3600);
        const minutes = Math.floor((diffSeconds % 3600) / 60);
        const seconds = diffSeconds % 60;
        if (hours > 0) {
            return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        }
        return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }

    async _openMeetingDetails(meetingId) {
        if (typeof meetingId !== 'string' || meetingId === '') {
            throw new Error(this.i18n.t('sync_app.err_meeting_id_required'));
        }
        const syncApi = this.services.get('syncApi');
        this._meetingsDetailsLoadingId = meetingId;
        const details = await syncApi.getMeeting(meetingId);
        if (!details || typeof details !== 'object' || !details.meeting) {
            this._meetingsDetailsLoadingId = null;
            throw new Error(this.i18n.t('sync_app.err_meeting_details_invalid'));
        }
        const selected = {
            ...details.meeting,
            recording: details.recording ?? null,
            segments: Array.isArray(details.segments) ? details.segments : [],
        };
        this._meetingDetailsById = {
            ...this._meetingDetailsById,
            [meetingId]: selected,
        };
        this._meetingsDetailsLoadingId = null;
        SyncStore.setMeetingSelected(selected);
    }

    async _exportSelectedMeeting() {
        const selected = this._selectedMeeting();
        if (!selected || typeof selected.meeting_id !== 'string' || selected.meeting_id === '') {
            throw new Error(this.i18n.t('sync_app.err_meeting_id_operation'));
        }
        const syncApi = this.services.get('syncApi');
        await syncApi.exportMeetingToCrm(selected.meeting_id, null);
        await SyncStore.loadMeetings(syncApi, { limit: 200 });
        await this._openMeetingDetails(selected.meeting_id);
    }

    async _retrySelectedMeeting() {
        const selected = this._selectedMeeting();
        if (!selected || typeof selected.meeting_id !== 'string' || selected.meeting_id === '') {
            throw new Error(this.i18n.t('sync_app.err_meeting_id_operation'));
        }
        const syncApi = this.services.get('syncApi');
        await syncApi.retryMeetingProcessing(selected.meeting_id);
        await SyncStore.loadMeetings(syncApi, { limit: 200 });
        await this._openMeetingDetails(selected.meeting_id);
    }

    renderHeader() {
        return this.i18n.t('meetings_title');
    }

    renderBody() {
        if (!this.open) {
            return html``;
        }
        const meetingsState = SyncStore.state.meetings;
        const filteredMeetings = this._filteredMeetings();
        const meetingChannelOptions = this._meetingChannelOptions(meetingsState.list);
        const selectedMeeting = this._selectedMeeting();
        const selectedParticipants = selectedMeeting ? this._meetingParticipants(selectedMeeting) : [];
        const ts = (k, p) => this.i18n.t(k, p ?? {});

        return html`
            <div class="meetings-modal-body">
                <div class="meetings-controls">
                    <select
                        class="meetings-select"
                        .value=${this._meetingsChannelFilter}
                        @change=${(e) => {
                            const el = e.target;
                            if (el instanceof HTMLSelectElement) {
                                this._meetingsChannelFilter = el.value;
                            }
                        }}
                    >
                        <option value="all">${ts('all_channels')}</option>
                        ${meetingChannelOptions.map((item) => html`
                            <option value=${item.channelId}>${item.title}</option>
                        `)}
                    </select>
                    <input
                        class="meetings-date"
                        type="date"
                        .value=${this._meetingsDateFrom}
                        @change=${(e) => {
                            const el = e.target;
                            if (el instanceof HTMLInputElement) {
                                this._meetingsDateFrom = el.value;
                            }
                        }}
                    />
                    <input
                        class="meetings-date"
                        type="date"
                        .value=${this._meetingsDateTo}
                        @change=${(e) => {
                            const el = e.target;
                            if (el instanceof HTMLInputElement) {
                                this._meetingsDateTo = el.value;
                            }
                        }}
                    />
                    <button
                        type="button"
                        class="filter-btn"
                        @click=${() => {
                            this._meetingsChannelFilter = 'all';
                            this._meetingsDateFrom = '';
                            this._meetingsDateTo = '';
                        }}
                    >
                        ${ts('reset_filters')}
                    </button>
                </div>
                <div class="meetings-body">
                    <div class="meetings-list">
                        ${meetingsState.loading ? html`<div class="meetings-empty">${ts('loading_meetings')}</div>` : ''}
                        ${!meetingsState.loading && filteredMeetings.length === 0
                            ? html`<div class="meetings-empty">${ts('empty_filtered')}</div>`
                            : ''}
                        ${filteredMeetings.map((meeting) => {
                            const isActive = selectedMeeting?.meeting_id === meeting.meeting_id;
                            const loading = this._meetingsDetailsLoadingId === meeting.meeting_id;
                            const statusClass = `meeting-status ${meeting.export_status}`;
                            const badgeColor = `background:hsl(${hueFromString(meeting.channel_id)} 48% 42%)`;
                            const details = this._meetingDetailsById[meeting.meeting_id];
                            const duration = details ? this._durationText(details) : ts('empty_dash');
                            return html`
                                <button
                                    type="button"
                                    class="meeting-card ${isActive ? 'active' : ''}"
                                    @click=${async () => {
                                        try {
                                            await this._openMeetingDetails(meeting.meeting_id);
                                        } catch (err) {
                                            const text = err instanceof Error ? err.message : String(err);
                                            this.error(text);
                                        }
                                    }}
                                >
                                    <div class="meeting-card-row">
                                        <span class="meeting-channel">
                                            <span class="meeting-channel-badge" style=${badgeColor}>${this._channelInitials(meeting.channel_id)}</span>
                                            <span class="meeting-channel-name">${this._channelName(meeting.channel_id)}</span>
                                        </span>
                                        <span class=${statusClass}>${this._statusLabel(meeting.export_status)}</span>
                                    </div>
                                    <div class="meeting-meta">${ts('meta_date')} ${this._formatMeetingDate(meeting.created_at)}</div>
                                    <div class="meeting-meta">${ts('meta_duration')} ${duration}</div>
                                    <div class="meeting-meta">${ts('meta_meeting_id')} ${meeting.meeting_id.slice(0, 12)}...</div>
                                    ${loading ? html`<div class="meeting-meta">${ts('loading_details')}</div>` : ''}
                                </button>
                            `;
                        })}
                    </div>
                    <div class="meetings-detail">
                        ${selectedMeeting ? html`
                            <div class="detail-section-title">${ts('meeting_details')}</div>
                            <div class="detail-grid">
                                <div>
                                    <div class="detail-label">${ts('label_channel')}</div>
                                    <div class="detail-value">${this._channelName(selectedMeeting.channel_id)}</div>
                                </div>
                                <div>
                                    <div class="detail-label">${ts('label_date')}</div>
                                    <div class="detail-value">${this._formatMeetingDate(selectedMeeting.created_at)}</div>
                                </div>
                                <div>
                                    <div class="detail-label">${ts('label_duration')}</div>
                                    <div class="detail-value">${this._durationText(selectedMeeting)}</div>
                                </div>
                                <div>
                                    <div class="detail-label">${ts('label_status')}</div>
                                    <div class="detail-value">${this._statusLabel(selectedMeeting.export_status)}</div>
                                </div>
                                <div>
                                    <div class="detail-label">${ts('label_participants')}</div>
                                    <div class="detail-value">${selectedParticipants.length > 0 ? selectedParticipants.join(', ') : ts('empty_dash')}</div>
                                </div>
                                <div>
                                    <div class="detail-label">${ts('label_meeting_id')}</div>
                                    <div class="detail-value">${selectedMeeting.meeting_id}</div>
                                </div>
                            </div>
                            <div class="detail-actions">
                                ${selectedMeeting.recording?.raw_file_download_url ? html`
                                    <a
                                        class="filter-btn"
                                        href=${selectedMeeting.recording.raw_file_download_url}
                                        download
                                        target="_blank"
                                        rel="noopener noreferrer"
                                    >${ts('download_recording')}</a>
                                ` : ''}
                                ${selectedMeeting.transcript_text_download_url ? html`
                                    <a
                                        class="filter-btn"
                                        href=${selectedMeeting.transcript_text_download_url}
                                        download
                                        target="_blank"
                                        rel="noopener noreferrer"
                                    >${ts('download_transcript')}</a>
                                ` : ''}
                                <button
                                    type="button"
                                    class="filter-btn"
                                    @click=${async () => {
                                        try {
                                            await this._exportSelectedMeeting();
                                        } catch (err) {
                                            const text = err instanceof Error ? err.message : String(err);
                                            this.error(text);
                                        }
                                    }}
                                >
                                    ${ts('export_crm')}
                                </button>
                                <button
                                    type="button"
                                    class="filter-btn"
                                    @click=${async () => {
                                        try {
                                            await this._retrySelectedMeeting();
                                        } catch (err) {
                                            const text = err instanceof Error ? err.message : String(err);
                                            this.error(text);
                                        }
                                    }}
                                >
                                    ${ts('retry_processing')}
                                </button>
                            </div>
                        ` : html`
                            <div class="meetings-empty">${ts('select_card_hint')}</div>
                        `}
                    </div>
                </div>
            </div>
        `;
    }

    renderFooter() {
        return html``;
    }
}

customElements.define('meetings-modal', MeetingsModal);
