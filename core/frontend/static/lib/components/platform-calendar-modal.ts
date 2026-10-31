import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformModal } from './glass-modal.js';
import { formStyles } from '../styles/shared/form.styles.js';
import { buttonStyles } from '../styles/shared/button.styles.js';
import './platform-icon.js';
import './platform-mail-calendar-rail.js';
import { resolveFileIconKey } from '../utils/file-icons.js';
import { platformStorageKey } from '../utils/storage-keys.js';
import { storageGet, storageSet } from '../utils/platform-storage.js';
import './platform-date-picker.js';
import './platform-timezone-picker.js';
import './platform-switch.js';
import { CALENDAR_EVENTS } from '../events/reducers/calendar.js';
import { MAIL_EVENTS } from '../events/reducers/mail.js';
import { TEAM_EVENTS } from '../events/reducers/team.js';
import { FILES_EVENTS } from '../events/reducers/files.js';
import { buildCalendarEventFileCreateSpecJson } from '../utils/file-create-spec.js';
import { registerModalKind } from '../utils/modal-registry.js';
import type { SelectController } from '../events/select-controller.js';
import type { PlatformEvent } from '../events/contract.js';
import { isPlainRecord, payloadFields, stringField } from '../events/payload.js';
import type { CalendarState } from '../events/reducers/calendar.js';
import type { MailState } from '../events/reducers/mail.js';
import type { TeamMemberRecord } from '../events/reducers/team.js';

import { COLOR_PALETTE, resolvePaletteColor } from '@platform/lib/utils/color-palette.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';

function calendarFailureMessage(event: PlatformEvent): string {
    const message = stringField(payloadFields(event).message);
    return message === null ? '' : message;
}

const EVENT_COLOR_KEY = 'event_color';
const DEFAULT_EVENT_COLOR = 'default';
const EVENT_COLOR_OPTIONS = COLOR_PALETTE;

const SERVICE_APP_TAG_SELECTORS = [
    'flows-app',
    'crm-app',
    'frontend-app',
    'rag-app',
    'sync-app',
    'office-app',
    'litserve-app',
];

/**
 * Публичные URL календаря вида /{сервис}/api/calendar (см. core/app/factory.py).
 * Модалка при открытии может портироваться в body, поэтому ищем корневой *-app в document.
 */
function serviceBaseUrlForCalendar(): string {
    for (const sel of SERVICE_APP_TAG_SELECTORS) {
        const el = document.querySelector(sel);
        if (el !== null && el.isConnected && 'getBaseUrl' in el && typeof el.getBaseUrl === 'function') {
            const base = el.getBaseUrl();
            if (typeof base === 'string' && base.length > 0) {
                return base;
            }
        }
    }
    throw new Error('platform-calendar-modal: root service app (getBaseUrl) not found');
}

function formControlValue(event: Event): string {
    const target = event.target;
    if (
        !(target instanceof HTMLInputElement)
        && !(target instanceof HTMLTextAreaElement)
        && !(target instanceof HTMLSelectElement)
    ) {
        throw new Error('platform-calendar-modal: form control required');
    }
    return target.value;
}

function customEventValue(event: Event): unknown {
    if (!(event instanceof CustomEvent)) {
        throw new Error('platform-calendar-modal: custom event required');
    }
    if (!isPlainRecord(event.detail) || !('value' in event.detail)) {
        throw new Error('platform-calendar-modal: detail.value required');
    }
    return event.detail.value;
}

function pointerTarget(event: PointerEvent): HTMLElement {
    const target = event.currentTarget;
    if (!(target instanceof HTMLElement)) {
        throw new Error('platform-calendar-modal: pointer target required');
    }
    return target;
}

function pointerListener(handler: (event: PointerEvent) => void): EventListener {
    return (event: Event) => {
        if (!(event instanceof PointerEvent)) {
            throw new Error('platform-calendar-modal: pointer event required');
        }
        handler(event);
    };
}

function integrationSettings(settings: unknown): Record<string, unknown> {
    return isPlainRecord(settings) ? settings : {};
}

function calendarIdLabel(settings: unknown, emptyLabel: string): string {
    const calendarId = integrationSettings(settings).default_calendar_id;
    if (typeof calendarId !== 'string' || calendarId.length === 0) {
        return emptyLabel;
    }
    return calendarId;
}

function pad2(value: unknown): string {
    return String(value).padStart(2, '0');
}

function toDateInputValue(date: Date): string {
    return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

/**
 * Строка YYYY-MM-DD из состояния календаря — это календарный день в локальной зоне,
 * а new Date('YYYY-MM-DD') в движке — полночь UTC, из‑за чего сетка дня и фильтр событий
 * расходятся с подписью периода (особенно при отрицательном смещении от UTC).
 */
function parseDateInputLocal(isoDate: string): Date {
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

function toDateTimeInputValue(date: Date): string {
    return `${toDateInputValue(date)}T${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function addDays(date: Date, amount: number): Date {
    const copy = new Date(date.getTime());
    copy.setDate(copy.getDate() + amount);
    return copy;
}

function startOfWeek(date: Date): Date {
    const copy = new Date(date.getTime());
    const day = copy.getDay();
    const shift = day === 0 ? 6 : day - 1;
    copy.setDate(copy.getDate() - shift);
    copy.setHours(0, 0, 0, 0);
    return copy;
}

function endOfWeek(date: Date): Date {
    const start = startOfWeek(date);
    return addDays(start, 7);
}

function startOfMonth(date: Date): Date {
    const copy = new Date(date.getFullYear(), date.getMonth(), 1, 0, 0, 0, 0);
    return copy;
}

function endOfMonth(date: Date): Date {
    return new Date(date.getFullYear(), date.getMonth() + 1, 1, 0, 0, 0, 0);
}

function isSameDay(left: Date, right: Date): boolean {
    return left.getFullYear() === right.getFullYear()
        && left.getMonth() === right.getMonth()
        && left.getDate() === right.getDate();
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function textOrEmpty(value: unknown): string {
    return typeof value === 'string' ? value : '';
}

function missingAsNull<T>(value: T | null | undefined): T | null {
    return value === undefined ? null : value;
}

function blankToNull(value: string): string | null {
    const trimmed = value.trim();
    return trimmed.length === 0 ? null : trimmed;
}

function normalizeEmail(value: unknown): string {
    return textOrEmpty(value).trim().toLowerCase();
}

interface AttendeeTag {
    attendee_id: string;
    email: string;
    display_name: string;
    response_status: string;
}

function toAttendeeTag(entry: { email?: unknown; display_name?: unknown; attendee_id?: unknown }): AttendeeTag {
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

function recurrenceToRule(value: string): string | null {
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

interface EventAttachment {
    file_id: string;
    name: string;
    url: string;
    content_type: string;
    file_size: number;
}

function parseEventAttachments(metadata: { attachments?: unknown } | null | undefined): EventAttachment[] {
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
    return parsed.map((item: unknown) => {
        if (!isPlainRecord(item)) {
            throw new Error('Attachment item must be an object');
        }
        const record = item;
        if (typeof record.file_id !== 'string' || record.file_id === '') {
            throw new Error('Attachment file_id is required');
        }
        if (typeof record.name !== 'string' || record.name === '') {
            throw new Error('Attachment name is required');
        }
        if (typeof record.url !== 'string' || record.url === '') {
            throw new Error('Attachment url is required');
        }
        return {
            file_id: record.file_id,
            name: record.name,
            url: record.url,
            content_type: typeof record.content_type === 'string' ? record.content_type : '',
            file_size: typeof record.file_size === 'number' && Number.isFinite(record.file_size) ? record.file_size : 0,
        };
    });
}

function buildEventMetadata(baseMetadata: Record<string, unknown> | null | undefined, attachments: EventAttachment[]): Record<string, string> {
    const nextMetadata: Record<string, string> = {};
    const metadata = baseMetadata === undefined || baseMetadata === null ? {} : baseMetadata;
    for (const [key, value] of Object.entries(metadata)) {
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

function isKnownEventColor(colorKey: string): boolean {
    return EVENT_COLOR_OPTIONS.some((color) => color.key === colorKey);
}

function normalizeEventColor(colorKey: string | null | undefined): string {
    if (!colorKey) {
        return DEFAULT_EVENT_COLOR;
    }
    if (isKnownEventColor(colorKey)) {
        return colorKey;
    }
    return DEFAULT_EVENT_COLOR;
}

function eventMetadataHasSyncMeeting(metadata: { sync_meeting?: unknown; sync_link_token?: unknown } | null | undefined): boolean {
    if (!metadata || typeof metadata !== 'object') {
        return false;
    }
    return metadata.sync_meeting === '1' || Boolean(metadata.sync_link_token);
}

const SYNC_LOGO_SRC = '/static/core/assets/service_logos/sync_logo.svg';
const CALENDAR_VIEW_STORAGE_KEY = platformStorageKey('core', 'calendar_view');
const VALID_VIEWS = ['day', 'week', 'month'];

function isStoredCalendarEvent(event: CalendarState['events'][number]): event is CalendarEventRecord {
    return typeof event.event_id === 'string' && event.event_id.length > 0
        && typeof event.start_at === 'string'
        && typeof event.end_at === 'string';
}

function requireCalendarEvents(events: CalendarState['events']): CalendarEventRecord[] {
    const stored: CalendarEventRecord[] = [];
    for (const event of events) {
        if (!isStoredCalendarEvent(event)) {
            throw new Error('calendar modal: event requires event_id, start_at and end_at');
        }
        stored.push(event);
    }
    return stored;
}

interface CalendarEventRecord {
    event_id: string;
    title?: string;
    description?: string;
    location?: string;
    timezone?: string;
    all_day?: boolean;
    start_at: string;
    end_at: string;
    kind?: string;
    source?: string;
    source_id?: string;
    series_id?: string;
    recurrence_id?: string;
    recurrence_rule?: string | null;
    attendees?: AttendeeTag[];
    metadata?: Record<string, string>;
    deep_link?: string;
    namespace?: string;
    status?: string;
    mailbox_binding_id?: string;
    target?: unknown;
    key?: string;
    [key: string]: unknown;
}

interface EventFormState {
    kind: string;
    color: string;
    title: string;
    description: string;
    location: string;
    timezone: string;
    all_day: boolean;
    start_at: string;
    end_at: string;
    attendees: AttendeeTag[];
    recurrence: string;
    [key: string]: unknown;
}

interface IntegrationFormState {
    username: string;
    app_password: string;
    default_calendar_id: string;
    caldav_base_url: string;
    sync_enabled: boolean;
    sync_inbound_enabled: boolean;
    sync_outbound_enabled: boolean;
    notifications_enabled: boolean;
    [key: string]: unknown;
}

export class PlatformCalendarModal extends PlatformModal {
    static modalKind = 'platform.calendar';
    static i18nNamespace = 'calendar';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        _view: { state: true },
        _anchorDate: { state: true },
        _saving: { state: true },
        _syncing: { state: true },
        _selectedEventId: { state: true },
        _activeProvider: { state: true },
        _activeIntegrationId: { state: true },
        _integrationsMenuOpen: { state: true },
        _integrationModalProvider: { state: true },
        _eventDialogOpen: { state: true },
        _showDescriptionField: { state: true },
        _uploadingAttachments: { state: true },
        _eventAttachments: { state: true },
        _eventMetadata: { state: true },
        _selectedEventSource: { state: true },
        _selectedEventKind: { state: true },
        _selectedEventNamespace: { state: true },
        _attendeeDraft: { state: true },
        _attendeeDropdownOpen: { state: true },
        _eventForm: { state: true },
        _integrationForm: { state: true },
        _isCompactLayout: { state: true },
        _dateSheetOpen: { state: true },
        _dateSheetMonthRef: { state: true },
        _eventDeepLink: { state: true },
        _dragEvent: { state: true },
        _dragGhostTop: { state: true },
        _dragGhostLeft: { state: true },
        _pendingAttachmentUploads: { state: true },
    };
    declare _view: 'day' | 'week' | 'month';
    declare _anchorDate: string;
    declare _saving: boolean;
    declare _syncing: boolean;
    declare _selectedEventId: string | null;
    declare _activeProvider: string;
    declare _activeIntegrationId: string | null;
    declare _integrationsMenuOpen: boolean;
    declare _integrationModalProvider: string | null;
    declare _eventDialogOpen: boolean;
    declare _showDescriptionField: boolean;
    declare _uploadingAttachments: boolean;
    declare _eventAttachments: EventAttachment[];
    declare _eventMetadata: Record<string, string>;
    declare _selectedEventSource: string;
    declare _selectedEventKind: string;
    declare _selectedEventNamespace: string | null;
    declare _attendeeDraft: string;
    declare _attendeeDropdownOpen: boolean;
    declare _eventForm: EventFormState;
    declare _integrationForm: IntegrationFormState;
    declare _isCompactLayout: boolean;
    declare _dateSheetOpen: boolean;
    declare _dateSheetMonthRef: string;
    declare _eventDeepLink: string | null;
    declare _dragEvent: CalendarEventRecord | null;
    declare _dragGhostTop: number;
    declare _dragGhostLeft: number;
    declare _pendingAttachmentUploads: Map<string, { name: string }>;
    _dragOrigin: { x: number; y: number; started: boolean } | null = null;
    _dragPointerId: number | null = null;
    _dragJustFinished = false;
    private _dragSessionUnsubs: Array<() => void> = [];
    _onDragMoveBound: EventListener;
    _onDragUpBound: EventListener;
    _onDocumentClickBound: ((event: Event) => void) | null = null;
    _eventsSelect: SelectController<CalendarEventRecord[]>;
    _integrationsSelect: SelectController<CalendarState['integrations']>;
    _calendarLoadingSelect: SelectController<boolean>;
    _calendarSyncingSelect: SelectController<boolean>;
    _teamMembersSelect: SelectController<TeamMemberRecord[]>;
    _localeSelect: SelectController<string>;
    _mailSelect: SelectController<MailState>;
    _resizeObserver: ResizeObserver | null = null;

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
        formStyles,
        buttonStyles,
        css`
            :host {
                --calendar-sidebar-width: 420px;
                --calendar-grid-columns: 7;
                --calendar-toolbar-control-size: 34px;
            }

            :host([open]) .modal-overlay {
                padding: 0 !important;
                inset: 0 !important;
            }

            :host([open]) .modal,
            :host([open]) .modal.full,
            :host([open]) .modal.fullscreen {
                position: fixed !important;
                inset: 0 !important;
                left: 0 !important;
                top: 0 !important;
                width: 100vw !important;
                max-width: 100vw !important;
                height: 100dvh !important;
                max-height: 100dvh !important;
                min-height: 100dvh !important;
                border-radius: 0 !important;
                margin: 0 !important;
                transform: none !important;
                transform-origin: center center;
                --modal-content-inset: 0;
                --modal-content-radius: 0;
            }

            @keyframes calendarModalIn {
                from {
                    opacity: 0;
                    transform: translateY(12px) scale(0.985);
                }
                to {
                    opacity: 1;
                    transform: none;
                }
            }

            :host([open]) .modal.panel-enter-active {
                animation: calendarModalIn 320ms var(--easing-smooth, cubic-bezier(0.22, 1, 0.36, 1)) both;
            }

            :host([open]:not([closing])) .modal.panel-enter-active,
            :host([open]:not([closing])) .modal:not(.panel-enter-active) {
                opacity: 1;
                transform: none !important;
            }

            /* Chrome как у platform.mail: без platform-header, контент edge-to-edge. */
            :host([open]) .modal .modal-content,
            :host([open]) .modal.full .modal-content,
            :host([open]) .modal.fullscreen .modal-content {
                margin: 0 !important;
                border-radius: 0 !important;
                padding: 0 !important;
                overflow: hidden;
                display: flex;
                flex-direction: column;
                min-height: 0;
                height: 100%;
            }

            :host([open]) .modal .modal-header,
            :host([open]) .modal.fullscreen .modal-header {
                display: none !important;
            }

            :host([open]) .modal .modal-actions,
            :host([open]) .modal.fullscreen .modal-actions {
                display: none !important;
            }

            @media (max-width: 768px) {
                :host([open]) .modal,
                :host([open]) .modal.full,
                :host([open]) .modal.fullscreen {
                    width: 100vw !important;
                    max-width: 100vw !important;
                    height: 100dvh !important;
                    max-height: 100dvh !important;
                    border-radius: 0 !important;
                }
            }

            .calendar-shell-wrap {
                position: relative;
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                background: var(--bg-primary);
                color: var(--text-primary);
            }

            .calendar-shell {
                display: grid;
                grid-template-columns: var(--mail-rail-width, 64px) minmax(0, 1fr);
                gap: 0;
                min-height: 0;
                flex: 1;
                background: var(--bg-primary);
            }
            platform-mail-calendar-rail {
                min-height: 0;
            }

            .calendar-sidebar {
                border-right: 1px solid var(--border-subtle);
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
                gap: 0;
                background: var(--bg-primary);
            }

            .toolbar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-3) var(--space-5);
                border-bottom: 1px solid var(--border-subtle);
                background: var(--bg-surface);
                flex-shrink: 0;
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
                box-sizing: border-box;
                width: var(--calendar-toolbar-control-size);
                height: var(--calendar-toolbar-control-size);
                min-width: var(--calendar-toolbar-control-size);
                min-height: var(--calendar-toolbar-control-size);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }

            .btn-icon:hover {
                border-color: var(--accent);
                color: var(--text-primary);
            }

            .view-segment {
                box-sizing: border-box;
                display: inline-flex;
                align-items: stretch;
                height: var(--calendar-toolbar-control-size);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                overflow: hidden;
                flex-shrink: 0;
            }

            .view-segment button {
                box-sizing: border-box;
                border: none;
                border-right: 1px solid var(--glass-border-subtle);
                background: transparent;
                color: var(--text-secondary);
                margin: 0;
                padding: 0 12px;
                height: 100%;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-size: var(--text-sm);
                line-height: 1;
                font-weight: var(--font-medium);
                cursor: pointer;
            }

            .view-segment button:last-child {
                border-right: none;
            }

            .view-segment button.active {
                background: var(--accent-subtle);
                color: var(--accent);
            }

            .calendar-panel {
                border: none;
                border-radius: 0;
                background: var(--bg-primary);
                min-height: 0;
                flex: 1;
                overflow: auto;
                padding: var(--space-3) var(--space-4);
            }

            .calendar-panel--day {
                border: none;
                background: transparent;
                padding: var(--space-2) var(--space-3);
                overflow: visible;
            }

            .btn-calendar-create {
                box-sizing: border-box;
                width: var(--calendar-toolbar-control-size);
                height: var(--calendar-toolbar-control-size);
                min-width: var(--calendar-toolbar-control-size);
                min-height: var(--calendar-toolbar-control-size);
                padding: 0;
                border-radius: 50%;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                line-height: 1;
                font-weight: var(--font-semibold);
                flex-shrink: 0;
            }

            .btn.btn-primary.btn-calendar-create {
                padding: 0;
                background: var(--accent);
                color: #fff;
            }

            .btn.btn-primary.btn-calendar-create:hover {
                background: color-mix(in srgb, var(--accent) 85%, #000);
            }

            .calendar-fab {
                display: none;
            }

            .toolbar--compact {
                gap: var(--space-2);
            }

            .toolbar--compact .toolbar-left {
                flex: 1 1 auto;
                justify-content: center;
                align-items: center;
                gap: var(--space-2);
                padding-left: max(var(--space-2), calc(env(safe-area-inset-left, 0px) + 10px));
                box-sizing: border-box;
            }

            .toolbar--compact .toolbar-left .btn-icon {
                touch-action: manipulation;
                flex-shrink: 0;
            }

            .toolbar--compact .toolbar-right {
                flex: 0 0 auto;
                align-items: center;
                padding-right: max(var(--space-2), env(safe-area-inset-right, 0px));
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
                border-color: #99A6F9;
                background: color-mix(in srgb, #99A6F9 12%, transparent);
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
                padding: 4px 8px;
                text-align: left;
                cursor: pointer;
                font-size: var(--text-xs);
                line-height: 1.3;
                overflow: hidden;
                display: flex;
                flex-direction: row;
                flex-wrap: wrap;
                align-items: baseline;
                gap: 0 4px;
                box-sizing: border-box;
                transition: top 0.2s ease, height 0.2s ease;
            }

            .day-event-block .event-chip-title {
                display: inline;
                -webkit-line-clamp: unset;
                -webkit-box-orient: unset;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                flex: 1 1 0;
                min-width: 0;
            }

            .day-event-block .event-chip-time {
                flex-shrink: 0;
                white-space: nowrap;
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

            .day-empty-hint {
                position: absolute;
                left: 8px;
                right: 8px;
                top: 12px;
                z-index: 1;
                text-align: center;
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                pointer-events: none;
            }

            :host([open]) .modal .modal-header--calendar-compact {
                display: flex;
                flex-wrap: nowrap;
                align-items: center;
                gap: 6px;
            }

            :host([open]) .modal .modal-header--calendar-compact .calendar-modal-title {
                flex: 0 1 auto;
                min-width: 0;
                font-size: var(--text-base, 16px);
            }

            :host([open]) .modal .modal-header--calendar-compact .calendar-header-date-nav {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 4px;
                flex: 1 1 auto;
                min-width: 0;
            }

            :host([open]) .modal .modal-header--calendar-compact .calendar-header-date-nav .period-date-btn {
                max-width: min(160px, 46vw);
                padding: 6px 10px;
                font-size: var(--text-xs, 12px);
            }

            :host([open]) .modal .modal-header--calendar-compact .calendar-header-date-nav .btn-icon {
                width: 30px;
                height: 30px;
                min-width: 30px;
                min-height: 30px;
            }

            :host([open]) .modal .modal-header--calendar-compact .header-buttons {
                flex: 0 0 auto;
                margin-left: auto;
            }

            .week-grid {
                display: flex;
                flex-direction: column;
                min-height: 0;
            }

            .week-header {
                display: grid;
                grid-template-columns: 44px repeat(7, minmax(0, 1fr));
                border-bottom: 1px solid var(--glass-border-subtle);
                position: sticky;
                top: 0;
                z-index: 1;
                background: var(--glass-solid-subtle);
            }

            .week-time-spacer {
                width: 44px;
            }

            .week-day-header {
                text-align: center;
                padding: var(--space-1) 0;
                font-size: var(--text-xs);
                color: var(--text-secondary);
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 2px;
            }

            .week-day-header.today {
                font-weight: var(--font-semibold);
                background: color-mix(in srgb, #99A6F9 5%, transparent);
            }

            .week-day-header.today .week-day-number {
                color: #fff;
                background: #99A6F9;
                border-radius: 999px;
                width: 24px;
                height: 24px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            .week-day-header.weekend {
                color: var(--text-tertiary);
            }

            .week-day-number {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
            }

            .week-body-scroll {
                overflow: auto;
                max-height: min(62dvh, 560px);
                min-height: 280px;
            }

            .week-body {
                display: grid;
                grid-template-columns: 44px repeat(7, minmax(0, 1fr));
                --week-hour-height: 48px;
            }

            .week-time-col {
                display: flex;
                flex-direction: column;
                width: 44px;
                flex-shrink: 0;
            }

            .week-time-label {
                height: var(--week-hour-height);
                font-size: 10px;
                color: var(--text-tertiary);
                padding-right: 4px;
                text-align: right;
                box-sizing: border-box;
            }

            .week-day-col {
                position: relative;
                border-left: 1px solid var(--glass-border-subtle);
                min-width: 0;
            }

            .week-day-col.weekend {
                background: rgba(34, 34, 34, 0.03);
            }

            .week-day-col.today {
                background: color-mix(in srgb, #99A6F9 5%, transparent);
            }

            .week-day-lines {
                display: flex;
                flex-direction: column;
            }

            .week-hour-slot {
                height: var(--week-hour-height);
                border-bottom: 1px solid var(--glass-border-subtle);
                box-sizing: border-box;
            }

            .week-day-events {
                position: absolute;
                left: 0;
                right: 0;
                top: 0;
                height: calc(24 * var(--week-hour-height));
                pointer-events: none;
            }

            .week-day-events .day-event-block {
                pointer-events: auto;
                left: 2px;
                right: 2px;
                font-size: 10px;
            }

            .week-all-day-row {
                display: grid;
                grid-template-columns: 44px repeat(7, minmax(0, 1fr));
                border-bottom: 1px solid var(--glass-border-subtle);
                padding: var(--space-1) 0;
                gap: 2px;
            }

            .week-all-day-cell {
                display: flex;
                flex-wrap: wrap;
                gap: 2px;
                padding: 0 2px;
                min-width: 0;
            }

            .week-all-day-cell .event-chip {
                font-size: 10px;
                padding: 3px 6px;
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
                color: var(--text-tertiary);
            }

            .month-cell {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                min-height: 114px;
                max-height: 180px;
                padding: var(--space-1) 6px;
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                background: var(--glass-solid-medium);
                overflow: hidden;
            }

            .month-cell.outside {
                opacity: 0.55;
            }

            .month-cell.weekend {
                background: color-mix(in srgb, rgba(34, 34, 34, 0.05) 100%, var(--glass-solid-medium));
            }

            .month-cell.today {
                border-color: color-mix(in srgb, #99A6F9 35%, var(--glass-border-subtle));
                background: color-mix(in srgb, #99A6F9 6%, var(--glass-solid-medium));
            }

            .month-cell .date-label {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                font-weight: var(--font-semibold);
            }

            .month-cell.today .date-label {
                color: #fff;
                background: #99A6F9;
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
                display: flex;
                flex-direction: column;
                gap: 4px;
                overflow-y: auto;
                scrollbar-width: thin;
            }


            .event-chip {
                font-size: var(--text-xs);
                line-height: 1.3;
                background: color-mix(in srgb, #a2affb 24%, var(--glass-solid-medium));
                border: none;
                color: #4f5eb6;
                border-radius: var(--radius-sm);
                padding: 8px 10px 8px 12px;
                cursor: pointer;
                text-align: left;
                display: grid;
                gap: 6px;
                min-width: 0;
                flex-shrink: 0;
                align-content: start;
                position: relative;
            }

            .event-chip::before {
                content: '';
                position: absolute;
                left: 0;
                top: 4px;
                bottom: 4px;
                width: 3px;
                border-radius: 2px;
                background: var(--mailbox-ribbon, transparent);
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
                gap: 4px;
                min-width: 0;
                overflow-x: auto;
                overflow-y: hidden;
                scrollbar-width: none;
                -ms-overflow-style: none;
                flex-shrink: 0;
            }

            .event-chip-top::-webkit-scrollbar {
                display: none;
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
                flex-shrink: 0;
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

            .drag-ghost {
                position: fixed;
                pointer-events: none;
                z-index: calc(var(--platform-modal-layer-z, var(--z-modal, 1000)) + 10);
                opacity: 0.85;
                border-radius: var(--radius-md);
                padding: 6px 10px;
                font-size: var(--text-xs);
                line-height: 1.3;
                color: #fff;
                background: #99A6F9;
                box-shadow: 0 6px 18px rgba(0, 0, 0, 0.18);
                max-width: 200px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                transform: translate(-50%, -50%);
            }

            .month-cell.drag-over {
                outline: 2px solid #99A6F9;
                outline-offset: -2px;
                background: color-mix(in srgb, #99A6F9 10%, var(--glass-solid-medium));
            }

            .week-day-col.drag-over,
            .day-tracks.drag-over {
                background: color-mix(in srgb, #99A6F9 8%, transparent);
            }

            .event-chip[data-dragging] {
                opacity: 0.35;
                transition: opacity 0.15s ease;
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

            .integrations-menu-anchor {
                position: relative;
            }

            .integrations-dropdown {
                position: absolute;
                right: 0;
                top: calc(100% + 4px);
                z-index: 10;
                min-width: 200px;
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-md);
                background: var(--glass-solid-strong);
                box-shadow: var(--glass-shadow-medium);
                padding: var(--space-1);
                display: grid;
                gap: 2px;
            }

            .dropdown-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 8px 12px;
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                cursor: pointer;
                border-radius: var(--radius-sm);
                text-align: left;
                width: 100%;
            }

            .dropdown-item:hover {
                background: var(--glass-tint-medium);
            }

            .integration-modal-overlay {
                position: fixed;
                inset: 0;
                background: rgba(0, 0, 0, 0.22);
                backdrop-filter: blur(4px);
                -webkit-backdrop-filter: blur(4px);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: calc(var(--platform-modal-layer-z, var(--z-modal, 1000)) + 3);
                padding: var(--space-4);
            }

            .integration-modal {
                width: min(520px, 96vw);
                max-height: min(80vh, 80dvh);
                overflow: auto;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-strong);
                box-shadow: var(--glass-shadow-medium), 0 14px 34px rgba(0, 0, 0, 0.16);
                padding: var(--space-4);
                display: grid;
                gap: var(--space-3);
            }

            .integration-modal-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }

            .integration-modal-title {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
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
                border: 0;
                background: transparent;
                padding: 0;
                color: var(--text-primary);
                font-size: var(--text-sm);
                text-decoration: none;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                max-width: 220px;
                cursor: pointer;
                font-family: inherit;
                text-align: left;
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

            .event-compose-tz {
                flex: 1 1 220px;
                min-width: 160px;
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
                    grid-template-columns: var(--mail-rail-width, 64px) minmax(0, 1fr);
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
        const savedView = storageGet(CALENDAR_VIEW_STORAGE_KEY);
        this._view = savedView === 'day' || savedView === 'week' || savedView === 'month' ? savedView : 'month';
        this._anchorDate = toDateInputValue(new Date());
        this._saving = false;
        this._syncing = false;
        this._selectedEventId = null;
        this._activeProvider = 'google';
        this._activeIntegrationId = null;
        this._integrationsMenuOpen = false;
        this._integrationModalProvider = null;
        this._eventDialogOpen = false;
        this._showDescriptionField = false;
        this._uploadingAttachments = false;
        this._eventAttachments = [];
        this._eventMetadata = {};
        this._selectedEventSource = 'platform';
        this._selectedEventKind = 'meeting';
        this._selectedEventNamespace = null;
        this._attendeeDraft = '';
        this._attendeeDropdownOpen = false;
        this._pendingAttachmentUploads = new Map();
        this._eventsSelect = this.select((s) => requireCalendarEvents(s.calendar.events));
        this._integrationsSelect = this.select((s) => s.calendar.integrations);
        this._calendarLoadingSelect = this.select((s) => s.calendar.loading);
        this._calendarSyncingSelect = this.select((s) => s.calendar.syncing);
        this._teamMembersSelect = this.select((s) => s.team.members);
        this._localeSelect = this.select((s) => s.i18n.locale);
        this._mailSelect = this.select((s) => s.mail);
        const currentTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
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
            caldav_base_url: '',
            sync_enabled: true,
            sync_inbound_enabled: true,
            sync_outbound_enabled: true,
            notifications_enabled: true,
        };
        this._isCompactLayout = false;
        this._dateSheetOpen = false;
        const sheetMonth = new Date();
        this._dateSheetMonthRef = toDateInputValue(new Date(sheetMonth.getFullYear(), sheetMonth.getMonth(), 1));
        this._dragEvent = null;
        this._dragGhostTop = 0;
        this._dragGhostLeft = 0;
        this._dragOrigin = null;
        this._dragPointerId = null;
        this._onDragMoveBound = pointerListener((event) => this._onDragMove(event));
        this._onDragUpBound = pointerListener((event) => this._onDragUp(event));
        this._dragJustFinished = false;
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        this.title = this.t('title');
        if (changed.has('open')) {
            if (this.open) {
                this._onModalOpened();
            } else {
                this._onModalClosed();
            }
        }
    }

    _onModalOpened() {
        this._dateSheetOpen = false;
        this._integrationsMenuOpen = false;
        this._integrationModalProvider = null;
        this._activeIntegrationId = null;
        this._isCompactLayout = window.matchMedia('(max-width: 767px)').matches;
        if (this._isCompactLayout) {
            this._view = 'day';
        }
        this.size = 'full';
        this._isFullscreen = true;
        if (!this._onDocumentClickBound) {
            this._onDocumentClickBound = (e: Event) => {
                if (!this._integrationsMenuOpen) {
                    return;
                }
                const anchor = this.renderRoot?.querySelector('.integrations-menu-anchor');
                const pathTarget = e.composedPath()[0];
                if (anchor && pathTarget instanceof Node && !anchor.contains(pathTarget)) {
                    this._integrationsMenuOpen = false;
                }
            };
        }
        this.useDomEvent(document, 'click', this._onDocumentClickBound);
        this._kickInitialLoad();
    }

    _onModalClosed() {
        this._dateSheetOpen = false;
        this._integrationsMenuOpen = false;
        this._integrationModalProvider = null;
        this._activeIntegrationId = null;
        this._eventDialogOpen = false;
    }

    _calT(key: string, params: Record<string, string | number> = {}): string {
        return this.t(key, params);
    }

    _calendarLocaleTag() {
        return this._localeSelect.value === 'ru' ? 'ru-RU' : 'en-US';
    }

    _kickInitialLoad() {
        const range = this._viewRange();
        this.dispatch(TEAM_EVENTS.MEMBERS_LOAD_REQUESTED, null);
        const bindings = this._mailSelect.value.bindings;
        if (!Array.isArray(bindings) || bindings.length === 0) {
            this.dispatch(MAIL_EVENTS.BINDINGS_LOAD_REQUESTED, null);
        }
        this.dispatch(CALENDAR_EVENTS.INTEGRATIONS_LOAD_REQUESTED, null);
        this.dispatch(CALENDAR_EVENTS.EVENTS_LOAD_REQUESTED, {
            start_at: range.start.toISOString(),
            end_at: range.end.toISOString(),
            include_sources: null,
            limit: 2000,
        });
        if (this._view === 'day' || this._view === 'week') {
            this._scrollToWorkZone();
        }
    }

    _mailboxRibbonStyle(event: CalendarEventRecord) {
        const mailboxBindingId = event && event.mailbox_binding_id;
        if (typeof mailboxBindingId !== 'string' || mailboxBindingId.length === 0) {
            return nothing;
        }
        const bindings = this._mailSelect.value.bindings;
        const binding = Array.isArray(bindings)
            ? bindings.find((item) => item.mailbox_binding_id === mailboxBindingId)
            : null;
        if (!binding || typeof binding.calendar_color !== 'string') {
            return nothing;
        }
        const color = resolvePaletteColor(binding.calendar_color);
        return `--mailbox-ribbon: ${color}`;
    }

    _openCalendarRailSettings() {
        this._integrationsMenuOpen = true;
    }

    _reload() {
        const range = this._viewRange();
        this.dispatch(CALENDAR_EVENTS.EVENTS_LOAD_REQUESTED, {
            start_at: range.start.toISOString(),
            end_at: range.end.toISOString(),
            include_sources: null,
            limit: 2000,
        });
        if (this._view === 'day' || this._view === 'week') {
            this._scrollToWorkZone();
        }
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.useEvent(CALENDAR_EVENTS.EVENTS_LOAD_FAILED, (e) => {
            this.toast('err_load_events', { type: 'error', vars: { message: calendarFailureMessage(e) } });
        });
        this.useEvent(CALENDAR_EVENTS.EVENT_CREATE_FAILED, (e) => {
            this._saving = false;
            this.toast('err_save_event', { type: 'error', vars: { message: calendarFailureMessage(e) } });
        });
        this.useEvent(CALENDAR_EVENTS.EVENT_UPDATE_FAILED, (e) => {
            this._saving = false;
            this.toast('err_save_event', { type: 'error', vars: { message: calendarFailureMessage(e) } });
        });
        this.useEvent(CALENDAR_EVENTS.EVENT_DELETE_FAILED, (e) => {
            this.toast('err_delete_event', { type: 'error', vars: { message: calendarFailureMessage(e) } });
        });
        this.useEvent(CALENDAR_EVENTS.INTEGRATIONS_LOAD_FAILED, (e) => {
            this.toast('err_load_integrations', { type: 'error', vars: { message: calendarFailureMessage(e) } });
        });
        this.useEvent(CALENDAR_EVENTS.INTEGRATION_CONNECT_FAILED, (e) => {
            this._saving = false;
            this.toast('err_connect_integration', { type: 'error', vars: { message: calendarFailureMessage(e) } });
        });
        this.useEvent(CALENDAR_EVENTS.INTEGRATION_DISCONNECT_FAILED, (e) => {
            this.toast('err_disconnect_integration', { type: 'error', vars: { message: calendarFailureMessage(e) } });
        });
        this.useEvent(CALENDAR_EVENTS.SYNC_FAILED, (e) => {
            this._syncing = false;
            this.toast('err_sync', { type: 'error', vars: { message: calendarFailureMessage(e) } });
        });
        this.useEvent(TEAM_EVENTS.MEMBERS_LOAD_FAILED, (e) => {
            this.toast('err_load_team', { type: 'error', vars: { message: calendarFailureMessage(e) } });
        });
        this.useEvent(CALENDAR_EVENTS.EVENT_CREATED, () => {
            this._saving = false;
            this._resetEventFormAfterSave();
        });
        this.useEvent(CALENDAR_EVENTS.EVENT_UPDATED, () => {
            this._saving = false;
            this._resetEventFormAfterSave();
        });
        this.useEvent(CALENDAR_EVENTS.EVENT_DELETED, () => this._resetEventFormAfterSave());
        this.useEvent(CALENDAR_EVENTS.SYNC_COMPLETED, () => { this._syncing = false; });
        this.useEvent(CALENDAR_EVENTS.INTEGRATION_CONNECTED, () => { this._saving = false; });
        this.useEvent(FILES_EVENTS.UPLOAD_COMPLETED, (e: PlatformEvent) => this._onFileUploadCompleted(e));
        this.useEvent(FILES_EVENTS.UPLOAD_FAILED, (e: PlatformEvent) => this._onFileUploadFailed(e));
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
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

    async _movePeriod(delta: number): Promise<void> {
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

    _onViewChange(view: 'day' | 'week' | 'month'): void {
        this._view = view;
        storageSet(CALENDAR_VIEW_STORAGE_KEY, view);
        this._reload();
    }

    async _scrollToWorkZone() {
        await this.updateComplete;
        const selector = this._view === 'day' ? '.day-timeline-scroll' : '.week-body-scroll';
        const container = this.renderRoot?.querySelector(selector);
        if (!container) {
            return;
        }
        const hourPx = this._view === 'day' ? 52 : 48;
        const anchor = parseDateInputLocal(this._anchorDate);
        const events = this._eventsForDate(anchor);
        const now = new Date();

        let targetHour = 8;

        if (isSameDay(now, anchor)) {
            targetHour = Math.max(0, now.getHours() - 1);
        } else {
            const timedEvents = events.filter((e) => !e.all_day);
            if (timedEvents.length > 0) {
                const earliestHour = Math.min(
                    ...timedEvents.map((e) => new Date(e.start_at).getHours()),
                );
                targetHour = Math.max(0, earliestHour - 1);
            }
        }

        container.scrollTop = targetHour * hourPx;
    }

    _onDragStart(event: CalendarEventRecord, pointerEvent: PointerEvent): void {
        pointerEvent.preventDefault();
        pointerEvent.stopPropagation();
        const target = pointerTarget(pointerEvent);
        target.setPointerCapture(pointerEvent.pointerId);
        this._dragPointerId = pointerEvent.pointerId;
        this._dragOrigin = { x: pointerEvent.clientX, y: pointerEvent.clientY, started: false };
        this._dragEvent = event;
        this._dragSessionUnsubs = [
            this.useDomEvent(target, 'pointermove', this._onDragMoveBound),
            this.useDomEvent(target, 'pointerup', this._onDragUpBound),
            this.useDomEvent(target, 'pointercancel', this._onDragUpBound),
        ];
    }

    _onDragMove(pointerEvent: PointerEvent): void {
        if (!this._dragEvent) {
            return;
        }
        const origin = this._dragOrigin;
        if (!origin) {
            return;
        }
        const dx = pointerEvent.clientX - origin.x;
        const dy = pointerEvent.clientY - origin.y;
        if (!origin.started && Math.abs(dx) + Math.abs(dy) < 8) {
            return;
        }
        origin.started = true;
        this._dragGhostTop = pointerEvent.clientY;
        this._dragGhostLeft = pointerEvent.clientX;
        this._updateDropTarget(pointerEvent.clientX, pointerEvent.clientY);
    }

    _onDragUp(pointerEvent: PointerEvent): void {
        const target = pointerTarget(pointerEvent);
        for (const unsub of this._dragSessionUnsubs) {
            unsub();
        }
        this._dragSessionUnsubs = [];
        if (this._dragPointerId !== null) {
            target.releasePointerCapture(this._dragPointerId);
            this._dragPointerId = null;
        }
        const wasDragging = this._dragOrigin?.started;
        if (!wasDragging || !this._dragEvent) {
            this._dragEvent = null;
            this._dragOrigin = null;
            this._clearDropTargets();
            return;
        }
        this._dragJustFinished = true;
        setTimeout(() => { this._dragJustFinished = false; }, 100);
        const dropTarget = this._findDropTarget(pointerEvent.clientX, pointerEvent.clientY);
        if (dropTarget) {
            this._applyDrop(this._dragEvent, dropTarget);
        }
        this._dragEvent = null;
        this._dragOrigin = null;
        this._clearDropTargets();
    }

    _updateDropTarget(clientX: number, clientY: number): void {
        this._clearDropTargets();
        const el = this._findDropElement(clientX, clientY);
        if (el) {
            el.classList.add('drag-over');
        }
    }

    _clearDropTargets() {
        const root = this.renderRoot;
        if (!root) {
            return;
        }
        root.querySelectorAll('.drag-over').forEach((el) => el.classList.remove('drag-over'));
    }

    _findDropElement(clientX: number, clientY: number): Element | null {
        const root = this.renderRoot;
        if (!root) {
            return null;
        }
        if (this._view === 'month') {
            const cells = root.querySelectorAll('.month-cell:not(.outside)');
            for (const cell of cells) {
                const rect = cell.getBoundingClientRect();
                if (clientX >= rect.left && clientX <= rect.right && clientY >= rect.top && clientY <= rect.bottom) {
                    return cell;
                }
            }
            return null;
        }
        if (this._view === 'week') {
            const cols = root.querySelectorAll('.week-day-col');
            for (const col of cols) {
                const rect = col.getBoundingClientRect();
                if (clientX >= rect.left && clientX <= rect.right && clientY >= rect.top && clientY <= rect.bottom) {
                    return col;
                }
            }
            return null;
        }
        if (this._view === 'day') {
            const tracks = root.querySelector('.day-tracks');
            if (tracks) {
                const rect = tracks.getBoundingClientRect();
                if (clientX >= rect.left && clientX <= rect.right && clientY >= rect.top && clientY <= rect.bottom) {
                    return tracks;
                }
            }
            return null;
        }
        return null;
    }

    _findDropTarget(clientX: number, clientY: number): { date: string; minutes?: number } | null {
        const root = this.renderRoot;
        if (!root) {
            return null;
        }
        if (this._view === 'month') {
            const cells = root.querySelectorAll('.month-cell:not(.outside)');
            for (const cell of cells) {
                const rect = cell.getBoundingClientRect();
                if (clientX >= rect.left && clientX <= rect.right && clientY >= rect.top && clientY <= rect.bottom) {
                    if (!(cell instanceof HTMLElement)) {
                        throw new Error('platform-calendar-modal: month cell required');
                    }
                    const iso = cell.dataset.iso;
                    if (iso) {
                        return { date: iso };
                    }
                }
            }
            return null;
        }
        if (this._view === 'week') {
            const cols = root.querySelectorAll('.week-day-col');
            for (let i = 0; i < cols.length; i += 1) {
                const col = cols[i];
                if (!(col instanceof HTMLElement)) {
                    continue;
                }
                const rect = col.getBoundingClientRect();
                if (clientX >= rect.left && clientX <= rect.right && clientY >= rect.top && clientY <= rect.bottom) {
                    const iso = col.dataset.iso;
                    if (!iso) {
                        return null;
                    }
                    const bodyRect = col.closest('.week-body')?.getBoundingClientRect();
                    if (!bodyRect) {
                        return { date: iso };
                    }
                    const relativeY = clientY - bodyRect.top;
                    const hourPx = 48;
                    const totalMinutes = Math.round((relativeY / hourPx) * 60);
                    const snappedMinutes = Math.round(totalMinutes / 15) * 15;
                    const clampedMinutes = Math.max(0, Math.min(snappedMinutes, 24 * 60 - 15));
                    return { date: iso, minutes: clampedMinutes };
                }
            }
            return null;
        }
        if (this._view === 'day') {
            const tracks = root.querySelector('.day-tracks');
            if (!tracks) {
                return null;
            }
            const rect = tracks.getBoundingClientRect();
            if (clientX < rect.left || clientX > rect.right || clientY < rect.top || clientY > rect.bottom) {
                return null;
            }
            const relativeY = clientY - rect.top;
            const hourPx = 52;
            const totalMinutes = Math.round((relativeY / hourPx) * 60);
            const snappedMinutes = Math.round(totalMinutes / 15) * 15;
            const clampedMinutes = Math.max(0, Math.min(snappedMinutes, 24 * 60 - 15));
            return { date: this._anchorDate, minutes: clampedMinutes };
        }
        return null;
    }

    _applyDrop(event: CalendarEventRecord, dropTarget: { date: string; minutes?: number }): void {
        const eventStart = new Date(event.start_at);
        const eventEnd = new Date(event.end_at);
        const durationMs = eventEnd.getTime() - eventStart.getTime();
        const targetDate = parseDateInputLocal(dropTarget.date);

        let startAt;
        if (dropTarget.minutes !== undefined) {
            const hours = Math.floor(dropTarget.minutes / 60);
            const mins = dropTarget.minutes % 60;
            startAt = new Date(targetDate.getFullYear(), targetDate.getMonth(), targetDate.getDate(), hours, mins, 0, 0);
        } else {
            startAt = new Date(
                targetDate.getFullYear(), targetDate.getMonth(), targetDate.getDate(),
                eventStart.getHours(), eventStart.getMinutes(), eventStart.getSeconds(), 0
            );
        }

        const endAt = new Date(startAt.getTime() + durationMs);

        if (startAt.getTime() === eventStart.getTime()) {
            return;
        }

        this.dispatch(CALENDAR_EVENTS.EVENT_UPDATE_REQUESTED, {
            event_id: event.event_id,
            title: event.title,
            kind: event.kind,
            source: event.source,
            source_id: missingAsNull(event.source_id),
            namespace: missingAsNull(event.namespace),
            description: missingAsNull(event.description),
            location: missingAsNull(event.location),
            status: event.status ?? 'confirmed',
            timezone: event.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone,
            all_day: Boolean(event.all_day),
            start_at: startAt.toISOString(),
            end_at: endAt.toISOString(),
            attendees: event.attendees === undefined ? [] : event.attendees,
            recurrence_rule: missingAsNull(event.recurrence_rule),
            recurrence_id: missingAsNull(event.recurrence_id),
            series_id: missingAsNull(event.series_id),
            deep_link: missingAsNull(event.deep_link),
            metadata: event.metadata === undefined ? {} : event.metadata,
        });
    }

    _eventsForDate(date: Date): CalendarEventRecord[] {
        const dayStart = new Date(date.getFullYear(), date.getMonth(), date.getDate(), 0, 0, 0, 0);
        const dayEnd = addDays(dayStart, 1);
        const events = this._eventsSelect.value;
        return events.filter((event) => {
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

    _shiftDateSheetMonth(delta: number): void {
        const ref = new Date(this._dateSheetMonthRef);
        if (Number.isNaN(ref.getTime())) {
            throw new Error(`Invalid date sheet month ref: ${this._dateSheetMonthRef}`);
        }
        const shifted = new Date(ref.getFullYear(), ref.getMonth() + delta, 1, 0, 0, 0, 0);
        this._dateSheetMonthRef = toDateInputValue(shifted);
    }

    _selectDateFromSheet(iso: unknown): void {
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
                <div class="date-sheet-card" @click=${(e: Event) => e.stopPropagation()}>
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
                                style=${this._mailboxRibbonStyle(event)}
                                @click=${() => this._fillFormFromEvent(event)}
                            >
                                <span class="event-chip-title">${event.title}</span>
                            </button>
                        `)}
                    </div>
                ` : ''}
                <div class="day-timeline-scroll">
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
                                ${events.length === 0
                                    ? html`<div class="day-empty-hint">${this._calT('events_empty')}</div>`
                                    : ''}
                                ${showNow && nowTop !== null ? html`
                                    <div class="day-now-line" style=${`top:${nowTop}px`}></div>
                                ` : ''}
                                ${layoutTimed.map(({ event, top, height, colorKey, visibleStartMs }) => {
                                    const ribbon = this._mailboxRibbonStyle(event);
                                    const layoutStyle = `top:${top}px;height:${height}px;touch-action:none`;
                                    const style = ribbon === nothing ? layoutStyle : `${layoutStyle};${ribbon}`;
                                    return html`
                                    <button
                                        type="button"
                                        class="day-event-block event-chip"
                                        data-color=${colorKey}
                                        ?data-dragging=${this._dragEvent?.event_id === event.event_id}
                                        style=${style}
                                        @click=${() => this._fillFormFromEvent(event)}
                                        @pointerdown=${(e: PointerEvent) => this._onDragStart(event, e)}
                                    >
                                        <span class="event-chip-time">${this._formatWallClockFromMs(visibleStartMs)}</span>
                                        <span class="event-chip-title">${event.title}</span>
                                    </button>
                                `;
                                })}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    _sourceKey(source: unknown): string {
        return textOrEmpty(source).toLowerCase();
    }

    _isCalDavProvider(provider: unknown): boolean {
        return provider === 'yandex' || provider === 'mailru' || provider === 'caldav';
    }

    _integrationModalIconName() {
        const provider = this._integrationModalProvider;
        if (provider === 'google' || provider === 'yandex') {
            return provider;
        }
        if (provider === 'mailru') {
            return 'mail';
        }
        return 'calendar';
    }

    _providerDisplayLabel(provider: unknown): string {
        if (provider === 'google') {
            return 'Google';
        }
        if (provider === 'yandex') {
            return 'Yandex';
        }
        if (provider === 'mailru') {
            return 'Mail.ru';
        }
        if (provider === 'caldav') {
            return this._calT('integration_caldav');
        }
        return typeof provider === 'string' && provider ? provider.toUpperCase() : '';
    }

    _kindKey(kind: unknown): string {
        return textOrEmpty(kind).toLowerCase();
    }

    _sourceLabel(source: unknown): string {
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
        if (key === 'mailru') {
            return 'Mail.ru';
        }
        if (key === 'caldav') {
            return this._calT('integration_caldav');
        }
        return key ? key.toUpperCase() : this._calT('unknown');
    }

    _kindLabel(kind: unknown): string {
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

    _isEventEditable(source: unknown): boolean {
        return this._sourceKey(source) === 'platform';
    }

    _formatWallClockFromMs(ms: number): string {
        const instant = new Date(ms);
        if (Number.isNaN(instant.getTime())) {
            throw new Error('Invalid instant for wall clock');
        }
        return instant.toLocaleTimeString(this._calendarLocaleTag(), {
            hour: '2-digit',
            minute: '2-digit',
        });
    }

    _eventStartTimeLabel(event: CalendarEventRecord): string {
        const startDate = new Date(event.start_at);
        if (Number.isNaN(startDate.getTime())) {
            throw new Error('event.start_at must be valid datetime');
        }
        return this._formatWallClockFromMs(startDate.getTime());
    }

    _fillFormFromEvent(event: CalendarEventRecord): void {
        if (this._dragJustFinished) {
            return;
        }
        this._selectedEventId = event.event_id;
        this._showDescriptionField = Boolean(event.description);
        this._selectedEventSource = this._sourceKey(event.source);
        this._selectedEventKind = this._kindKey(event.kind);
        this._selectedEventNamespace = event.namespace === undefined || event.namespace.length === 0 ? null : event.namespace;
        this._eventMetadata = event.metadata && typeof event.metadata === 'object' ? { ...event.metadata } : {};
        this._eventAttachments = parseEventAttachments(this._eventMetadata);
        this._eventForm = {
            kind: event.kind || 'event',
            color: normalizeEventColor(this._eventMetadata[EVENT_COLOR_KEY]),
            title: textOrEmpty(event.title),
            description: textOrEmpty(event.description),
            location: textOrEmpty(event.location),
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

    _ruleToRecurrence(rule: string | null | undefined): string {
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

    _onEventFormChange(field: string, value: unknown): void {
        const form: EventFormState = { ...this._eventForm, [field]: value };

        if (field === 'start_at' || field === 'end_at') {
            const startMs = new Date(form.start_at).getTime();
            const endMs = new Date(form.end_at).getTime();

            if (!Number.isNaN(startMs) && !Number.isNaN(endMs) && startMs >= endMs) {
                const MIN_DURATION_MS = 15 * 60 * 1000;
                if (field === 'start_at') {
                    form.end_at = toDateTimeInputValue(new Date(startMs + MIN_DURATION_MS));
                } else {
                    form.start_at = toDateTimeInputValue(new Date(endMs - MIN_DURATION_MS));
                }
            }
        }

        this._eventForm = form;
    }

    _attendeeTags() {
        if (!Array.isArray(this._eventForm.attendees)) {
            return [];
        }
        return this._eventForm.attendees.map((entry) => toAttendeeTag(entry));
    }

    _addAttendeeByEmail(emailValue: unknown): void {
        const normalized = normalizeEmail(emailValue);
        if (!normalized) {
            return;
        }
        if (!EMAIL_PATTERN.test(normalized)) {
            this.toast('error_email_invalid', { type: 'error' });
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

    _addTeamMemberAsAttendee(member: TeamMemberRecord): void {
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

    _removeAttendee(emailValue: unknown): void {
        const email = normalizeEmail(emailValue);
        const nextAttendees = this._attendeeTags().filter((item) => item.email !== email);
        this._onEventFormChange('attendees', nextAttendees);
    }

    _attendeeSuggestions() {
        const query = this._attendeeDraft.trim().toLowerCase();
        const selectedEmails = new Set(this._attendeeTags().map((item) => item.email));
        const membersWithEmail = (this._teamMembersSelect.value)
            .filter((member) => normalizeEmail(member.email) !== '')
            .filter((member) => !selectedEmails.has(normalizeEmail(member.email)));
        if (!query) {
            return membersWithEmail.slice(0, 8);
        }
        return membersWithEmail
            .filter((member) => {
                const name = textOrEmpty(member.name).toLowerCase();
                const email = textOrEmpty(member.email).toLowerCase();
                return name.includes(query) || email.includes(query);
            })
            .slice(0, 8);
    }

    _onAttendeeInputKeyDown(event: KeyboardEvent): void {
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
            this._removeAttendee(tags[tags.length - 1]?.email);
        }
    }

    _openCreateEventDialog(date?: unknown): void {
        if (this._dragJustFinished) {
            return;
        }
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
        if (!(fileInput instanceof HTMLInputElement)) {
            throw new Error('Attachment input not found');
        }
        fileInput.value = '';
        fileInput.click();
    }

    _onAttachmentInputChange(event: Event): void {
        const input = event.target;
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('platform-calendar-modal: file input required');
        }
        const files = input.files === null ? [] : Array.from(input.files);
        if (files.length === 0) {
            return;
        }
        for (const file of files) {
            const correlation_id = `cal-upload-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
            this._pendingAttachmentUploads.set(correlation_id, { name: file.name });
            this.dispatch(
                FILES_EVENTS.UPLOAD_REQUESTED,
                {
                    file,
                    name: file.name,
                    spec: buildCalendarEventFileCreateSpecJson({ eventId: this._selectedEventId === null ? '' : this._selectedEventId }),
                },
                { correlation_id, source: 'local' },
            );
        }
        this._uploadingAttachments = this._pendingAttachmentUploads.size > 0;
        this.requestUpdate();
    }

    _onFileUploadCompleted(event: PlatformEvent): void {
        const correlation_id = event.meta?.correlation_id;
        if (!correlation_id || !this._pendingAttachmentUploads.has(correlation_id)) {
            return;
        }
        this._pendingAttachmentUploads.delete(correlation_id);
        const file = payloadFields(event).file;
        if (!isPlainRecord(file) || typeof file.file_id !== 'string' || file.file_id === '') {
            this._uploadingAttachments = this._pendingAttachmentUploads.size > 0;
            this.toast('err_upload_attachment', { type: 'error', vars: { message: 'invalid file payload' } });
            this.requestUpdate();
            return;
        }
        const existingIds = new Set(this._eventAttachments.map((item) => item.file_id));
        if (!existingIds.has(file.file_id)) {
            this._eventAttachments = [...this._eventAttachments, {
                file_id: file.file_id,
                name: typeof file.original_name === 'string' && file.original_name ? file.original_name : file.file_id,
                url: typeof file.url === 'string' ? file.url : '',
                content_type: typeof file.content_type === 'string' ? file.content_type : '',
                file_size: typeof file.file_size === 'number' && Number.isFinite(file.file_size) ? file.file_size : 0,
            }];
        }
        this._uploadingAttachments = this._pendingAttachmentUploads.size > 0;
        this.requestUpdate();
    }

    _onFileUploadFailed(event: PlatformEvent): void {
        const correlation_id = event.meta?.correlation_id;
        if (!correlation_id || !this._pendingAttachmentUploads.has(correlation_id)) {
            return;
        }
        this._pendingAttachmentUploads.delete(correlation_id);
        this._uploadingAttachments = this._pendingAttachmentUploads.size > 0;
        this.toast('err_upload_attachment', { type: 'error', vars: { message: calendarFailureMessage(event) } });
        this.requestUpdate();
    }

    _removeAttachment(fileId: string): void {
        this._eventAttachments = this._eventAttachments.filter((item) => item.file_id !== fileId);
    }

    _resetEventFormAfterSave() {
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
    }

    _saveEvent() {
        if (this._selectedEventId && !this._isEventEditable(this._selectedEventSource)) {
            this.toast('err_edit_remote', { type: 'error', vars: { label: this._sourceLabel(this._selectedEventSource) } });
            return;
        }
        const activeMailboxBindingId = this._mailSelect.value.activeMailboxBindingId;
        if (typeof activeMailboxBindingId !== 'string' || activeMailboxBindingId.length === 0) {
            this.toast('err_mailbox_required', { type: 'error' });
            return;
        }
        const payload = {
            title: this._eventForm.title.trim(),
            kind: this._eventForm.kind.trim(),
            source: 'platform',
            source_id: null,
            namespace: null,
            description: blankToNull(this._eventForm.description),
            location: blankToNull(this._eventForm.location),
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
            mailbox_binding_id: activeMailboxBindingId,
            metadata: buildEventMetadata(
                {
                    ...this._eventMetadata,
                    [EVENT_COLOR_KEY]: normalizeEventColor(this._eventForm.color),
                },
                this._eventAttachments
            ),
        };
        if (!payload.title) {
            this.toast('err_title_required', { type: 'error' });
            return;
        }
        if (!payload.kind) {
            this.toast('err_kind_required', { type: 'error' });
            return;
        }
        if (new Date(payload.start_at) >= new Date(payload.end_at)) {
            this.toast('err_end_after_start', { type: 'error' });
            return;
        }
        this._saving = true;
        if (this._selectedEventId) {
            this.dispatch(CALENDAR_EVENTS.EVENT_UPDATE_REQUESTED, {
                event_id: this._selectedEventId,
                ...payload,
            });
        } else {
            this.dispatch(CALENDAR_EVENTS.EVENT_CREATE_REQUESTED, payload);
        }
    }

    _deleteSelectedEvent() {
        if (!this._selectedEventId) {
            this.toast('err_no_event_selected', { type: 'error' });
            return;
        }
        if (!this._isEventEditable(this._selectedEventSource)) {
            this.toast('err_delete_remote', { type: 'error', vars: { label: this._sourceLabel(this._selectedEventSource) } });
            return;
        }
        this.dispatch(CALENDAR_EVENTS.EVENT_DELETE_REQUESTED, { event_id: this._selectedEventId });
    }

    _saveIntegration() {
        if (this._activeProvider === 'google') {
            this.toast('err_google_oauth_only', { type: 'error' });
            return;
        }
        const activeIntegration = this._activeIntegration();
        const payload = {
            provider: this._activeProvider,
            mailbox_binding_id: activeIntegration ? activeIntegration.mailbox_binding_id : null,
            username: this._integrationForm.username.trim(),
            access_token: this._integrationForm.app_password.trim(),
            refresh_token: null,
            expires_at: null,
            scope: null,
            token_type: null,
            default_calendar_id: blankToNull(this._integrationForm.default_calendar_id),
            caldav_base_url: blankToNull(this._integrationForm.caldav_base_url),
            sync_enabled: Boolean(this._integrationForm.sync_enabled),
            sync_inbound_enabled: Boolean(this._integrationForm.sync_inbound_enabled),
            sync_outbound_enabled: Boolean(this._integrationForm.sync_outbound_enabled),
            notifications_enabled: Boolean(this._integrationForm.notifications_enabled),
        };
        if (!payload.username) {
            this.toast('err_username_required', { type: 'error' });
            return;
        }
        if (!payload.access_token) {
            this.toast('err_app_password_required', { type: 'error' });
            return;
        }
        if (this._activeProvider === 'caldav' && !payload.caldav_base_url) {
            this.toast('err_caldav_base_url_required', { type: 'error' });
            return;
        }
        this._saving = true;
        this.dispatch(CALENDAR_EVENTS.INTEGRATION_CONNECT_REQUESTED, payload);
    }

    _startGoogleConnect() {
        const returnPath = `${window.location.pathname}${window.location.search}`;
        const base = serviceBaseUrlForCalendar();
        const connectUrl = `${base}/api/calendar/integrations/google/start?return_path=${encodeURIComponent(returnPath)}`;
        window.location.assign(connectUrl);
    }

    _disconnectIntegration(integrationId: unknown): void {
        if (typeof integrationId !== 'string' || integrationId.length === 0) {
            throw new Error('platform-calendar-modal: integration_id required to disconnect');
        }
        this.dispatch(CALENDAR_EVENTS.INTEGRATION_DISCONNECT_REQUESTED, { integration_id: integrationId });
    }

    _runSync(integrationId: unknown): void {
        if (typeof integrationId !== 'string' || integrationId.length === 0) {
            throw new Error('platform-calendar-modal: integration_id required to sync');
        }
        this._syncing = true;
        const range = this._viewRange();
        this.dispatch(CALENDAR_EVENTS.SYNC_REQUESTED, {
            integration_id: integrationId,
            start_at: range.start.toISOString(),
            end_at: range.end.toISOString(),
        });
    }

    _activeIntegration() {
        const integrations = this._integrationsSelect.value;
        const found = this._activeIntegrationId
            ? integrations.find((item) => item.integration_id === this._activeIntegrationId)
            : integrations.find((item) => item.provider === this._activeProvider);
        return found === undefined ? null : found;
    }

    _mailboxLabelForIntegration(integration: CalendarState['integrations'][number] | null | undefined): string | null {
        const mailboxBindingId = integration && integration.mailbox_binding_id;
        if (typeof mailboxBindingId !== 'string' || mailboxBindingId.length === 0) {
            return null;
        }
        const bindings = this._mailSelect.value.bindings;
        const binding = Array.isArray(bindings)
            ? bindings.find((item) => item.mailbox_binding_id === mailboxBindingId)
            : null;
        return binding ? binding.email_address : mailboxBindingId;
    }

    _onIntegrationProviderSelect(provider: string, integrationId: string | null = null): void {
        this._activeProvider = provider;
        this._activeIntegrationId = integrationId;
        const activeIntegration = this._activeIntegration();
        if (!this._isCalDavProvider(provider) || !activeIntegration) {
            return;
        }
        const settings = isPlainRecord(activeIntegration.settings) ? activeIntegration.settings : {};
        const mailboxLabel = this._mailboxLabelForIntegration(activeIntegration);
        this._integrationForm = {
            ...this._integrationForm,
            username: activeIntegration.mailbox_binding_id
                ? (mailboxLabel === null ? '' : mailboxLabel)
                : this._integrationForm.username,
            default_calendar_id: typeof settings.default_calendar_id === 'string' ? settings.default_calendar_id : '',
            caldav_base_url: typeof settings.caldav_base_url === 'string' ? settings.caldav_base_url : '',
            sync_enabled: settings.sync_enabled !== false,
            sync_inbound_enabled: settings.sync_inbound_enabled !== false,
            sync_outbound_enabled: settings.sync_outbound_enabled !== false,
            notifications_enabled: settings.notifications_enabled !== false,
        };
    }

    _renderWeekGrid() {
        const anchor = parseDateInputLocal(this._anchorDate);
        anchor.setHours(12, 0, 0, 0);
        const weekStart = startOfWeek(anchor);
        const hourPx = 48;
        const daySpanMin = 24 * 60;
        const dayHeightPx = 24 * hourPx;
        const hours = Array.from({ length: 24 }, (_, h) => h);
        const now = new Date();
        const today = new Date();
        const weekdayNames = [1, 2, 3, 4, 5, 6, 7].map((i) => this._calT(`weekday_${i}`));

        const days = Array.from({ length: 7 }, (_, i) => {
            const date = addDays(weekStart, i);
            const dayOfWeek = date.getDay();
            return {
                date,
                iso: toDateInputValue(date),
                label: weekdayNames[i],
                number: date.getDate(),
                today: isSameDay(date, today),
                weekend: dayOfWeek === 0 || dayOfWeek === 6,
                events: this._eventsForDate(date),
            };
        });

        const hasAllDay = days.some((d) => d.events.some((e) => e.all_day));

        const layoutForDay = (day: { date: Date; events: CalendarEventRecord[] }) => {
            const timed = day.events.filter((e) => !e.all_day);
            const dayStart = new Date(day.date.getFullYear(), day.date.getMonth(), day.date.getDate(), 0, 0, 0, 0);
            const dayEndMs = addDays(dayStart, 1).getTime();
            return timed.map((event) => {
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
                const height = Math.max((durMin / daySpanMin) * dayHeightPx, 22);
                const colorKey = normalizeEventColor(event.metadata?.[EVENT_COLOR_KEY]);
                return { event, top, height, colorKey, visibleStartMs: startClamped };
            });
        };

        return html`
            <div class="week-grid">
                <div class="week-header">
                    <div class="week-time-spacer"></div>
                    ${days.map((day) => html`
                        <div class="week-day-header ${day.today ? 'today' : ''} ${day.weekend ? 'weekend' : ''}">
                            <span>${day.label}</span>
                            <span class="week-day-number">${day.number}</span>
                        </div>
                    `)}
                </div>
                ${hasAllDay ? html`
                    <div class="week-all-day-row">
                        <div class="week-time-spacer"></div>
                        ${days.map((day) => {
                            const allDayEvents = day.events.filter((e) => e.all_day);
                            return html`
                                <div class="week-all-day-cell">
                                    ${allDayEvents.map((event) => html`
                                        <button
                                            type="button"
                                            class="event-chip"
                                            data-color=${normalizeEventColor(event.metadata?.[EVENT_COLOR_KEY])}
                                            style=${this._mailboxRibbonStyle(event)}
                                            @click=${() => this._fillFormFromEvent(event)}
                                        >
                                            <span class="event-chip-title">${event.title}</span>
                                        </button>
                                    `)}
                                </div>
                            `;
                        })}
                    </div>
                ` : ''}
                <div class="week-body-scroll">
                    <div class="week-body">
                        <div class="week-time-col">
                            ${hours.map((h) => html`
                                <div class="week-time-label">${pad2(h)}:00</div>
                            `)}
                        </div>
                        ${days.map((day) => {
                            const timedLayout = layoutForDay(day);
                            const showNowLine = day.today && isSameDay(now, day.date);
                            const nowTop = showNowLine
                                ? (((now.getHours() * 60 + now.getMinutes()) / daySpanMin) * dayHeightPx)
                                : null;
                            return html`
                                <div class="week-day-col ${day.today ? 'today' : ''} ${day.weekend ? 'weekend' : ''}" data-iso=${day.iso}>
                                    <div class="week-day-lines">
                                        ${hours.map(() => html`<div class="week-hour-slot"></div>`)}
                                    </div>
                                    <div class="week-day-events">
                                        ${showNowLine && nowTop !== null ? html`
                                            <div class="day-now-line" style=${`top:${nowTop}px`}></div>
                                        ` : ''}
                                        ${timedLayout.map(({ event, top, height, colorKey, visibleStartMs }) => {
                                            const ribbon = this._mailboxRibbonStyle(event);
                                            const layoutStyle = `top:${top}px;height:${height}px;touch-action:none`;
                                            const style = ribbon === nothing ? layoutStyle : `${layoutStyle};${ribbon}`;
                                            return html`
                                            <button
                                                type="button"
                                                class="day-event-block event-chip"
                                                data-color=${colorKey}
                                                ?data-dragging=${this._dragEvent?.event_id === event.event_id}
                                                style=${style}
                                                @click=${() => this._fillFormFromEvent(event)}
                                                @pointerdown=${(e: PointerEvent) => this._onDragStart(event, e)}
                                            >
                                                <span class="event-chip-time">${this._formatWallClockFromMs(visibleStartMs)}</span>
                                                <span class="event-chip-title">${event.title}</span>
                                            </button>
                                        `;
                                        })}
                                    </div>
                                </div>
                            `;
                        })}
                    </div>
                </div>
            </div>
        `;
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
                        data-iso=${cell.iso}
                        @click=${() => this._openCreateEventDialog(cell.date)}
                    >
                        <div class="date-label">${cell.date.getDate()}</div>
                        <div class="month-cell-events">
                            ${cell.events.map((event) => {
                                const ribbon = this._mailboxRibbonStyle(event);
                                const style = ribbon === nothing
                                    ? 'touch-action: none;'
                                    : `touch-action: none;${ribbon}`;
                                return html`
                                <button
                                    class="event-chip ${this._selectedEventId === event.event_id ? 'active' : ''}"
                                    data-color=${normalizeEventColor(event.metadata?.[EVENT_COLOR_KEY])}
                                    ?data-dragging=${this._dragEvent?.event_id === event.event_id}
                                    type="button"
                                    @click=${(e: Event) => {
                                        e.stopPropagation();
                                        this._fillFormFromEvent(event);
                                    }}
                                    @pointerdown=${(e: PointerEvent) => this._onDragStart(event, e)}
                                    title=${`${this._sourceLabel(event.source)} • ${this._kindLabel(event.kind)}`}
                                    style=${style}
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
                            `;
                            })}
                        </div>
                    </article>
                `)}
            </div>
        `;
    }

    _renderEventForm() {
        const submitLabel = this._saving
            ? this._calT('compose_saving')
            : (this._selectedEventId ? this._calT('compose_save') : this._calT('compose_create'));
        const c = (key: string, params?: Record<string, string | number>) => this._calT(key, params);
        return html`
            <div class="event-compose">
                <div class="event-compose-row">
                    <label class="event-compose-label">${c('label_title')}</label>
                    <div class="event-compose-control">
                        <input
                            class="event-compose-title-input"
                            .value=${this._eventForm.title}
                            @input=${(e: Event) => this._onEventFormChange('title', formControlValue(e))}
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
                                        <button
                                            type="button"
                                            class="event-compose-attachment-link"
                                            title=${attachment.name}
                                            @click=${() => this.openFile({
                                                file_id: attachment.file_id,
                                                original_name: attachment.name,
                                                content_type: typeof attachment.content_type === 'string' ? attachment.content_type : '',
                                                url: attachment.url,
                                            }, { source: 'calendar_event_attachment' })}
                                        >
                                            ${attachment.name}
                                        </button>
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
                                @input=${(e: Event) => this._onEventFormChange('description', formControlValue(e))}
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
                                    @input=${(event: Event) => {
                                        this._attendeeDraft = formControlValue(event);
                                        this._attendeeDropdownOpen = true;
                                    }}
                                    @keydown=${(event: KeyboardEvent) => this._onAttendeeInputKeyDown(event)}
                                    placeholder=${c('attendee_placeholder')}
                                />
                            </div>
                            ${this._attendeeDropdownOpen && this._attendeeSuggestions().length > 0 ? html`
                                <div class="attendees-dropdown">
                                    ${this._attendeeSuggestions().map((member) => html`
                                        <button class="attendee-option" type="button" @mousedown=${(event: Event) => event.preventDefault()} @click=${() => this._addTeamMemberAsAttendee(member)}>
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
                                @change=${(e: Event) => this._onEventFormChange('start_at', formControlValue(e))}
                            ></platform-date-picker>
                            <div class="event-compose-time-sep">-</div>
                            <platform-date-picker
                                mode="datetime"
                                value-format="iso"
                                .value=${this._eventForm.end_at}
                                @change=${(e: Event) => this._onEventFormChange('end_at', formControlValue(e))}
                            ></platform-date-picker>
                        </div>
                        <div class="event-compose-options">
                            <div class="event-compose-switch">
                                <platform-switch
                                    .checked=${Boolean(this._eventForm.all_day)}
                                    .label=${c('all_day')}
                                    @change=${(e: Event) => this._onEventFormChange('all_day', customEventValue(e))}
                                ></platform-switch>
                            </div>
                            <div class="event-compose-switch">
                                <platform-switch
                                    .checked=${this._eventForm.recurrence !== 'none'}
                                    .label=${c('repeat')}
                                    @change=${(e: Event) => this._onEventFormChange('recurrence', customEventValue(e) ? 'weekly' : 'none')}
                                ></platform-switch>
                            </div>
                            <platform-timezone-picker
                                class="event-compose-tz"
                                .value=${this._eventForm.timezone}
                                @change=${(e: Event) => this._onEventFormChange('timezone', customEventValue(e))}
                            ></platform-timezone-picker>
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
                            @change=${(e: Event) => this._onEventFormChange('kind', formControlValue(e))}
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
                            @input=${(e: Event) => this._onEventFormChange('location', formControlValue(e))}
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

    _openIntegrationModal(provider: string, integrationId: string | null = null): void {
        this._integrationsMenuOpen = false;
        this._onIntegrationProviderSelect(provider, integrationId);
        this._integrationModalProvider = provider;
    }

    _closeIntegrationModal() {
        this._integrationModalProvider = null;
        this._activeIntegrationId = null;
    }

    _renderIntegrationModal() {
        if (!this._integrationModalProvider) {
            return html``;
        }
        const c = (key: string, params?: Record<string, string | number>) => this._calT(key, params);
        const providerLabel = this._providerDisplayLabel(this._integrationModalProvider);
        return html`
            <div class="integration-modal-overlay" @click=${() => this._closeIntegrationModal()}>
                <div class="integration-modal" @click=${(e: Event) => e.stopPropagation()}>
                    <div class="integration-modal-header">
                        <div class="integration-modal-title">
                            <platform-icon name=${this._integrationModalIconName()} size="20" colored></platform-icon>
                            ${c('integration_provider_title', { provider: providerLabel })}
                        </div>
                        <button class="btn-icon" type="button" @click=${() => this._closeIntegrationModal()}>
                            <platform-icon name="close" size="18"></platform-icon>
                        </button>
                    </div>
                    ${this._renderIntegrationContent()}
                </div>
            </div>
        `;
    }

    _renderIntegrationContent() {
        const c = (key: string, params?: Record<string, string | number>) => this._calT(key, params);
        const activeIntegration = this._activeIntegration();

        if (this._activeProvider === 'google') {
            return this._renderGoogleIntegration(c, activeIntegration);
        }
        return this._renderCalDavIntegration(c, activeIntegration, this._activeProvider);
    }

    _renderGoogleIntegration(c: (key: string, params?: Record<string, string | number>) => string, activeIntegration: CalendarState['integrations'][number] | null) {
        return html`
            <div class="hint">${c('google_oauth_hint')}</div>
            <div class="hint">${c('autosync_hint')}</div>
            ${activeIntegration ? html`
                <div class="hint">
                    ${c('notifications_label', {
                        state: integrationSettings(activeIntegration.settings).notifications_enabled === false
                            ? c('notifications_off')
                            : c('notifications_on'),
                    })}
                </div>
            ` : ''}
            <div class="actions">
                <button class="btn btn-primary" type="button" @click=${() => this._startGoogleConnect()}>
                    ${activeIntegration ? c('reconnect_google') : c('connect_google')}
                </button>
                <button
                    class="btn btn-secondary"
                    type="button"
                    @click=${() => this._runSync(activeIntegration?.integration_id)}
                    ?disabled=${this._syncing || !activeIntegration}
                >
                    ${this._syncing ? c('syncing') : c('sync')}
                </button>
                ${activeIntegration ? html`
                    <button class="btn btn-danger" type="button" @click=${() => this._disconnectIntegration(activeIntegration.integration_id)}>
                        ${c('disconnect')}
                    </button>
                ` : ''}
            </div>
            ${this._renderIntegrationList()}
        `;
    }

    _renderCalDavIntegration(c: (key: string, params?: Record<string, string | number>) => string, activeIntegration: CalendarState['integrations'][number] | null, provider: string) {
        const isCustom = provider === 'caldav';
        const usernamePlaceholder = provider === 'mailru'
            ? 'login@mail.ru'
            : (provider === 'yandex' ? 'login@yandex.ru' : c('caldav_username_placeholder'));
        const calendarIdPlaceholder = isCustom
            ? c('caldav_calendar_id_placeholder')
            : c('yandex_calendar_id_placeholder');
        const mailboxLabel = this._mailboxLabelForIntegration(activeIntegration);
        const baseUrlPlaceholder = isCustom
            ? 'https://caldav.example.com'
            : (provider === 'mailru' ? 'https://calendar.mail.ru' : 'https://caldav.yandex.ru');
        return html`
            <div class="hint">${c('caldav_hint')}</div>
            ${mailboxLabel ? html`
                <div class="hint">${c('integration_mailbox_label', { email: mailboxLabel })}</div>
            ` : ''}
            <div class="row">
                <label class="form-label">${c('caldav_base_url_label')}</label>
                <input
                    class="form-input"
                    .value=${this._integrationForm.caldav_base_url}
                    @input=${(e: Event) => { this._integrationForm = { ...this._integrationForm, caldav_base_url: formControlValue(e) }; }}
                    placeholder=${baseUrlPlaceholder}
                />
            </div>
            <div class="row">
                <label class="form-label">${c('yandex_username_label')}</label>
                <input
                    class="form-input"
                    .value=${this._integrationForm.username}
                    @input=${(e: Event) => { this._integrationForm = { ...this._integrationForm, username: formControlValue(e) }; }}
                    placeholder=${usernamePlaceholder}
                />
            </div>
            <div class="row">
                <label class="form-label">${c('yandex_app_password_label')}</label>
                <input
                    class="form-input"
                    .value=${this._integrationForm.app_password}
                    @input=${(e: Event) => { this._integrationForm = { ...this._integrationForm, app_password: formControlValue(e) }; }}
                    placeholder=${c('yandex_password_placeholder')}
                />
            </div>
            <div class="row">
                <label class="form-label">${c('yandex_calendar_id_label')}</label>
                <input
                    class="form-input"
                    .value=${this._integrationForm.default_calendar_id}
                    @input=${(e: Event) => { this._integrationForm = { ...this._integrationForm, default_calendar_id: formControlValue(e) }; }}
                    placeholder=${calendarIdPlaceholder}
                />
            </div>
            <div class="event-compose-switch event-compose-switch--spaced">
                <platform-switch
                    .checked=${Boolean(this._integrationForm.notifications_enabled)}
                    .label=${c('notifications_new_events')}
                    @change=${(e: Event) => {
                        this._integrationForm = { ...this._integrationForm, notifications_enabled: Boolean(customEventValue(e)) };
                    }}
                ></platform-switch>
            </div>
            <div class="hint">${c('autosync_hint')}</div>
            <div class="actions">
                <button class="btn btn-primary" type="button" @click=${this._saveIntegration} ?disabled=${this._saving}>
                    ${c('save_connection')}
                </button>
                <button
                    class="btn btn-secondary"
                    type="button"
                    @click=${() => this._runSync(activeIntegration?.integration_id)}
                    ?disabled=${this._syncing || !activeIntegration}
                >
                    ${this._syncing ? c('syncing') : c('sync')}
                </button>
                ${activeIntegration ? html`
                    <button class="btn btn-danger" type="button" @click=${() => this._disconnectIntegration(activeIntegration.integration_id)}>
                        ${c('disconnect')}
                    </button>
                ` : ''}
            </div>
            ${this._renderIntegrationList()}
        `;
    }

    _renderIntegrationList() {
        const c = (key: string, params?: Record<string, string | number>) => this._calT(key, params);
        return html`
            <div class="integration-list">
                ${(this._integrationsSelect.value).map((integration) => {
                    const mailboxLabel = this._mailboxLabelForIntegration(integration);
                    const title = mailboxLabel
                        ? `${this._providerDisplayLabel(integration.provider)} / ${mailboxLabel}`
                        : `${this._providerDisplayLabel(integration.provider)} / ${calendarIdLabel(integration.settings, c('integration_no_calendar'))}`;
                    return html`
                        <div class="integration-item">
                            <div>
                                <div>${title}</div>
                                <div class="hint">${c('integration_updated_at', {
                                    value: formatPlatformDateTime(integration.updated_at as string, this._localeSelect.value),
                                })}</div>
                            </div>
                            <div class="actions">
                                <button
                                    class="btn btn-secondary"
                                    type="button"
                                    @click=${() => {
                                        const integrationId = integration.integration_id;
                                        this._openIntegrationModal(
                                            integration.provider as string,
                                            typeof integrationId === 'string' && integrationId.length > 0 ? integrationId : null,
                                        );
                                    }}
                                >${c('integration_configure')}</button>
                                <button
                                    class="btn btn-danger"
                                    type="button"
                                    @click=${() => this._disconnectIntegration(integration.integration_id)}
                                >${c('disconnect')}</button>
                            </div>
                        </div>
                    `;
                })}
            </div>
        `;
    }


    _renderEventDialog() {
        if (!this._eventDialogOpen) {
            return html``;
        }
        return html`
            <div class="event-dialog-overlay" @click=${() => this._closeEventDialog()}>
                <section class="event-dialog" @click=${(e: Event) => e.stopPropagation()}>
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
        if (this._calendarLoadingSelect.value) {
            return html`<div class="hint">${this._calT('loading')}</div>`;
        }
        if (this._view === 'month') {
            return this._renderMonth();
        }
        if (this._view === 'day') {
            return this._renderDayTimeline();
        }
        return this._renderWeekGrid();
    }

    _renderIntegrationsMenuBlock(v: (key: string) => string, headerStyle = false) {
        const btnClass = headerStyle ? 'header-btn' : 'btn-icon';
        const iconSize = '16';
        return html`
            <div class="integrations-menu-anchor">
                <button
                    class=${btnClass}
                    type="button"
                    @click=${() => { this._integrationsMenuOpen = !this._integrationsMenuOpen; }}
                    title=${v('integrations_menu')}
                >
                    <platform-icon name="more-vert" size=${iconSize}></platform-icon>
                </button>
                ${this._integrationsMenuOpen ? html`
                    <div class="integrations-dropdown" @click=${(e: Event) => e.stopPropagation()}>
                        <button class="dropdown-item" type="button" @click=${() => this._openIntegrationModal('google')}>
                            <platform-icon name="google" size="16" colored></platform-icon>
                            <span>${v('integration_google')}</span>
                        </button>
                        <button class="dropdown-item" type="button" @click=${() => this._openIntegrationModal('yandex')}>
                            <platform-icon name="yandex" size="16" colored></platform-icon>
                            <span>${v('integration_yandex')}</span>
                        </button>
                        <button class="dropdown-item" type="button" @click=${() => this._openIntegrationModal('mailru')}>
                            <platform-icon name="mail" size="16"></platform-icon>
                            <span>${v('integration_mailru')}</span>
                        </button>
                        <button class="dropdown-item" type="button" @click=${() => this._openIntegrationModal('caldav')}>
                            <platform-icon name="calendar" size="16"></platform-icon>
                            <span>${v('integration_caldav')}</span>
                        </button>
                    </div>
                ` : ''}
            </div>
        `;
    }

    _renderCompactHeaderDateNav(v: (key: string) => string) {
        return html`
            <div class="calendar-header-date-nav">
                <button class="btn-icon" type="button" @click=${() => { void this._movePeriod(-1); }} aria-label=${v('sheet_prev_day')}>
                    <platform-icon name="chevron-left" size="16"></platform-icon>
                </button>
                <button class="period-date-btn" type="button" @click=${() => this._openDateSheet()} title=${v('pick_date_title')}>
                    ${this._compactPeriodLabel()}
                </button>
                <button class="btn-icon" type="button" @click=${() => { void this._movePeriod(1); }} aria-label=${v('sheet_next_day')}>
                    <platform-icon name="chevron-right" size="16"></platform-icon>
                </button>
            </div>
        `;
    }

    override renderBody() {
        const v = (key: string) => this._calT(key);
        const compact = this._isCompactLayout;
        return html`
            <div class="calendar-shell-wrap">
                <div class="calendar-shell">
                    <platform-mail-calendar-rail
                        surface="calendar"
                        show-settings
                        @settings-click=${() => this._openCalendarRailSettings()}
                    ></platform-mail-calendar-rail>
                    <section class="calendar-main">
                        <div class="toolbar ${compact ? 'toolbar--compact' : ''}">
                            <div class="toolbar-left">
                                ${compact
                                    ? this._renderCompactHeaderDateNav(v)
                                    : html`
                                        <div class="title">${this._periodLabel()}</div>
                                        <button class="btn-icon" type="button" @click=${() => { void this._movePeriod(-1); }}>
                                            <platform-icon name="chevron-left" size="16"></platform-icon>
                                        </button>
                                        <button class="btn-icon" type="button" @click=${() => { void this._movePeriod(1); }}>
                                            <platform-icon name="chevron-right" size="16"></platform-icon>
                                        </button>
                                    `}
                                <div class="view-segment">
                                    <button class=${this._view === 'day' ? 'active' : ''} type="button" @click=${() => this._onViewChange('day')}>${v('view_day')}</button>
                                    <button class=${this._view === 'week' ? 'active' : ''} type="button" @click=${() => this._onViewChange('week')}>${v('view_week')}</button>
                                    <button class=${this._view === 'month' ? 'active' : ''} type="button" @click=${() => this._onViewChange('month')}>${v('view_month')}</button>
                                </div>
                            </div>
                            <div class="toolbar-right">
                                <button
                                    class="btn btn-primary btn-calendar-create toolbar-create"
                                    type="button"
                                    title=${v('create_event')}
                                    aria-label=${v('create_event')}
                                    @click=${() => this._openCreateEventDialog(parseDateInputLocal(this._anchorDate))}
                                >
                                    <platform-icon name="plus" size="16"></platform-icon>
                                </button>
                                ${this._renderIntegrationsMenuBlock(v, compact)}
                                <button
                                    class="btn-icon"
                                    type="button"
                                    @click=${() => this.close()}
                                    title=${v('modal.close')}
                                    aria-label=${v('modal.close')}
                                >
                                    <platform-icon name="close" size="16"></platform-icon>
                                </button>
                            </div>
                        </div>
                        <div class="calendar-panel ${this._view === 'day' ? 'calendar-panel--day' : ''}">
                            ${this._renderCalendarPanel()}
                        </div>
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
                ` : nothing}
                ${this._renderDateSheet()}
                ${this._renderEventDialog()}
                ${this._renderIntegrationModal()}
                ${this._dragEvent && this._dragOrigin?.started ? html`
                    <div class="drag-ghost" style=${`top:${this._dragGhostTop}px;left:${this._dragGhostLeft}px`}>
                        ${this._dragEvent.title}
                    </div>
                ` : nothing}
            </div>
        `;
    }
}

customElements.define('platform-calendar-modal', PlatformCalendarModal);
registerModalKind(PlatformCalendarModal.modalKind, 'platform-calendar-modal');
