import { html, css } from 'lit';
import { PlatformModal } from './glass-modal.js';
import { formStyles } from '../styles/shared/form.styles.js';
import { buttonStyles } from '../styles/shared/button.styles.js';
import './platform-icon.js';
import { resolveFileIconKey } from '../../services/icon.service.js';
import './platform-date-picker.js';
import './platform-switch.js';

const BASE_TIMEZONE_OPTIONS = [
    'UTC',
    'Europe/Moscow',
    'Europe/London',
    'Europe/Berlin',
    'Europe/Paris',
    'Europe/Istanbul',
    'America/New_York',
    'America/Chicago',
    'America/Denver',
    'America/Los_Angeles',
    'America/Sao_Paulo',
    'Asia/Dubai',
    'Asia/Almaty',
    'Asia/Kolkata',
    'Asia/Bangkok',
    'Asia/Singapore',
    'Asia/Shanghai',
    'Asia/Tokyo',
    'Australia/Sydney',
];

import { COLOR_PALETTE } from '@platform/lib/utils/color-palette.js';

const EVENT_COLOR_KEY = 'event_color';
const DEFAULT_EVENT_COLOR = 'default';
const EVENT_COLOR_OPTIONS = COLOR_PALETTE;

function pad2(value) {
    return String(value).padStart(2, '0');
}

function toDateInputValue(date) {
    return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

/**
 * Строка YYYY-MM-DD из состояния календаря — это календарный день в локальной зоне,
 * а new Date('YYYY-MM-DD') в движке — полночь UTC, из‑за чего сетка дня и фильтр событий
 * расходятся с подписью периода (особенно при отрицательном смещении от UTC).
 */
function parseDateInputLocal(isoDate) {
    if (typeof isoDate !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(isoDate)) {
        const parsed = new Date(isoDate);
        if (Number.isNaN(parsed.getTime())) {
            throw new Error(`Invalid calendar date: ${isoDate}`);
        }
        return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate(), 0, 0, 0, 0);
    }
    const y = Number(isoDate.slice(0, 4));
    const m = Number(isoDate.slice(5, 7)) - 1;
    const d = Number(isoDate.slice(8, 10));
    return new Date(y, m, d, 0, 0, 0, 0);
}

function toDateTimeInputValue(date) {
    return `${toDateInputValue(date)}T${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function addDays(date, amount) {
    const copy = new Date(date.getTime());
    copy.setDate(copy.getDate() + amount);
    return copy;
}

function startOfWeek(date) {
    const copy = new Date(date.getTime());
    const day = copy.getDay();
    const shift = day === 0 ? 6 : day - 1;
    copy.setDate(copy.getDate() - shift);
    copy.setHours(0, 0, 0, 0);
    return copy;
}

function endOfWeek(date) {
    const start = startOfWeek(date);
    return addDays(start, 7);
}

function startOfMonth(date) {
    const copy = new Date(date.getFullYear(), date.getMonth(), 1, 0, 0, 0, 0);
    return copy;
}

function endOfMonth(date) {
    return new Date(date.getFullYear(), date.getMonth() + 1, 1, 0, 0, 0, 0);
}

function isSameDay(left, right) {
    return left.getFullYear() === right.getFullYear()
        && left.getMonth() === right.getMonth()
        && left.getDate() === right.getDate();
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function normalizeEmail(value) {
    return String(value || '').trim().toLowerCase();
}

function toAttendeeTag(entry) {
    if (!entry || typeof entry !== 'object') {
        throw new Error('Attendee entry must be object');
    }
    const email = normalizeEmail(entry.email);
    if (!email) {
        throw new Error('Attendee email is required');
    }
    if (!EMAIL_PATTERN.test(email)) {
        throw new Error(`Invalid attendee email: ${email}`);
    }
    const displayName = typeof entry.display_name === 'string' && entry.display_name.trim()
        ? entry.display_name.trim()
        : email;
    const attendeeId = typeof entry.attendee_id === 'string' && entry.attendee_id.trim()
        ? entry.attendee_id.trim()
        : email;
    return {
        attendee_id: attendeeId,
        email,
        display_name: displayName,
        response_status: 'needsAction',
    };
}

function recurrenceToRule(value) {
    if (value === 'none') {
        return null;
    }
    if (value === 'daily') {
        return 'FREQ=DAILY';
    }
    if (value === 'weekly') {
        return 'FREQ=WEEKLY';
    }
    if (value === 'monthly') {
        return 'FREQ=MONTHLY';
    }
    throw new Error(`Unsupported recurrence value: ${value}`);
}

function parseEventAttachments(metadata) {
    if (!metadata) {
        return [];
    }
    const rawAttachments = metadata.attachments;
    if (!rawAttachments) {
        return [];
    }
    if (typeof rawAttachments !== 'string') {
        throw new Error('metadata.attachments must be a string');
    }
    const parsed = JSON.parse(rawAttachments);
    if (!Array.isArray(parsed)) {
        throw new Error('metadata.attachments must be a JSON array');
    }
    return parsed.map((item) => {
        if (!item || typeof item !== 'object') {
            throw new Error('Attachment item must be an object');
        }
        if (typeof item.file_id !== 'string' || item.file_id === '') {
            throw new Error('Attachment file_id is required');
        }
        if (typeof item.name !== 'string' || item.name === '') {
            throw new Error('Attachment name is required');
        }
        if (typeof item.url !== 'string' || item.url === '') {
            throw new Error('Attachment url is required');
        }
        return {
            file_id: item.file_id,
            name: item.name,
            url: item.url,
            content_type: typeof item.content_type === 'string' ? item.content_type : '',
            file_size: Number.isFinite(item.file_size) ? item.file_size : 0,
        };
    });
}

function buildEventMetadata(baseMetadata, attachments) {
    const nextMetadata = {};
    for (const [key, value] of Object.entries(baseMetadata || {})) {
        if (typeof value !== 'string') {
            throw new Error(`Event metadata value for key '${key}' must be string`);
        }
        nextMetadata[key] = value;
    }
    if (attachments.length === 0) {
        delete nextMetadata.attachments;
        return nextMetadata;
    }
    nextMetadata.attachments = JSON.stringify(attachments);
    return nextMetadata;
}

function isKnownEventColor(colorKey) {
    return EVENT_COLOR_OPTIONS.some((color) => color.key === colorKey);
}

function normalizeEventColor(colorKey) {
    if (!colorKey) {
        return DEFAULT_EVENT_COLOR;
    }
    if (isKnownEventColor(colorKey)) {
        return colorKey;
    }
    return DEFAULT_EVENT_COLOR;
}

function eventMetadataHasSyncMeeting(metadata) {
    if (!metadata || typeof metadata !== 'object') {
        return false;
    }
    return metadata.sync_meeting === '1' || Boolean(metadata.sync_link_token);
}

const SYNC_LOGO_SRC = '/static/core/assets/service_logos/sync_logo.svg';

export class PlatformCalendarModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        _view: { state: true },
        _anchorDate: { state: true },
        _events: { state: true },
        _integrations: { state: true },
        _loading: { state: true },
        _saving: { state: true },
        _syncing: { state: true },
        _selectedEventId: { state: true },
        _activeProvider: { state: true },
        _showAdvanced: { state: true },
        _eventDialogOpen: { state: true },
        _showDescriptionField: { state: true },
        _uploadingAttachments: { state: true },
        _eventAttachments: { state: true },
        _eventMetadata: { state: true },
        _selectedEventSource: { state: true },
        _selectedEventKind: { state: true },
        _selectedEventNamespace: { state: true },
        _timezoneOptions: { state: true },
        _teamMembers: { state: true },
        _attendeeDraft: { state: true },
        _attendeeDropdownOpen: { state: true },
        _eventForm: { state: true },
        _integrationForm: { state: true },
        _isCompactLayout: { state: true },
        _dateSheetOpen: { state: true },
        _dateSheetMonthRef: { state: true },
        _eventDeepLink: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        formStyles,
        buttonStyles,
        css`
            :host {
                --calendar-sidebar-width: 420px;
                --calendar-grid-columns: 7;
            }

            .calendar-shell {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-height: 0;
                height: 100%;
            }

            .calendar-sidebar {
                border-right: 1px solid var(--glass-border-subtle);
                padding-right: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                overflow: auto;
                min-height: 0;
                min-width: 0;
            }

            .calendar-main {
                min-height: 0;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }

            .toolbar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-2) 0;
                border-bottom: 1px solid var(--glass-border-subtle);
            }

            .toolbar-left,
            .toolbar-right {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }

            .title {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .btn-icon {
                width: 34px;
                height: 34px;
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            .btn-icon:hover {
                border-color: var(--accent);
                color: var(--text-primary);
            }

            .view-segment {
                display: inline-flex;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                overflow: hidden;
            }

            .view-segment button {
                border: none;
                background: transparent;
                color: var(--text-secondary);
                padding: 6px 10px;
                font-size: var(--text-xs);
                cursor: pointer;
            }

            .view-segment button.active {
                background: var(--accent-subtle);
                color: var(--accent);
            }

            .calendar-panel {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-subtle);
                min-height: 0;
                overflow: auto;
                padding: var(--space-2);
            }

            .calendar-panel--day {
                border: none;
                background: transparent;
                padding: 0;
                overflow: visible;
            }

            .btn-calendar-create {
                width: 40px;
                height: 40px;
                min-width: 40px;
                min-height: 40px;
                padding: 0;
                border-radius: 50%;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-size: 22px;
                line-height: 1;
                font-weight: var(--font-semibold);
            }

            .btn.btn-primary.btn-calendar-create {
                padding: 0;
            }

            .calendar-fab {
                display: none;
            }

            .toolbar--compact {
                flex-wrap: wrap;
                gap: var(--space-2);
            }

            .toolbar--compact .toolbar-left {
                flex: 1 1 100%;
                justify-content: center;
                align-items: center;
                gap: var(--space-2);
                padding-left: max(var(--space-2), calc(env(safe-area-inset-left, 0px) + 10px));
                padding-right: max(var(--space-2), env(safe-area-inset-right, 0px));
                box-sizing: border-box;
            }

            .toolbar--compact .toolbar-left .btn-icon {
                touch-action: manipulation;
                flex-shrink: 0;
            }

            .toolbar--compact .toolbar-right {
                flex: 1 1 100%;
                justify-content: space-between;
                align-items: center;
            }

            .toolbar--compact .view-segment {
                display: none;
            }

            .toolbar--compact .title {
                display: none;
            }

            .period-date-btn {
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                border-radius: var(--radius-full);
                padding: 8px 14px;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
                cursor: pointer;
                max-width: min(100%, 280px);
            }

            .period-date-btn:hover {
                border-color: var(--accent);
            }

            .date-sheet-overlay {
                position: fixed;
                inset: 0;
                z-index: calc(var(--platform-modal-layer-z, var(--z-modal, 1000)) + 4);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-4);
                background: rgba(0, 0, 0, 0.2);
                backdrop-filter: blur(4px);
                -webkit-backdrop-filter: blur(4px);
            }

            .date-sheet-card {
                width: min(340px, 100%);
                max-height: min(86dvh, 520px);
                overflow: auto;
                border-radius: var(--radius-xl);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-strong);
                box-shadow: var(--glass-shadow-medium);
                padding: var(--space-3);
                display: grid;
                gap: var(--space-3);
            }

            .date-sheet-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }

            .date-sheet-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .date-sheet-nav {
                display: flex;
                gap: var(--space-1);
            }

            .date-sheet-grid {
                display: grid;
                grid-template-columns: repeat(7, minmax(0, 1fr));
                gap: 4px;
            }

            .date-sheet-weekday {
                text-align: center;
                font-size: 10px;
                color: var(--text-tertiary);
                font-weight: var(--font-semibold);
            }

            .date-sheet-cell {
                aspect-ratio: 1;
                max-height: 40px;
                border: 1px solid transparent;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                cursor: pointer;
                padding: 0;
            }

            .date-sheet-cell.outside {
                color: var(--text-tertiary);
                opacity: 0.55;
            }

            .date-sheet-cell.today {
                border-color: color-mix(in srgb, #ef6f98 45%, var(--glass-border-subtle));
            }

            .date-sheet-cell.selected {
                background: var(--accent-subtle);
                color: var(--accent);
                border-color: var(--accent);
            }

            .day-timeline {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-width: 0;
            }

            .day-all-day-row {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
                padding-bottom: var(--space-2);
                border-bottom: 1px solid var(--glass-border-subtle);
            }

            .day-timeline-scroll {
                overflow-x: auto;
                overflow-y: auto;
                max-height: min(62dvh, 560px);
                min-height: 280px;
            }

            .day-timeline-body {
                display: grid;
                grid-template-columns: 44px minmax(0, 1fr);
                gap: 0;
                align-items: start;
                --day-hour-height: 52px;
            }

            .day-time-col {
                display: flex;
                flex-direction: column;
                width: 44px;
                flex-shrink: 0;
            }

            .day-time-label {
                height: var(--day-hour-height);
                font-size: 11px;
                color: var(--text-tertiary);
                padding-right: 6px;
                text-align: right;
                box-sizing: border-box;
            }

            .day-tracks {
                position: relative;
                min-width: 0;
            }

            .day-tracks-lines {
                display: flex;
                flex-direction: column;
            }

            .day-hour-slot {
                height: var(--day-hour-height);
                border-bottom: 1px solid var(--glass-border-subtle);
                box-sizing: border-box;
            }

            .day-events-layer {
                position: absolute;
                left: 0;
                right: 0;
                top: 0;
                height: calc(24 * var(--day-hour-height));
                pointer-events: none;
            }

            .day-event-block {
                pointer-events: auto;
                position: absolute;
                left: 4px;
                right: 4px;
                min-height: 24px;
                border: none;
                border-radius: var(--radius-md);
                padding: 6px 8px;
                text-align: left;
                cursor: pointer;
                font-size: var(--text-xs);
                line-height: 1.25;
                overflow: hidden;
                display: flex;
                flex-direction: column;
                gap: 2px;
                box-sizing: border-box;
            }

            .day-event-block.event-chip {
                display: flex;
            }

            .day-now-line {
                position: absolute;
                left: 0;
                right: 0;
                height: 2px;
                background: #e53935;
                z-index: 2;
                pointer-events: none;
            }

            .day-now-line::before {
                content: '';
                position: absolute;
                left: -6px;
                top: 50%;
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: #e53935;
                transform: translateY(-50%);
            }

            .month-grid {
                display: grid;
                grid-template-columns: repeat(7, minmax(0, 1fr));
                gap: var(--space-1);
            }

            .weekday {
                text-align: center;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                padding: var(--space-1) 0;
            }

            .weekday.weekend {
                color: var(--accent);
                background: color-mix(in srgb, var(--accent) 10%, transparent);
                border-radius: var(--radius-sm);
            }

            .month-cell {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                min-height: 114px;
                padding: var(--space-1) 6px;
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                background: var(--glass-solid-medium);
            }

            .month-cell.outside {
                opacity: 0.55;
            }

            .month-cell.weekend {
                background: color-mix(in srgb, var(--accent) 10%, var(--glass-solid-medium));
                border-color: color-mix(in srgb, var(--accent) 30%, var(--glass-border-subtle));
            }

            .month-cell.today {
                border-color: color-mix(in srgb, #ef6f98 45%, var(--glass-border-subtle));
                background: color-mix(in srgb, #ef6f98 8%, var(--glass-solid-medium));
            }

            .month-cell .date-label {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                font-weight: var(--font-semibold);
            }

            .month-cell.today .date-label {
                color: #a7365e;
                background: color-mix(in srgb, #ef6f98 18%, transparent);
                border-radius: 999px;
                width: 22px;
                height: 22px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            .month-cell-events {
                flex: 1;
                min-height: 0;
                display: grid;
                gap: 6px;
                grid-auto-rows: minmax(0, 1fr);
            }

            .event-chip {
                font-size: var(--text-xs);
                line-height: 1.3;
                background: color-mix(in srgb, #a2affb 24%, var(--glass-solid-medium));
                border: none;
                color: #4f5eb6;
                border-radius: var(--radius-sm);
                padding: 8px 10px;
                cursor: pointer;
                text-align: left;
                display: grid;
                gap: 6px;
                min-width: 0;
                min-height: 0;
                align-content: start;
            }

            .event-chip.active {
                box-shadow: inset 0 0 0 2px color-mix(in srgb, currentColor 45%, transparent);
            }

            .event-chip[data-color='default'] {
                background: color-mix(in srgb, #a2affb 24%, var(--glass-solid-medium));
                color: #4f5eb6;
            }

            .event-chip[data-color='mint'] {
                background: color-mix(in srgb, #34c38f 18%, var(--glass-solid-medium));
                color: #0b7a59;
            }

            .event-chip[data-color='sky'] {
                background: color-mix(in srgb, #4ea8ff 18%, var(--glass-solid-medium));
                color: #1866b8;
            }

            .event-chip[data-color='violet'] {
                background: color-mix(in srgb, #8f7bff 18%, var(--glass-solid-medium));
                color: #5c49ca;
            }

            .event-chip[data-color='amber'] {
                background: color-mix(in srgb, #f5b14c 20%, var(--glass-solid-medium));
                color: #9f6610;
            }

            .event-chip[data-color='rose'] {
                background: color-mix(in srgb, #ef6f98 18%, var(--glass-solid-medium));
                color: #a7365e;
            }

            .event-chip[data-color='gray'] {
                background: color-mix(in srgb, #8f96a3 18%, var(--glass-solid-medium));
                color: #4f5868;
            }

            .event-chip-top {
                display: flex;
                align-items: center;
                justify-content: flex-start;
                flex-wrap: wrap;
                gap: 4px;
                min-width: 0;
            }

            .event-chip-title {
                overflow: hidden;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                color: inherit;
            }

            .event-chip-time {
                font-weight: var(--font-semibold);
                margin-right: 4px;
            }

            .event-badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-height: 16px;
                padding: 0 6px;
                border-radius: 999px;
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                font-size: 10px;
                font-weight: var(--font-medium);
                line-height: 1;
                white-space: nowrap;
            }

            .event-badge[data-source='platform'] {
                border-color: color-mix(in srgb, var(--accent) 55%, var(--glass-border-subtle));
                color: var(--accent);
                background: color-mix(in srgb, var(--accent) 16%, var(--glass-solid-medium));
            }

            .event-badge[data-source='crm'] {
                border-color: color-mix(in srgb, #8f5cff 55%, var(--glass-border-subtle));
                color: #7851ff;
                background: color-mix(in srgb, #8f5cff 12%, var(--glass-solid-medium));
            }

            .event-badge[data-source='sync'] {
                border-color: color-mix(in srgb, #34a3ff 55%, var(--glass-border-subtle));
                color: #2a8de0;
                background: color-mix(in srgb, #34a3ff 12%, var(--glass-solid-medium));
            }

            .event-badge[data-source='google'] {
                border-color: color-mix(in srgb, #1a73e8 55%, var(--glass-border-subtle));
                color: #1a73e8;
                background: color-mix(in srgb, #1a73e8 12%, var(--glass-solid-medium));
            }

            .event-badge[data-source='yandex'] {
                border-color: color-mix(in srgb, #fc3f1d 55%, var(--glass-border-subtle));
                color: #d9381b;
                background: color-mix(in srgb, #fc3f1d 12%, var(--glass-solid-medium));
            }

            .event-badge-sync {
                gap: 4px;
            }

            .event-sync-logo-inline {
                width: 14px;
                height: 14px;
                flex-shrink: 0;
            }

            .event-compose-sync-head {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
            }

            .event-compose-sync-row {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                width: 100%;
            }

            .event-compose-sync-row .event-compose-switch {
                flex: 0 1 auto;
                min-width: 0;
            }

            .event-compose-sync-hint-row {
                flex-direction: column;
                align-items: flex-start;
            }

            .event-compose-meeting-sync-hint {
                margin: 0;
                font-size: var(--text-sm);
                color: var(--text-secondary, var(--glass-text-muted));
                line-height: 1.45;
            }

            .event-compose-join-link {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                color: var(--accent, #99a6f9);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                text-decoration: none;
                white-space: nowrap;
                flex: 0 0 auto;
            }

            .event-compose-join-link:hover {
                text-decoration: underline;
            }

            .event-compose-join-link platform-icon {
                flex-shrink: 0;
                color: var(--accent, #99a6f9);
            }

            .list-view {
                display: grid;
                gap: var(--space-2);
            }

            .list-item {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                padding: var(--space-2) var(--space-3);
                display: flex;
                justify-content: space-between;
                gap: var(--space-2);
                cursor: pointer;
            }

            .list-item.active {
                border-color: var(--accent);
            }

            .list-title {
                font-size: var(--text-sm);
                color: var(--text-primary);
                font-weight: var(--font-medium);
            }

            .list-meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .list-badges {
                display: flex;
                align-items: center;
                gap: 6px;
                flex-wrap: wrap;
                margin-top: 4px;
            }

            .section {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-subtle);
                padding: var(--space-3);
                display: grid;
                gap: var(--space-3);
                min-width: 0;
            }

            .section-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .row {
                display: grid;
                gap: var(--space-2);
                min-width: 0;
            }

            .row.two {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }

            .row.two > * {
                min-width: 0;
            }

            .form-input,
            .form-select,
            .form-textarea {
                min-width: 0;
            }

            platform-date-picker {
                display: block;
                width: 100%;
                min-width: 0;
            }

            .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .integration-tabs {
                display: flex;
                gap: var(--space-2);
            }

            .integration-tabs button {
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                border-radius: var(--radius-md);
                padding: 6px 10px;
                font-size: var(--text-xs);
                cursor: pointer;
            }

            .integration-tabs button.active {
                border-color: var(--accent);
                color: var(--accent);
                background: var(--accent-subtle);
            }

            .integration-list {
                display: grid;
                gap: var(--space-2);
            }

            .integration-item {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                padding: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-secondary);
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: var(--space-2);
            }

            .actions {
                display: flex;
                justify-content: flex-end;
                gap: var(--space-2);
            }

            .advanced-toggle {
                display: flex;
                justify-content: flex-end;
            }

            .event-dialog-overlay {
                position: fixed;
                inset: 0;
                background: rgba(0, 0, 0, 0.22);
                backdrop-filter: blur(4px);
                -webkit-backdrop-filter: blur(4px);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: calc(var(--platform-modal-layer-z, var(--z-modal, 1000)) + 2);
                padding: var(--space-4);
            }

            .event-dialog {
                width: min(860px, 96vw);
                max-height: min(88vh, 88dvh);
                overflow: auto;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-strong);
                box-shadow: var(--glass-shadow-medium), 0 14px 34px rgba(0, 0, 0, 0.16);
                display: flex;
                flex-direction: column;
            }

            .event-dialog-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                padding: 20px 24px 12px;
            }

            .event-dialog-title {
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                line-height: 1.05;
                color: var(--text-primary);
                letter-spacing: -0.02em;
            }

            .event-dialog-subtitle {
                margin-top: 6px;
                display: flex;
                align-items: center;
                gap: 6px;
                flex-wrap: wrap;
            }

            .event-dialog-header-actions {
                display: inline-flex;
                align-items: center;
                gap: 10px;
            }

            .event-dialog-icon-btn {
                width: 32px;
                height: 32px;
                border-radius: 50%;
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
            }

            .event-dialog-icon-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            .event-compose {
                padding: 0 24px 0;
                display: grid;
                gap: 12px;
            }

            .event-compose-row {
                display: grid;
                grid-template-columns: 150px minmax(0, 1fr);
                gap: 12px;
                align-items: center;
                min-width: 0;
            }

            .event-compose-label {
                font-size: var(--text-sm);
                line-height: 1.1;
                color: var(--text-secondary);
                letter-spacing: -0.01em;
            }

            .event-compose-control {
                min-width: 0;
                display: grid;
                gap: 10px;
            }

            .event-compose-attachments {
                display: flex;
                align-items: center;
                gap: 8px;
                flex-wrap: wrap;
            }

            .event-compose-attachment {
                display: flex;
                align-items: center;
                gap: 8px;
                min-height: 36px;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-full);
                background: var(--glass-solid-subtle);
                padding: 4px 8px;
                max-width: 320px;
            }

            .event-compose-attachment-icon {
                color: var(--text-tertiary);
                flex-shrink: 0;
            }

            .event-compose-attachment-link {
                color: var(--text-primary);
                font-size: var(--text-sm);
                text-decoration: none;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                max-width: 220px;
            }

            .event-compose-attachment-remove {
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                font-size: 12px;
                line-height: 1;
                width: 20px;
                height: 20px;
                border-radius: 50%;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            .event-compose-attachment-remove:hover {
                color: var(--danger);
                background: color-mix(in srgb, var(--danger) 12%, transparent);
            }

            .event-compose-title-input,
            .event-compose-input {
                width: 100%;
                min-height: 44px;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                font-size: var(--text-sm);
                line-height: 1.1;
                padding: 10px 14px;
                outline: none;
            }

            .event-compose-title-input {
                border: 2px solid color-mix(in srgb, var(--accent) 55%, var(--glass-border-subtle));
                background: var(--glass-solid-subtle);
            }

            .event-compose-title-input:focus,
            .event-compose-input:focus {
                border-color: var(--accent);
                background: var(--glass-solid-subtle);
            }

            .event-compose-input::placeholder {
                color: var(--text-tertiary);
            }

            .attendees-picker {
                position: relative;
                display: grid;
                gap: 8px;
            }

            .attendees-tags {
                min-height: 44px;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                padding: 8px 10px;
                display: flex;
                align-items: center;
                gap: 8px;
                flex-wrap: wrap;
            }

            .attendee-tag {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                max-width: 100%;
                border-radius: var(--radius-full);
                background: color-mix(in srgb, var(--accent) 16%, var(--glass-solid-subtle));
                color: var(--text-primary);
                padding: 4px 8px;
                font-size: var(--text-xs);
            }

            .attendee-tag-label {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                max-width: 260px;
            }

            .attendee-tag-remove {
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                font-size: 12px;
                width: 16px;
                height: 16px;
                border-radius: 50%;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            .attendee-tag-remove:hover {
                color: var(--danger);
                background: color-mix(in srgb, var(--danger) 12%, transparent);
            }

            .attendees-input {
                flex: 1;
                min-width: 180px;
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                outline: none;
                padding: 0;
            }

            .attendees-input::placeholder {
                color: var(--text-tertiary);
            }

            .attendees-dropdown {
                position: absolute;
                top: calc(100% + 4px);
                left: 0;
                right: 0;
                max-height: 200px;
                overflow: auto;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-strong);
                z-index: 10;
                box-shadow: var(--glass-shadow-medium);
                padding: 4px;
                display: grid;
                gap: 2px;
            }

            .attendee-option {
                border: none;
                background: transparent;
                border-radius: var(--radius-sm);
                text-align: left;
                padding: 6px 8px;
                cursor: pointer;
                display: grid;
                gap: 2px;
            }

            .attendee-option:hover {
                background: var(--glass-solid-medium);
            }

            .attendee-option-name {
                font-size: var(--text-sm);
                color: var(--text-primary);
                font-weight: var(--font-medium);
            }

            .attendee-option-email {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            .event-compose-pills {
                display: flex;
                align-items: center;
                gap: 12px;
                flex-wrap: wrap;
            }

            .event-compose-pill {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                min-height: 38px;
                padding: 0 12px;
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1;
                display: inline-flex;
                align-items: center;
                gap: 8px;
                cursor: pointer;
            }

            .event-compose-pill small {
                font-size: var(--text-sm);
                font-weight: 500;
            }

            .event-color-palette {
                display: flex;
                align-items: center;
                gap: 8px;
                flex-wrap: wrap;
            }

            .event-color-swatch {
                width: 22px;
                height: 22px;
                border: none;
                border-radius: 50%;
                padding: 0;
                cursor: pointer;
                box-shadow: inset 0 0 0 1px color-mix(in srgb, #000 10%, transparent);
            }

            .event-color-swatch.active {
                box-shadow: 0 0 0 2px var(--glass-solid-strong), 0 0 0 4px color-mix(in srgb, #3f4959 55%, transparent);
            }

            .event-compose-textarea {
                width: 100%;
                min-height: 96px;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                font-size: var(--text-sm);
                line-height: 1.25;
                padding: 10px 12px;
                outline: none;
                resize: vertical;
            }

            .event-compose-time-layout {
                display: grid;
                gap: 10px;
            }

            .event-compose-time-row {
                display: grid;
                grid-template-columns: minmax(0, 1fr) 24px minmax(0, 1fr);
                gap: 10px;
                align-items: center;
            }

            .event-compose-time-sep {
                text-align: center;
                font-size: 18px;
                color: var(--text-tertiary);
            }

            .event-compose-options {
                display: flex;
                align-items: center;
                gap: 18px;
                flex-wrap: wrap;
            }

            .event-compose-switch {
                display: inline-flex;
                align-items: center;
                flex-shrink: 0;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1;
            }

            .event-compose-switch platform-switch {
                --text-primary: var(--text-secondary);
            }

            .event-compose-switch--spaced {
                margin-top: var(--space-2);
            }

            .event-compose-select {
                min-height: 40px;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                font-size: var(--text-sm);
                padding: 0 10px;
                max-width: 100%;
            }

            .event-compose-divider {
                height: 1px;
                background: var(--glass-border-subtle);
                margin: 2px 0;
            }

            .event-compose-footer {
                margin-top: 12px;
                border-top: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                border-radius: 0 0 var(--radius-xl) var(--radius-xl);
                padding: 14px 24px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 14px;
            }

            .event-compose-footer-left {
                display: inline-flex;
                align-items: center;
                gap: 10px;
            }

            .event-compose-link-btn {
                border: none;
                background: transparent;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                padding: 0;
            }

            .event-compose-delete-btn {
                border: none;
                background: transparent;
                color: var(--danger);
                font-size: var(--text-sm);
                cursor: pointer;
                padding: 0;
            }

            .event-compose-submit-btn {
                min-height: 40px;
                min-width: 130px;
                padding: 0 18px;
                font-size: var(--text-sm);
                font-weight: 600;
            }

            .event-compose-submit-btn:disabled {
                opacity: 0.7;
                cursor: default;
            }

            .event-source-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }

            @media (max-width: 1100px) {
                .event-dialog-title {
                    font-size: var(--text-lg);
                }

                .event-compose-label {
                    font-size: var(--text-sm);
                }

                .event-compose-title-input,
                .event-compose-input {
                    min-height: 50px;
                    font-size: var(--text-sm);
                }

                .event-compose-pill {
                    min-height: 44px;
                    font-size: var(--text-sm);
                }

                .event-compose-pill small {
                    font-size: var(--text-sm);
                }

                .event-compose-textarea {
                    font-size: var(--text-sm);
                }

                .event-compose-switch {
                    font-size: var(--text-sm);
                }

                .event-compose-select {
                    font-size: var(--text-sm);
                    min-height: 44px;
                }

                .event-compose-link-btn {
                    font-size: var(--text-sm);
                }

                .event-compose-submit-btn {
                    min-height: 50px;
                    font-size: var(--text-sm);
                }
            }

            @media (max-width: 1279px) {
                .calendar-shell {
                    grid-template-columns: 1fr;
                }

                .calendar-sidebar {
                    border-right: none;
                    padding-right: 0;
                    border-bottom: 1px solid var(--glass-border-subtle);
                    padding-bottom: var(--space-3);
                }
            }

            @media (max-width: 767px) {
                .event-dialog {
                    width: 100%;
                    border-radius: var(--radius-xl);
                }

                .event-dialog-header {
                    padding: 18px 16px 10px;
                }

                .event-compose {
                    padding: 0 16px;
                    gap: 12px;
                }

                .event-compose-row {
                    grid-template-columns: 1fr;
                    gap: 6px;
                    align-items: start;
                }

                .event-compose-label {
                    font-size: var(--text-sm);
                }

                .event-compose-title-input,
                .event-compose-input {
                    min-height: 42px;
                    font-size: var(--text-sm);
                    border-width: 2px;
                }

                .event-compose-time-row {
                    grid-template-columns: 1fr;
                    gap: 8px;
                }

                .event-compose-time-sep {
                    display: none;
                }

                .event-compose-switch {
                    font-size: var(--text-sm);
                }

                .event-compose-select {
                    font-size: var(--text-sm);
                    min-height: 40px;
                }

                .event-compose-footer {
                    padding: 14px 16px;
                    border-radius: 0 0 var(--radius-xl) var(--radius-xl);
                }

                .event-compose-link-btn {
                    font-size: var(--text-sm);
                }

                .event-compose-submit-btn {
                    min-height: 42px;
                    min-width: 120px;
                    font-size: var(--text-sm);
                }

                .calendar-fab {
                    display: inline-flex;
                    position: fixed;
                    right: max(20px, env(safe-area-inset-right));
                    bottom: max(24px, env(safe-area-inset-bottom));
                    z-index: calc(var(--platform-modal-layer-z, var(--z-modal, 1000)) + 2);
                    width: 52px;
                    height: 52px;
                    border-radius: 50%;
                    border: none;
                    align-items: center;
                    justify-content: center;
                    background: color-mix(in srgb, var(--accent) 92%, #000);
                    color: #fff;
                    font-size: 26px;
                    line-height: 1;
                    font-weight: 400;
                    cursor: pointer;
                    box-shadow: 0 8px 22px rgba(0, 0, 0, 0.2);
                }

                .toolbar--compact .btn-calendar-create.toolbar-create {
                    display: none;
                }

                .row.two {
                    grid-template-columns: 1fr;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.title = '';
        this._view = 'month';
        this._anchorDate = toDateInputValue(new Date());
        this._events = [];
        this._integrations = [];
        this._loading = false;
        this._saving = false;
        this._syncing = false;
        this._selectedEventId = null;
        this._activeProvider = 'google';
        this._showAdvanced = false;
        this._eventDialogOpen = false;
        this._showDescriptionField = false;
        this._uploadingAttachments = false;
        this._eventAttachments = [];
        this._eventMetadata = {};
        this._selectedEventSource = 'platform';
        this._selectedEventKind = 'meeting';
        this._selectedEventNamespace = null;
        this._timezoneOptions = [...BASE_TIMEZONE_OPTIONS];
        this._teamMembers = [];
        this._attendeeDraft = '';
        this._attendeeDropdownOpen = false;
        const currentTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
        if (!this._timezoneOptions.includes(currentTimeZone)) {
            this._timezoneOptions = [currentTimeZone, ...this._timezoneOptions];
        }
        const now = new Date();
        const defaultEnd = addDays(now, 0);
        defaultEnd.setMinutes(defaultEnd.getMinutes() + 30);
        this._eventForm = {
            kind: 'meeting',
            color: DEFAULT_EVENT_COLOR,
            title: '',
            description: '',
            location: '',
            timezone: currentTimeZone,
            all_day: false,
            start_at: toDateTimeInputValue(now),
            end_at: toDateTimeInputValue(defaultEnd),
            attendees: [],
            recurrence: 'none',
        };
        this._eventDeepLink = null;
        this._integrationForm = {
            username: '',
            app_password: '',
            default_calendar_id: '',
            sync_enabled: true,
            sync_inbound_enabled: true,
            sync_outbound_enabled: true,
            notifications_enabled: true,
        };
        this._isCompactLayout = false;
        this._dateSheetOpen = false;
        const sheetMonth = new Date();
        this._dateSheetMonthRef = toDateInputValue(new Date(sheetMonth.getFullYear(), sheetMonth.getMonth(), 1));
    }

    willUpdate(changedProperties) {
        super.willUpdate(changedProperties);
        this.title = this.i18n.t('title', {}, 'calendar');
    }

    _calT(key, params = {}) {
        return this.i18n.t(key, params, 'calendar');
    }

    _calendarLocaleTag() {
        const code = this.i18n.getCurrentLocale();
        if (code === 'ru') {
            return 'ru-RU';
        }
        return 'en-US';
    }

    async showModal() {
        this._dateSheetOpen = false;
        this._isCompactLayout = window.matchMedia('(max-width: 767px)').matches;
        this._isFullscreen = !this._isCompactLayout;
        if (this._isCompactLayout) {
            this._view = 'day';
            this.size = 'full';
        } else {
            this.size = 'md';
        }
        super.showModal();
        await this._loadTeamMembers();
        await this._reload();
    }

    async _loadTeamMembers() {
        if (!this.services.has('team')) {
            this._teamMembers = [];
            return;
        }
        const teamMembers = await this.services.get('team').getMembers();
        if (!Array.isArray(teamMembers)) {
            throw new Error('Team members response must be array');
        }
        this._teamMembers = teamMembers;
    }

    async _reload() {
        this._loading = true;
        const range = this._viewRange();
        const result = await this.calendarApi.listEvents({
            startAt: range.start.toISOString(),
            endAt: range.end.toISOString(),
            includeSources: null,
            limit: 2000,
        });
        if (!result || !Array.isArray(result.events) || !Array.isArray(result.integrations)) {
            throw new Error('Calendar API response is invalid');
        }
        this._events = result.events;
        this._integrations = result.integrations;
        this._loading = false;
    }

    _viewRange() {
        const anchor = parseDateInputLocal(this._anchorDate);
        if (Number.isNaN(anchor.getTime())) {
            throw new Error(`Invalid anchor date: ${this._anchorDate}`);
        }
        if (this._view === 'day') {
            const start = new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate(), 0, 0, 0, 0);
            const end = addDays(start, 1);
            return { start, end };
        }
        anchor.setHours(12, 0, 0, 0);
        if (this._view === 'week') {
            return { start: startOfWeek(anchor), end: endOfWeek(anchor) };
        }
        if (this._view === 'month') {
            return { start: startOfMonth(anchor), end: endOfMonth(anchor) };
        }
        throw new Error(`Unsupported view: ${this._view}`);
    }

    _periodLabel() {
        const anchor = parseDateInputLocal(this._anchorDate);
        if (this._view === 'day') {
            return anchor.toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
        }
        if (this._view === 'week') {
            anchor.setHours(12, 0, 0, 0);
            const start = startOfWeek(anchor);
            const end = addDays(start, 6);
            return `${start.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })} - ${end.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })}`;
        }
        anchor.setHours(12, 0, 0, 0);
        return anchor.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
    }

    async _movePeriod(delta) {
        const anchor = parseDateInputLocal(this._anchorDate);
        if (this._view === 'day') {
            anchor.setDate(anchor.getDate() + delta);
        } else if (this._view === 'week') {
            anchor.setDate(anchor.getDate() + (delta * 7));
        } else {
            anchor.setMonth(anchor.getMonth() + delta);
        }
        this._anchorDate = toDateInputValue(anchor);
        await this._reload();
    }

    _onViewChange(view) {
        this._view = view;
        this._reload();
    }

    _eventsForDate(date) {
        const dayStart = new Date(date.getFullYear(), date.getMonth(), date.getDate(), 0, 0, 0, 0);
        const dayEnd = addDays(dayStart, 1);
        return this._events.filter((event) => {
            const start = new Date(event.start_at);
            const end = new Date(event.end_at);
            return start < dayEnd && end > dayStart;
        });
    }

    _monthCells() {
        const anchor = parseDateInputLocal(this._anchorDate);
        anchor.setHours(12, 0, 0, 0);
        const monthStart = startOfMonth(anchor);
        const firstVisible = startOfWeek(monthStart);
        const today = new Date();
        const cells = [];
        for (let index = 0; index < 42; index += 1) {
            const date = addDays(firstVisible, index);
            const day = date.getDay();
            cells.push({
                date,
                iso: toDateInputValue(date),
                outside: date.getMonth() !== anchor.getMonth(),
                weekend: day === 0 || day === 6,
                today: isSameDay(date, today),
                events: this._eventsForDate(date),
            });
        }
        return cells;
    }

    _listRows() {
        const range = this._viewRange();
        const rows = [];
        let cursor = new Date(range.start.getTime());
        while (cursor < range.end) {
            rows.push({
                iso: toDateInputValue(cursor),
                label: cursor.toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'short' }),
                events: this._eventsForDate(cursor),
            });
            cursor = addDays(cursor, 1);
        }
        return rows;
    }

    _compactPeriodLabel() {
        const anchor = parseDateInputLocal(this._anchorDate);
        if (Number.isNaN(anchor.getTime())) {
            throw new Error(`Invalid anchor date: ${this._anchorDate}`);
        }
        return anchor.toLocaleDateString(this._calendarLocaleTag(), { weekday: 'short', day: 'numeric', month: 'long' });
    }

    _openDateSheet() {
        const anchor = parseDateInputLocal(this._anchorDate);
        if (Number.isNaN(anchor.getTime())) {
            throw new Error(`Invalid anchor date: ${this._anchorDate}`);
        }
        this._dateSheetMonthRef = toDateInputValue(new Date(anchor.getFullYear(), anchor.getMonth(), 1));
        this._dateSheetOpen = true;
    }

    _closeDateSheet() {
        this._dateSheetOpen = false;
    }

    _shiftDateSheetMonth(delta) {
        const ref = new Date(this._dateSheetMonthRef);
        if (Number.isNaN(ref.getTime())) {
            throw new Error(`Invalid date sheet month ref: ${this._dateSheetMonthRef}`);
        }
        const shifted = new Date(ref.getFullYear(), ref.getMonth() + delta, 1, 0, 0, 0, 0);
        this._dateSheetMonthRef = toDateInputValue(shifted);
    }

    _selectDateFromSheet(iso) {
        if (typeof iso !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
            throw new Error(`Invalid sheet date: ${iso}`);
        }
        const parsed = new Date(iso);
        if (Number.isNaN(parsed.getTime())) {
            throw new Error(`Invalid sheet date: ${iso}`);
        }
        this._anchorDate = iso;
        this._dateSheetOpen = false;
        this._reload();
    }

    _monthCellsForDateSheet() {
        const ref = new Date(this._dateSheetMonthRef);
        if (Number.isNaN(ref.getTime())) {
            throw new Error(`Invalid date sheet month ref: ${this._dateSheetMonthRef}`);
        }
        const monthStart = startOfMonth(ref);
        const anchorMonth = ref.getMonth();
        const firstVisible = startOfWeek(monthStart);
        const today = new Date();
        const cells = [];
        for (let index = 0; index < 42; index += 1) {
            const date = addDays(firstVisible, index);
            cells.push({
                date,
                iso: toDateInputValue(date),
                outside: date.getMonth() !== anchorMonth,
                today: isSameDay(date, today),
            });
        }
        return cells;
    }

    _renderDateSheet() {
        if (!this._dateSheetOpen) {
            return html``;
        }
        const weekdays = [1, 2, 3, 4, 5, 6, 7].map((i) => this._calT(`weekday_${i}`));
        const cells = this._monthCellsForDateSheet();
        const sheetMonth = new Date(this._dateSheetMonthRef);
        if (Number.isNaN(sheetMonth.getTime())) {
            throw new Error(`Invalid date sheet month ref: ${this._dateSheetMonthRef}`);
        }
        const monthTitle = sheetMonth.toLocaleDateString(this._calendarLocaleTag(), { month: 'long', year: 'numeric' });
        return html`
            <div class="date-sheet-overlay" @click=${() => this._closeDateSheet()}>
                <div class="date-sheet-card" @click=${(e) => e.stopPropagation()}>
                    <div class="date-sheet-header">
                        <span class="date-sheet-title">${monthTitle}</span>
                        <div class="date-sheet-nav">
                            <button type="button" class="btn-icon" @click=${() => this._shiftDateSheetMonth(-1)} aria-label=${this._calT('sheet_prev_month')}>
                                <platform-icon name="chevron-left" size="16"></platform-icon>
                            </button>
                            <button type="button" class="btn-icon" @click=${() => this._shiftDateSheetMonth(1)} aria-label=${this._calT('sheet_next_month')}>
                                <platform-icon name="chevron-right" size="16"></platform-icon>
                            </button>
                            <button type="button" class="btn-icon" @click=${() => this._closeDateSheet()} aria-label=${this._calT('sheet_close')}>
                                <platform-icon name="close" size="16"></platform-icon>
                            </button>
                        </div>
                    </div>
                    <div class="date-sheet-grid">
                        ${weekdays.map((label) => html`<div class="date-sheet-weekday">${label}</div>`)}
                        ${cells.map((cell) => html`
                            <button
                                type="button"
                                class="date-sheet-cell ${cell.outside ? 'outside' : ''} ${cell.today ? 'today' : ''} ${cell.iso === this._anchorDate ? 'selected' : ''}"
                                @click=${() => this._selectDateFromSheet(cell.iso)}
                            >
                                ${cell.date.getDate()}
                            </button>
                        `)}
                    </div>
                </div>
            </div>
        `;
    }

    _renderDayTimeline() {
        const anchor = parseDateInputLocal(this._anchorDate);
        if (Number.isNaN(anchor.getTime())) {
            throw new Error(`Invalid anchor date: ${this._anchorDate}`);
        }
        const hourPx = 52;
        const daySpanMin = 24 * 60;
        const dayHeightPx = 24 * hourPx;
        const events = this._eventsForDate(anchor);
        const allDay = events.filter((e) => Boolean(e.all_day));
        const timed = events.filter((e) => !e.all_day);
        const dayStart = new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate(), 0, 0, 0, 0);
        const dayEndMs = addDays(dayStart, 1).getTime();
        const layoutTimed = timed.map((event) => {
            const startMs = new Date(event.start_at).getTime();
            const endMs = new Date(event.end_at).getTime();
            if (Number.isNaN(startMs) || Number.isNaN(endMs)) {
                throw new Error('event must have valid start_at and end_at');
            }
            const startClamped = Math.max(startMs, dayStart.getTime());
            const endClamped = Math.min(endMs, dayEndMs);
            const startMin = (startClamped - dayStart.getTime()) / 60000;
            const durMin = Math.max((endClamped - startClamped) / 60000, 15);
            const top = (startMin / daySpanMin) * dayHeightPx;
            const height = Math.max((durMin / daySpanMin) * dayHeightPx, 28);
            const colorKey = normalizeEventColor(event.metadata?.[EVENT_COLOR_KEY]);
            return { event, top, height, colorKey, visibleStartMs: startClamped };
        });
        const hours = Array.from({ length: 24 }, (_, h) => h);
        const now = new Date();
        const showNow = isSameDay(now, anchor);
        const nowTop = showNow
            ? (((now.getHours() * 60 + now.getMinutes()) / daySpanMin) * dayHeightPx)
            : null;
        return html`
            <div class="day-timeline">
                ${allDay.length > 0 ? html`
                    <div class="day-all-day-row">
                        ${allDay.map((event) => html`
                            <button
                                type="button"
                                class="event-chip"
                                data-color=${normalizeEventColor(event.metadata?.[EVENT_COLOR_KEY])}
                                @click=${() => this._fillFormFromEvent(event)}
                            >
                                <span class="event-chip-title">${event.title}</span>
                            </button>
                        `)}
                    </div>
                ` : ''}
                <div class="day-timeline-scroll">
                    ${events.length === 0 ? html`<div class="hint" style="padding: var(--space-3);">${this._calT('events_empty')}</div>` : html`
                        <div class="day-timeline-body">
                            <div class="day-time-col">
                                ${hours.map((h) => html`
                                    <div class="day-time-label">${pad2(h)}:00</div>
                                `)}
                            </div>
                            <div class="day-tracks">
                                <div class="day-tracks-lines">
                                    ${hours.map(() => html`<div class="day-hour-slot"></div>`)}
                                </div>
                                <div class="day-events-layer">
                                    ${showNow && nowTop !== null ? html`
                                        <div class="day-now-line" style=${`top:${nowTop}px`}></div>
                                    ` : ''}
                                    ${layoutTimed.map(({ event, top, height, colorKey, visibleStartMs }) => html`
                                        <button
                                            type="button"
                                            class="day-event-block event-chip"
                                            data-color=${colorKey}
                                            style=${`top:${top}px;height:${height}px`}
                                            @click=${() => this._fillFormFromEvent(event)}
                                        >
                                            <span class="event-chip-time">${this._formatWallClockFromMs(visibleStartMs)}</span>
                                            <span class="event-chip-title">${event.title}</span>
                                        </button>
                                    `)}
                                </div>
                            </div>
                        </div>
                    `}
                </div>
            </div>
        `;
    }

    _sourceKey(source) {
        return String(source || '').toLowerCase();
    }

    _kindKey(kind) {
        return String(kind || '').toLowerCase();
    }

    _sourceLabel(source) {
        const key = this._sourceKey(source);
        if (key === 'platform') {
            return this._calT('source_platform');
        }
        if (key === 'crm') {
            return 'NetWorkle';
        }
        if (key === 'sync') {
            return 'Sync';
        }
        if (key === 'flows') {
            return 'Flows';
        }
        if (key === 'google') {
            return 'Google';
        }
        if (key === 'yandex') {
            return 'Yandex';
        }
        return key ? key.toUpperCase() : this._calT('unknown');
    }

    _kindLabel(kind) {
        const key = this._kindKey(kind);
        if (key === 'event') {
            return this._calT('kind_event');
        }
        if (key === 'meeting') {
            return this._calT('kind_meeting');
        }
        if (key === 'task') {
            return this._calT('kind_task');
        }
        if (key === 'note') {
            return this._calT('kind_note');
        }
        if (key === 'call') {
            return this._calT('kind_call');
        }
        return key ? key : this._calT('kind_generic');
    }

    _isEventEditable(source) {
        return this._sourceKey(source) === 'platform';
    }

    _formatWallClockFromMs(ms) {
        const instant = new Date(ms);
        if (Number.isNaN(instant.getTime())) {
            throw new Error('Invalid instant for wall clock');
        }
        return instant.toLocaleTimeString(this._calendarLocaleTag(), {
            hour: '2-digit',
            minute: '2-digit',
        });
    }

    _eventStartTimeLabel(event) {
        const startDate = new Date(event.start_at);
        if (Number.isNaN(startDate.getTime())) {
            throw new Error('event.start_at must be valid datetime');
        }
        return this._formatWallClockFromMs(startDate.getTime());
    }

    _fillFormFromEvent(event) {
        this._ensureTimezoneOption(event.timezone);
        this._selectedEventId = event.event_id;
        this._showDescriptionField = Boolean(event.description);
        this._selectedEventSource = this._sourceKey(event.source);
        this._selectedEventKind = this._kindKey(event.kind);
        this._selectedEventNamespace = event.namespace || null;
        this._eventMetadata = event.metadata && typeof event.metadata === 'object' ? { ...event.metadata } : {};
        this._eventAttachments = parseEventAttachments(this._eventMetadata);
        this._eventForm = {
            kind: event.kind || 'event',
            color: normalizeEventColor(this._eventMetadata[EVENT_COLOR_KEY]),
            title: event.title || '',
            description: event.description || '',
            location: event.location || '',
            timezone: event.timezone || 'UTC',
            all_day: Boolean(event.all_day),
            start_at: toDateTimeInputValue(new Date(event.start_at)),
            end_at: toDateTimeInputValue(new Date(event.end_at)),
            attendees: Array.isArray(event.attendees) ? event.attendees.map((item) => toAttendeeTag(item)) : [],
            recurrence: this._ruleToRecurrence(event.recurrence_rule),
        };
        this._eventDeepLink = typeof event.deep_link === 'string' && event.deep_link !== '' ? event.deep_link : null;
        this._attendeeDraft = '';
        this._attendeeDropdownOpen = false;
        this._eventDialogOpen = true;
    }

    _ensureTimezoneOption(timezone) {
        if (!timezone) {
            throw new Error('Timezone is required');
        }
        if (this._timezoneOptions.includes(timezone)) {
            return;
        }
        this._timezoneOptions = [timezone, ...this._timezoneOptions];
    }

    _ruleToRecurrence(rule) {
        if (!rule) {
            return 'none';
        }
        if (rule === 'FREQ=DAILY') {
            return 'daily';
        }
        if (rule === 'FREQ=WEEKLY') {
            return 'weekly';
        }
        if (rule === 'FREQ=MONTHLY') {
            return 'monthly';
        }
        return 'none';
    }

    _onEventFormChange(field, value) {
        this._eventForm = {
            ...this._eventForm,
            [field]: value,
        };
    }

    _attendeeTags() {
        if (!Array.isArray(this._eventForm.attendees)) {
            return [];
        }
        return this._eventForm.attendees.map((entry) => toAttendeeTag(entry));
    }

    _addAttendeeByEmail(emailValue) {
        const normalized = normalizeEmail(emailValue);
        if (!normalized) {
            return;
        }
        if (!EMAIL_PATTERN.test(normalized)) {
            this.error(this._calT('error_email_invalid'));
            return;
        }
        const current = this._attendeeTags();
        if (current.some((item) => item.email === normalized)) {
            this._attendeeDraft = '';
            this._attendeeDropdownOpen = false;
            return;
        }
        this._onEventFormChange('attendees', [
            ...current,
            {
                attendee_id: normalized,
                email: normalized,
                display_name: normalized,
                response_status: 'needsAction',
            },
        ]);
        this._attendeeDraft = '';
        this._attendeeDropdownOpen = false;
    }

    _addTeamMemberAsAttendee(member) {
        if (!member || typeof member !== 'object') {
            throw new Error('Team member is required');
        }
        const email = normalizeEmail(member.email);
        if (!email) {
            throw new Error('Team member email is required');
        }
        const current = this._attendeeTags();
        if (current.some((item) => item.email === email)) {
            this._attendeeDraft = '';
            this._attendeeDropdownOpen = false;
            return;
        }
        this._onEventFormChange('attendees', [
            ...current,
            {
                attendee_id: String(member.user_id || email),
                email,
                display_name: String(member.name || email).trim(),
                response_status: 'needsAction',
            },
        ]);
        this._attendeeDraft = '';
        this._attendeeDropdownOpen = false;
    }

    _removeAttendee(emailValue) {
        const email = normalizeEmail(emailValue);
        const nextAttendees = this._attendeeTags().filter((item) => item.email !== email);
        this._onEventFormChange('attendees', nextAttendees);
    }

    _attendeeSuggestions() {
        const query = this._attendeeDraft.trim().toLowerCase();
        const selectedEmails = new Set(this._attendeeTags().map((item) => item.email));
        const membersWithEmail = this._teamMembers
            .filter((member) => normalizeEmail(member.email) !== '')
            .filter((member) => !selectedEmails.has(normalizeEmail(member.email)));
        if (!query) {
            return membersWithEmail.slice(0, 8);
        }
        return membersWithEmail
            .filter((member) => {
                const name = String(member.name || '').toLowerCase();
                const email = String(member.email || '').toLowerCase();
                return name.includes(query) || email.includes(query);
            })
            .slice(0, 8);
    }

    _onAttendeeInputKeyDown(event) {
        if (event.key === 'Enter' || event.key === ',') {
            event.preventDefault();
            this._addAttendeeByEmail(this._attendeeDraft);
            return;
        }
        if (event.key === 'Backspace' && !this._attendeeDraft) {
            const tags = this._attendeeTags();
            if (tags.length === 0) {
                return;
            }
            this._removeAttendee(tags[tags.length - 1].email);
        }
    }

    _openCreateEventDialog(date) {
        const selectedDate = date instanceof Date ? new Date(date.getTime()) : parseDateInputLocal(this._anchorDate);
        if (Number.isNaN(selectedDate.getTime())) {
            throw new Error('Invalid date for event dialog');
        }
        const startDate = new Date(
            selectedDate.getFullYear(),
            selectedDate.getMonth(),
            selectedDate.getDate(),
            10,
            0,
            0,
            0
        );
        const endDate = new Date(startDate.getTime());
        endDate.setMinutes(endDate.getMinutes() + 30);
        this._selectedEventId = null;
        this._eventForm = {
            ...this._eventForm,
            kind: 'meeting',
            color: DEFAULT_EVENT_COLOR,
            title: '',
            description: '',
            location: '',
            attendees: [],
            recurrence: 'none',
            start_at: toDateTimeInputValue(startDate),
            end_at: toDateTimeInputValue(endDate),
        };
        this._eventDeepLink = null;
        this._selectedEventSource = 'platform';
        this._selectedEventKind = 'meeting';
        this._selectedEventNamespace = null;
        this._eventMetadata = {};
        this._eventAttachments = [];
        this._showDescriptionField = false;
        this._attendeeDraft = '';
        this._attendeeDropdownOpen = false;
        this._eventDialogOpen = true;
    }

    _closeEventDialog() {
        this._eventDialogOpen = false;
    }

    _triggerAttachmentSelect() {
        const fileInput = this.renderRoot?.querySelector('#calendar-event-file-input');
        if (!fileInput) {
            throw new Error('Attachment input not found');
        }
        fileInput.value = '';
        fileInput.click();
    }

    async _onAttachmentInputChange(event) {
        const files = Array.from(event.target.files || []);
        if (files.length === 0) {
            return;
        }
        this._uploadingAttachments = true;
        try {
            const uploadedAttachments = [];
            for (const file of files) {
                const uploadedFile = await this.filesApi.uploadFile(file);
                if (!uploadedFile || typeof uploadedFile !== 'object') {
                    throw new Error('File upload response is invalid');
                }
                if (typeof uploadedFile.file_id !== 'string' || uploadedFile.file_id === '') {
                    throw new Error('Uploaded file_id is required');
                }
                if (typeof uploadedFile.url !== 'string' || uploadedFile.url === '') {
                    throw new Error('Uploaded file url is required');
                }
                if (typeof uploadedFile.original_name !== 'string' || uploadedFile.original_name === '') {
                    throw new Error('Uploaded original_name is required');
                }
                uploadedAttachments.push({
                    file_id: uploadedFile.file_id,
                    name: uploadedFile.original_name,
                    url: uploadedFile.url,
                    content_type: typeof uploadedFile.content_type === 'string' ? uploadedFile.content_type : '',
                    file_size: Number.isFinite(uploadedFile.file_size) ? uploadedFile.file_size : 0,
                });
            }
            const existingIds = new Set(this._eventAttachments.map((item) => item.file_id));
            const uniqueUploads = uploadedAttachments.filter((item) => !existingIds.has(item.file_id));
            this._eventAttachments = [...this._eventAttachments, ...uniqueUploads];
        } finally {
            this._uploadingAttachments = false;
        }
    }

    _removeAttachment(fileId) {
        this._eventAttachments = this._eventAttachments.filter((item) => item.file_id !== fileId);
    }

    async _saveEvent() {
        this._saving = true;
        try {
            if (this._selectedEventId && !this._isEventEditable(this._selectedEventSource)) {
                throw new Error(this._calT('err_edit_remote', { label: this._sourceLabel(this._selectedEventSource) }));
            }
            const payload = {
                title: this._eventForm.title.trim(),
                kind: String(this._eventForm.kind || '').trim(),
                source: 'platform',
                source_id: null,
                namespace: null,
                description: this._eventForm.description.trim() || null,
                location: this._eventForm.location.trim() || null,
                status: 'confirmed',
                timezone: this._eventForm.timezone.trim(),
                all_day: Boolean(this._eventForm.all_day),
                start_at: new Date(this._eventForm.start_at).toISOString(),
                end_at: new Date(this._eventForm.end_at).toISOString(),
                attendees: this._attendeeTags(),
                recurrence_rule: recurrenceToRule(this._eventForm.recurrence),
                recurrence_id: null,
                series_id: null,
                deep_link: null,
                metadata: buildEventMetadata(
                    {
                        ...this._eventMetadata,
                        [EVENT_COLOR_KEY]: normalizeEventColor(this._eventForm.color),
                    },
                    this._eventAttachments
                ),
            };
            if (!payload.title) {
                throw new Error(this._calT('err_title_required'));
            }
            if (!payload.kind) {
                throw new Error(this._calT('err_kind_required'));
            }
            if (new Date(payload.start_at) >= new Date(payload.end_at)) {
                throw new Error(this._calT('err_end_after_start'));
            }
            if (this._selectedEventId) {
                await this.calendarApi.updateEvent(this._selectedEventId, payload);
            } else {
                await this.calendarApi.createEvent(payload);
            }
            this._selectedEventId = null;
            this._selectedEventSource = 'platform';
            this._selectedEventKind = 'meeting';
            this._selectedEventNamespace = null;
            this._eventForm = {
                ...this._eventForm,
                kind: 'meeting',
                color: DEFAULT_EVENT_COLOR,
                title: '',
                description: '',
                location: '',
                attendees: [],
                recurrence: 'none',
            };
            this._eventMetadata = {};
            this._eventDeepLink = null;
            this._eventAttachments = [];
            this._attendeeDraft = '';
            this._attendeeDropdownOpen = false;
            this._eventDialogOpen = false;
            await this._reload();
        } catch (error) {
            this.error(error instanceof Error ? error.message : this._calT('error_save_event'));
        } finally {
            this._saving = false;
        }
    }

    async _deleteSelectedEvent() {
        if (!this._selectedEventId) {
            throw new Error(this._calT('err_no_event_selected'));
        }
        if (!this._isEventEditable(this._selectedEventSource)) {
            throw new Error(this._calT('err_delete_remote', { label: this._sourceLabel(this._selectedEventSource) }));
        }
        await this.calendarApi.deleteEvent(this._selectedEventId);
        this._selectedEventId = null;
        this._selectedEventSource = 'platform';
        this._selectedEventKind = 'meeting';
        this._selectedEventNamespace = null;
        this._eventMetadata = {};
        this._eventAttachments = [];
        this._eventDeepLink = null;
        this._eventDialogOpen = false;
        await this._reload();
    }

    async _saveIntegration() {
        this._saving = true;
        if (this._activeProvider === 'google') {
            this._saving = false;
            throw new Error(this._calT('err_google_oauth_only'));
        }
        const payload = {
            provider: this._activeProvider,
            username: this._integrationForm.username.trim(),
            access_token: this._integrationForm.app_password.trim(),
            refresh_token: null,
            expires_at: null,
            scope: null,
            token_type: null,
            default_calendar_id: this._integrationForm.default_calendar_id.trim() || null,
            sync_enabled: Boolean(this._integrationForm.sync_enabled),
            sync_inbound_enabled: Boolean(this._integrationForm.sync_inbound_enabled),
            sync_outbound_enabled: Boolean(this._integrationForm.sync_outbound_enabled),
            notifications_enabled: Boolean(this._integrationForm.notifications_enabled),
        };
        if (!payload.username) {
            this._saving = false;
            throw new Error(this._calT('err_username_required'));
        }
        if (!payload.access_token) {
            this._saving = false;
            throw new Error(this._calT('err_app_password_required'));
        }
        await this.calendarApi.connectIntegration(payload);
        this._saving = false;
        await this._reload();
    }

    _startGoogleConnect() {
        const returnPath = `${window.location.pathname}${window.location.search}`;
        const connectUrl = this.calendarApi.getGoogleConnectUrl(returnPath);
        window.location.assign(connectUrl);
    }

    async _disconnectIntegration(provider) {
        await this.calendarApi.disconnectIntegration(provider);
        await this._reload();
    }

    async _runSync(provider) {
        this._syncing = true;
        const range = this._viewRange();
        await this.calendarApi.runSync({
            provider,
            start_at: range.start.toISOString(),
            end_at: range.end.toISOString(),
        });
        this._syncing = false;
        await this._reload();
    }

    _onIntegrationProviderSelect(provider) {
        this._activeProvider = provider;
        const activeIntegration = this._integrations.find((item) => item.provider === provider) || null;
        if (provider !== 'yandex' || !activeIntegration) {
            return;
        }
        const settings = activeIntegration.settings || {};
        this._integrationForm = {
            ...this._integrationForm,
            default_calendar_id: settings.default_calendar_id || '',
            sync_enabled: settings.sync_enabled !== false,
            sync_inbound_enabled: settings.sync_inbound_enabled !== false,
            sync_outbound_enabled: settings.sync_outbound_enabled !== false,
            notifications_enabled: settings.notifications_enabled !== false,
        };
    }

    _renderMonth() {
        const weekdays = [1, 2, 3, 4, 5, 6, 7].map((i) => this._calT(`weekday_${i}`));
        const cells = this._monthCells();
        return html`
            <div class="month-grid">
                ${weekdays.map((label, index) => html`
                    <div class="weekday ${index >= 5 ? 'weekend' : ''}">${label}</div>
                `)}
                ${cells.map((cell) => html`
                    <article
                        class="month-cell ${cell.outside ? 'outside' : ''} ${cell.weekend ? 'weekend' : ''} ${cell.today ? 'today' : ''}"
                        @click=${() => this._openCreateEventDialog(cell.date)}
                    >
                        <div class="date-label">${cell.date.getDate()}</div>
                        <div class="month-cell-events">
                            ${cell.events.slice(0, 3).map((event) => html`
                                <button
                                    class="event-chip ${this._selectedEventId === event.event_id ? 'active' : ''}"
                                    data-color=${normalizeEventColor(event.metadata?.[EVENT_COLOR_KEY])}
                                    type="button"
                                    @click=${(e) => {
                                        e.stopPropagation();
                                        this._fillFormFromEvent(event);
                                    }}
                                    title=${`${this._sourceLabel(event.source)} • ${this._kindLabel(event.kind)}`}
                                >
                                    <span class="event-chip-top">
                                        <span class="event-badge" data-source=${this._sourceKey(event.source)}>${this._sourceLabel(event.source)}</span>
                                        <span class="event-badge">${this._kindLabel(event.kind)}</span>
                                        ${eventMetadataHasSyncMeeting(event.metadata) ? html`
                                            <span class="event-badge event-badge-sync" data-source="sync">
                                                <img class="event-sync-logo-inline" src=${SYNC_LOGO_SRC} alt="" />
                                                ${this._calT('tag_sync')}
                                            </span>
                                        ` : ''}
                                    </span>
                                    <span class="event-chip-title">
                                        <span class="event-chip-time">${this._eventStartTimeLabel(event)}</span>${event.title}
                                    </span>
                                </button>
                            `)}
                        </div>
                    </article>
                `)}
            </div>
        `;
    }

    _renderList() {
        const rows = this._listRows();
        return html`
            <div class="list-view">
                ${rows.map((row) => html`
                    <article class="section">
                        <div class="section-title">${row.label}</div>
                        ${row.events.length === 0 ? html`
                            <div class="hint">${this._calT('events_empty')}</div>
                        ` : row.events.map((event) => html`
                            <button
                                class="list-item ${this._selectedEventId === event.event_id ? 'active' : ''}"
                                type="button"
                                @click=${() => this._fillFormFromEvent(event)}
                            >
                                <div>
                                    <div class="list-title">${event.title}</div>
                                    <div class="list-meta">${new Date(event.start_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}</div>
                                    <div class="list-badges">
                                        <span class="event-badge" data-source=${this._sourceKey(event.source)}>${this._sourceLabel(event.source)}</span>
                                        <span class="event-badge">${this._kindLabel(event.kind)}</span>
                                        ${eventMetadataHasSyncMeeting(event.metadata) ? html`
                                            <span class="event-badge event-badge-sync" data-source="sync">
                                                <img class="event-sync-logo-inline" src=${SYNC_LOGO_SRC} alt="" />
                                                ${this._calT('tag_sync')}
                                            </span>
                                        ` : ''}
                                        ${event.namespace ? html`<span class="event-badge">${event.namespace}</span>` : ''}
                                    </div>
                                </div>
                                <platform-icon name="calendar" size="14"></platform-icon>
                            </button>
                        `)}
                    </article>
                `)}
            </div>
        `;
    }

    _renderEventForm() {
        const submitLabel = this._saving
            ? this._calT('compose_saving')
            : (this._selectedEventId ? this._calT('compose_save') : this._calT('compose_create'));
        const c = (key, params) => this._calT(key, params);
        return html`
            <div class="event-compose">
                <div class="event-compose-row">
                    <label class="event-compose-label">${c('label_title')}</label>
                    <div class="event-compose-control">
                        <input
                            class="event-compose-title-input"
                            .value=${this._eventForm.title}
                            @input=${(e) => this._onEventFormChange('title', e.target.value)}
                        />
                    </div>
                </div>

                <div class="event-compose-row">
                    <div></div>
                    <div class="event-compose-control">
                        <input id="calendar-event-file-input" type="file" hidden multiple @change=${this._onAttachmentInputChange} />
                        <div class="event-compose-pills">
                            <button class="event-compose-pill" type="button" @click=${() => { this._showDescriptionField = !this._showDescriptionField; }}>
                                <span>+</span>
                                <small>${c('label_description')}</small>
                            </button>
                            <button class="event-compose-pill" type="button" @click=${this._triggerAttachmentSelect} ?disabled=${this._uploadingAttachments}>
                                <small>${c('label_attach')}</small>
                            </button>
                        </div>
                        ${this._eventAttachments.length > 0 ? html`
                            <div class="event-compose-attachments">
                                ${this._eventAttachments.map((attachment) => html`
                                    <div class="event-compose-attachment">
                                        <platform-icon
                                            class="event-compose-attachment-icon"
                                            file-icon
                                            name=${resolveFileIconKey(
                                                attachment.name,
                                                typeof attachment.content_type === 'string' ? attachment.content_type : '',
                                            )}
                                            size="14"
                                        ></platform-icon>
                                        <a
                                            class="event-compose-attachment-link"
                                            href=${attachment.url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            title=${attachment.name}
                                        >
                                            ${attachment.name}
                                        </a>
                                        <button
                                            class="event-compose-attachment-remove"
                                            type="button"
                                            @click=${() => this._removeAttachment(attachment.file_id)}
                                            title=${c('remove_file')}
                                        >
                                            ×
                                        </button>
                                    </div>
                                `)}
                            </div>
                        ` : ''}
                    </div>
                </div>

                ${this._showDescriptionField ? html`
                    <div class="event-compose-row">
                        <label class="event-compose-label">${c('label_description')}</label>
                        <div class="event-compose-control">
                            <textarea
                                class="event-compose-textarea"
                                rows="3"
                                .value=${this._eventForm.description}
                                @input=${(e) => this._onEventFormChange('description', e.target.value)}
                            ></textarea>
                        </div>
                    </div>
                ` : ''}

                <div class="event-compose-row">
                    <label class="event-compose-label">${c('label_attendees')}</label>
                    <div class="event-compose-control">
                        <div class="attendees-picker">
                            <div class="attendees-tags">
                                ${this._attendeeTags().map((attendee) => html`
                                    <span class="attendee-tag">
                                        <span class="attendee-tag-label">${attendee.display_name} (${attendee.email})</span>
                                        <button
                                            class="attendee-tag-remove"
                                            type="button"
                                            title=${c('remove_attendee')}
                                            @click=${() => this._removeAttendee(attendee.email)}
                                        >
                                            ×
                                        </button>
                                    </span>
                                `)}
                                <input
                                    class="attendees-input"
                                    .value=${this._attendeeDraft}
                                    @focus=${() => { this._attendeeDropdownOpen = true; }}
                                    @blur=${() => {
                                        setTimeout(() => {
                                            this._attendeeDropdownOpen = false;
                                        }, 120);
                                    }}
                                    @input=${(event) => {
                                        this._attendeeDraft = event.target.value;
                                        this._attendeeDropdownOpen = true;
                                    }}
                                    @keydown=${(event) => this._onAttendeeInputKeyDown(event)}
                                    placeholder=${c('attendee_placeholder')}
                                />
                            </div>
                            ${this._attendeeDropdownOpen && this._attendeeSuggestions().length > 0 ? html`
                                <div class="attendees-dropdown">
                                    ${this._attendeeSuggestions().map((member) => html`
                                        <button class="attendee-option" type="button" @mousedown=${(event) => event.preventDefault()} @click=${() => this._addTeamMemberAsAttendee(member)}>
                                            <span class="attendee-option-name">${member.name || member.email}</span>
                                            <span class="attendee-option-email">${member.email}</span>
                                        </button>
                                    `)}
                                </div>
                            ` : ''}
                        </div>
                    </div>
                </div>

                <div class="event-compose-row">
                    <label class="event-compose-label">${c('label_datetime')}</label>
                    <div class="event-compose-time-layout">
                        <div class="event-compose-time-row">
                            <platform-date-picker
                                mode="datetime"
                                value-format="iso"
                                .value=${this._eventForm.start_at}
                                @change=${(e) => this._onEventFormChange('start_at', e.target.value)}
                            ></platform-date-picker>
                            <div class="event-compose-time-sep">-</div>
                            <platform-date-picker
                                mode="datetime"
                                value-format="iso"
                                .value=${this._eventForm.end_at}
                                @change=${(e) => this._onEventFormChange('end_at', e.target.value)}
                            ></platform-date-picker>
                        </div>
                        <div class="event-compose-options">
                            <div class="event-compose-switch">
                                <platform-switch
                                    .checked=${Boolean(this._eventForm.all_day)}
                                    .label=${c('all_day')}
                                    @change=${(e) => this._onEventFormChange('all_day', e.detail.value)}
                                ></platform-switch>
                            </div>
                            <div class="event-compose-switch">
                                <platform-switch
                                    .checked=${this._eventForm.recurrence !== 'none'}
                                    .label=${c('repeat')}
                                    @change=${(e) => this._onEventFormChange('recurrence', e.detail.value ? 'weekly' : 'none')}
                                ></platform-switch>
                            </div>
                            <select
                                class="event-compose-select"
                                .value=${this._eventForm.timezone}
                                @change=${(e) => this._onEventFormChange('timezone', e.target.value)}
                            >
                                ${this._timezoneOptions.map((timezone) => html`
                                    <option value=${timezone}>${timezone}</option>
                                `)}
                            </select>
                        </div>
                    </div>
                </div>

                <div class="event-compose-row">
                    <label class="event-compose-label">${c('label_color')}</label>
                    <div class="event-compose-control">
                        <div class="event-color-palette">
                            ${EVENT_COLOR_OPTIONS.map((color) => html`
                                <button
                                    class="event-color-swatch ${this._eventForm.color === color.key ? 'active' : ''}"
                                    type="button"
                                    style=${`background:${color.dot};`}
                                    title=${color.key}
                                    @click=${() => this._onEventFormChange('color', color.key)}
                                ></button>
                            `)}
                        </div>
                    </div>
                </div>

                <div class="event-compose-row">
                    <label class="event-compose-label">${c('label_type')}</label>
                    <div class="event-compose-control">
                        <select
                            class="event-compose-select"
                            .value=${this._eventForm.kind}
                            @change=${(e) => this._onEventFormChange('kind', e.target.value)}
                            ?disabled=${this._selectedEventId && !this._isEventEditable(this._selectedEventSource)}
                        >
                            <option value="meeting">${c('kind_meeting')}</option>
                            <option value="event">${c('kind_event')}</option>
                            <option value="task">${c('kind_task')}</option>
                            <option value="note">${c('kind_note')}</option>
                            <option value="call">${c('kind_call')}</option>
                        </select>
                    </div>
                </div>

                <div class="event-compose-divider"></div>

                <div class="event-compose-row">
                    <label class="event-compose-label">${c('label_location')}</label>
                    <div class="event-compose-control">
                        <input
                            class="event-compose-input"
                            .value=${this._eventForm.location}
                            @input=${(e) => this._onEventFormChange('location', e.target.value)}
                            placeholder=${c('location_placeholder')}
                        />
                    </div>
                </div>

                ${this._selectedEventSource === 'platform' && (!this._selectedEventId || this._isEventEditable(this._selectedEventSource)) && this._eventForm.kind === 'meeting' ? html`
                    <div class="event-compose-row">
                        <label class="event-compose-label">
                            <span class="event-compose-sync-head">
                                <img class="event-sync-logo-inline" src=${SYNC_LOGO_SRC} alt="" />
                                ${c('tag_sync')}
                            </span>
                        </label>
                        <div class="event-compose-control">
                            <div class="event-compose-sync-row event-compose-sync-hint-row">
                                <p class="event-compose-meeting-sync-hint">${c('meeting_sync_hint')}</p>
                                ${this._eventDeepLink ? html`
                                    <a
                                        class="event-compose-join-link"
                                        href=${this._eventDeepLink}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                    >
                                        <platform-icon name="paperclip" size="16"></platform-icon>
                                        <span>${c('sync_join_open')}</span>
                                    </a>
                                ` : ''}
                            </div>
                        </div>
                    </div>
                ` : ''}
            </div>

            <div class="event-compose-footer">
                <div class="event-compose-footer-left">
                    ${this._selectedEventId && this._isEventEditable(this._selectedEventSource) ? html`
                        <button class="btn btn-danger" type="button" @click=${this._deleteSelectedEvent} ?disabled=${this._saving}>${c('delete')}</button>
                    ` : ''}
                    ${this._selectedEventId && !this._isEventEditable(this._selectedEventSource) ? html`
                        <span class="event-source-hint">${c('edit_in_service', { source: this._sourceLabel(this._selectedEventSource) })}</span>
                    ` : ''}
                </div>
                <button
                    class="btn btn-primary event-compose-submit-btn"
                    type="button"
                    @click=${this._saveEvent}
                    ?disabled=${this._saving || this._uploadingAttachments || (this._selectedEventId && !this._isEventEditable(this._selectedEventSource))}
                >
                    ${submitLabel}
                </button>
            </div>
        `;
    }

    _renderIntegrations() {
        const providers = ['google', 'yandex'];
        const activeIntegration = this._integrations.find((item) => item.provider === this._activeProvider) || null;
        const c = (key, params) => this._calT(key, params);
        return html`
            <section class="section">
                <div class="section-title">${c('integrations_title')}</div>
                <div class="integration-tabs">
                    ${providers.map((provider) => html`
                        <button
                            type="button"
                            class=${this._activeProvider === provider ? 'active' : ''}
                            @click=${() => this._onIntegrationProviderSelect(provider)}
                        >
                            ${provider.toUpperCase()}
                        </button>
                    `)}
                </div>

                ${this._activeProvider === 'google' ? html`
                    <div class="hint">
                        ${c('google_oauth_hint')}
                    </div>
                    <div class="hint">
                        ${c('autosync_hint')}
                    </div>
                    ${activeIntegration ? html`
                        <div class="hint">
                            ${c('notifications_label', {
                                state: activeIntegration.settings?.notifications_enabled === false
                                    ? c('notifications_off')
                                    : c('notifications_on'),
                            })}
                        </div>
                    ` : ''}
                    <div class="actions">
                        <button class="btn btn-primary" type="button" @click=${() => this._startGoogleConnect()}>
                            ${activeIntegration ? c('reconnect_google') : c('connect_google')}
                        </button>
                        <button class="btn btn-secondary" type="button" @click=${() => this._runSync('google')} ?disabled=${this._syncing || !activeIntegration}>
                            ${this._syncing ? c('syncing') : c('sync')}
                        </button>
                        ${activeIntegration ? html`
                            <button class="btn btn-danger" type="button" @click=${() => this._disconnectIntegration('google')}>
                                ${c('disconnect')}
                            </button>
                        ` : ''}
                    </div>
                ` : html`
                    <div class="row">
                        <label class="form-label">Yandex username</label>
                        <input
                            class="form-input"
                            .value=${this._integrationForm.username}
                            @input=${(e) => this._integrationForm = { ...this._integrationForm, username: e.target.value }}
                            placeholder="login@yandex.ru"
                        />
                    </div>
                    <div class="row">
                        <label class="form-label">${c('yandex_app_password')}</label>
                        <input
                            class="form-input"
                            .value=${this._integrationForm.app_password}
                            @input=${(e) => this._integrationForm = { ...this._integrationForm, app_password: e.target.value }}
                            placeholder=${c('yandex_password_placeholder')}
                        />
                    </div>
                    <div class="row">
                        <label class="form-label">Calendar id</label>
                        <input
                            class="form-input"
                            .value=${this._integrationForm.default_calendar_id}
                            @input=${(e) => this._integrationForm = { ...this._integrationForm, default_calendar_id: e.target.value }}
                            placeholder="default"
                        />
                    </div>
                    <div class="event-compose-switch event-compose-switch--spaced">
                        <platform-switch
                            .checked=${Boolean(this._integrationForm.notifications_enabled)}
                            .label=${c('notifications_new_events')}
                            @change=${(e) => {
                                this._integrationForm = { ...this._integrationForm, notifications_enabled: e.detail.value };
                            }}
                        ></platform-switch>
                    </div>
                    <div class="hint">
                        ${c('autosync_hint')}
                    </div>

                    <div class="actions">
                        <button class="btn btn-primary" type="button" @click=${this._saveIntegration} ?disabled=${this._saving}>
                            ${c('save_connection')}
                        </button>
                        <button class="btn btn-secondary" type="button" @click=${() => this._runSync('yandex')} ?disabled=${this._syncing || !activeIntegration}>
                            ${this._syncing ? c('syncing') : c('sync')}
                        </button>
                        ${activeIntegration ? html`
                            <button class="btn btn-danger" type="button" @click=${() => this._disconnectIntegration('yandex')}>
                                ${c('disconnect')}
                            </button>
                        ` : ''}
                    </div>
                `}

                <div class="integration-list">
                    ${this._integrations.map((integration) => html`
                        <div class="integration-item">
                            <div>
                                <div>${integration.provider.toUpperCase()} / ${integration.settings?.default_calendar_id || 'no-calendar'}</div>
                                <div class="hint">updated: ${new Date(integration.updated_at).toLocaleString('ru-RU')}</div>
                            </div>
                            <button class="btn btn-danger" type="button" @click=${() => this._disconnectIntegration(integration.provider)}>${c('disconnect')}</button>
                        </div>
                    `)}
                </div>
            </section>
        `;
    }

    _renderEventDialog() {
        if (!this._eventDialogOpen) {
            return html``;
        }
        return html`
            <div class="event-dialog-overlay" @click=${() => this._closeEventDialog()}>
                <section class="event-dialog" @click=${(e) => e.stopPropagation()}>
                    <div class="event-dialog-header">
                        <div>
                            <div class="event-dialog-title">${this._selectedEventId ? this._calT('dialog_edit') : this._calT('dialog_new')}</div>
                            ${this._selectedEventId ? html`
                                <div class="event-dialog-subtitle">
                                    <span class="event-badge" data-source=${this._sourceKey(this._selectedEventSource)}>${this._sourceLabel(this._selectedEventSource)}</span>
                                    <span class="event-badge">${this._kindLabel(this._selectedEventKind)}</span>
                                    ${eventMetadataHasSyncMeeting(this._eventMetadata) ? html`
                                        <span class="event-badge event-badge-sync" data-source="sync">
                                            <img class="event-sync-logo-inline" src=${SYNC_LOGO_SRC} alt="" />
                                            ${this._calT('tag_sync')}
                                        </span>
                                    ` : ''}
                                    ${this._selectedEventNamespace ? html`<span class="event-badge">${this._selectedEventNamespace}</span>` : ''}
                                </div>
                            ` : ''}
                        </div>
                        <div class="event-dialog-header-actions">
                            <button class="event-dialog-icon-btn" type="button" @click=${() => this._closeEventDialog()}>
                                <platform-icon name="close" size="20"></platform-icon>
                            </button>
                        </div>
                    </div>
                    ${this._renderEventForm()}
                </section>
            </div>
        `;
    }

    _renderCalendarPanel() {
        if (this._loading) {
            return html`<div class="hint">${this._calT('loading')}</div>`;
        }
        if (this._view === 'month') {
            return this._renderMonth();
        }
        if (this._view === 'day') {
            return this._renderDayTimeline();
        }
        return this._renderList();
    }

    renderBody() {
        const v = (key) => this._calT(key);
        const compact = this._isCompactLayout;
        return html`
            <div class="calendar-shell">
                <section class="calendar-main">
                    <div class="toolbar ${compact ? 'toolbar--compact' : ''}">
                        <div class="toolbar-left">
                            ${compact ? html`
                                <button class="btn-icon" type="button" @click=${() => { void this._movePeriod(-1); }} aria-label=${v('sheet_prev_day')}>
                                    <platform-icon name="chevron-left" size="16"></platform-icon>
                                </button>
                                <button class="period-date-btn" type="button" @click=${() => this._openDateSheet()} title=${v('pick_date_title')}>
                                    ${this._compactPeriodLabel()}
                                </button>
                                <button class="btn-icon" type="button" @click=${() => { void this._movePeriod(1); }} aria-label=${v('sheet_next_day')}>
                                    <platform-icon name="chevron-right" size="16"></platform-icon>
                                </button>
                            ` : html`
                                <div class="title">${this._periodLabel()}</div>
                                <button class="btn-icon" type="button" @click=${() => { void this._movePeriod(-1); }}>
                                    <platform-icon name="chevron-left" size="16"></platform-icon>
                                </button>
                                <button class="btn-icon" type="button" @click=${() => { void this._movePeriod(1); }}>
                                    <platform-icon name="chevron-right" size="16"></platform-icon>
                                </button>
                            `}
                        </div>
                        <div class="toolbar-right">
                            <button
                                class="btn btn-primary btn-calendar-create toolbar-create"
                                type="button"
                                title=${v('create_event')}
                                aria-label=${v('create_event')}
                                @click=${() => this._openCreateEventDialog(parseDateInputLocal(this._anchorDate))}
                            >
                                <platform-icon name="plus" size="20"></platform-icon>
                            </button>
                            <div class="advanced-toggle">
                                <button class="btn btn-secondary" type="button" @click=${() => { this._showAdvanced = !this._showAdvanced; }}>
                                    ${this._showAdvanced ? v('advanced_hide') : v('advanced_show')}
                                </button>
                            </div>
                            ${compact ? '' : html`
                                <div class="view-segment">
                                    <button class=${this._view === 'day' ? 'active' : ''} type="button" @click=${() => this._onViewChange('day')}>${v('view_day')}</button>
                                    <button class=${this._view === 'week' ? 'active' : ''} type="button" @click=${() => this._onViewChange('week')}>${v('view_week')}</button>
                                    <button class=${this._view === 'month' ? 'active' : ''} type="button" @click=${() => this._onViewChange('month')}>${v('view_month')}</button>
                                </div>
                            `}
                        </div>
                    </div>
                    <div class="calendar-panel ${this._view === 'day' ? 'calendar-panel--day' : ''}">
                        ${this._renderCalendarPanel()}
                    </div>
                    ${this._showAdvanced ? this._renderIntegrations() : ''}
                </section>
            </div>
            ${compact ? html`
                <button
                    type="button"
                    class="calendar-fab"
                    title=${v('create_event')}
                    aria-label=${v('create_event')}
                    @click=${() => this._openCreateEventDialog(parseDateInputLocal(this._anchorDate))}
                >+</button>
            ` : ''}
            ${this._renderDateSheet()}
            ${this._renderEventDialog()}
        `;
    }
}

customElements.define('platform-calendar-modal', PlatformCalendarModal);
