import { html, css, render, nothing } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { nextModalLayerZIndex } from '../utils/modal-z-stack.js';
import './platform-icon.js';

const DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;
const DATETIME_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/;
const TIME_PATTERN = /^(\d{2}):(\d{2})$/;
const DAYS_IN_WEEK = 7;

function pad2(value) {
    return String(value).padStart(2, '0');
}

function assertEnumValue(fieldName, value, allowedValues) {
    if (!allowedValues.includes(value)) {
        throw new Error(`${fieldName} must be one of: ${allowedValues.join(', ')}`);
    }
}

function cloneDate(date) {
    return new Date(date.getTime());
}

function startOfDay(date) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function parseIsoDate(value) {
    const match = DATE_PATTERN.exec(value);
    if (!match) {
        throw new Error(`Invalid date format: ${value}`);
    }
    const year = Number(match[1]);
    const month = Number(match[2]) - 1;
    const day = Number(match[3]);
    return new Date(year, month, day);
}

function parseIsoDateTime(value) {
    const match = DATETIME_PATTERN.exec(value);
    if (!match) {
        throw new Error(`Invalid datetime format: ${value}`);
    }
    const year = Number(match[1]);
    const month = Number(match[2]) - 1;
    const day = Number(match[3]);
    const hours = Number(match[4]);
    const minutes = Number(match[5]);
    return new Date(year, month, day, hours, minutes, 0, 0);
}

function parseIsoTime(value) {
    const match = TIME_PATTERN.exec(value);
    if (!match) {
        throw new Error(`Invalid time format: ${value}`);
    }
    const hours = Number(match[1]);
    const minutes = Number(match[2]);
    if (hours < 0 || hours > 23) {
        throw new Error(`Hour is out of range: ${value}`);
    }
    if (minutes < 0 || minutes > 59) {
        throw new Error(`Minute is out of range: ${value}`);
    }
    return (hours * 60) + minutes;
}

function formatIsoDate(date) {
    return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function formatIsoDateTime(date) {
    return `${formatIsoDate(date)}T${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function formatIsoTime(totalMinutes) {
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    return `${pad2(hours)}:${pad2(minutes)}`;
}

function minutesToDate(totalMinutes) {
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    return new Date(1970, 0, 1, hours, minutes, 0, 0);
}

function dateToMinutes(date) {
    return (date.getHours() * 60) + date.getMinutes();
}

function compareDateOnly(left, right) {
    const leftValue = startOfDay(left).getTime();
    const rightValue = startOfDay(right).getTime();
    if (leftValue < rightValue) {
        return -1;
    }
    if (leftValue > rightValue) {
        return 1;
    }
    return 0;
}

function dateAtWeekStart(date) {
    const result = startOfDay(date);
    const day = result.getDay();
    const shift = day === 0 ? 6 : day - 1;
    result.setDate(result.getDate() - shift);
    return result;
}

function normalizeDateForMode(mode, date) {
    if (mode === 'date') {
        return startOfDay(date);
    }
    return cloneDate(date);
}

function applyMinutes(date, minutes) {
    const target = cloneDate(date);
    target.setHours(Math.floor(minutes / 60), minutes % 60, 0, 0);
    return target;
}

function toRangeValue(startValue, endValue, valueFormat) {
    if (valueFormat === 'date') {
        return {
            start: startValue,
            end: endValue,
        };
    }
    return {
        start: startValue,
        end: endValue,
    };
}

export class PlatformDatePicker extends PlatformElement {
    static properties = {
        mode: { type: String, reflect: true },
        selection: { type: String, reflect: true },
        valueFormat: { type: String, attribute: 'value-format', reflect: true },
        value: { attribute: false },
        min: { type: String },
        max: { type: String },
        step: { type: Number },
        locale: { type: String },
        disabled: { type: Boolean, reflect: true },
        readonly: { type: Boolean, reflect: true },
        required: { type: Boolean, reflect: true },
        placeholder: { type: String },
        label: { type: String },
        leadingIcon: { type: String, attribute: 'leading-icon' },
        embedded: { type: Boolean, reflect: true },
        hideTriggerIcon: { type: Boolean, attribute: 'hide-trigger-icon', reflect: true },
        open: { type: Boolean, reflect: true },
        _viewYear: { state: true },
        _viewMonth: { state: true },
        _focusedDateIso: { state: true },
        _activeTimeTarget: { state: true },
        _singleDate: { state: true },
        _rangeStart: { state: true },
        _rangeEnd: { state: true },
        _singleTime: { state: true },
        _rangeStartTime: { state: true },
        _rangeEndTime: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-block;
                position: relative;
                min-width: 180px;
            }

            .trigger {
                width: 100%;
                min-height: 42px;
                border: 1px solid var(--border-default);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                font-size: var(--text-sm);
                line-height: 1;
                padding: var(--space-2) var(--space-3);
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                cursor: pointer;
            }

            .trigger.with-label {
                min-height: var(--platform-date-picker-labeled-height, 62px);
                border: 1px solid var(--platform-date-picker-labeled-border, var(--border-subtle));
                background: var(--platform-date-picker-labeled-bg, var(--glass-solid-subtle));
                border-radius: var(--radius-full);
                padding: var(--platform-date-picker-labeled-padding, var(--space-2) var(--space-4));
            }

            :host([embedded]) .trigger {
                min-height: 28px;
                border: none;
                border-radius: 0;
                background: transparent;
                padding: 0;
                box-shadow: none;
            }

            .trigger:focus-visible {
                outline: none;
                box-shadow: var(--focus-ring);
                border-color: var(--accent);
            }

            .trigger[aria-expanded='true'] {
                border-color: var(--accent);
            }

            :host([embedded]) .trigger[aria-expanded='true'] {
                border-color: transparent;
            }

            :host([disabled]) .trigger {
                opacity: 0.6;
                cursor: not-allowed;
            }

            .trigger-text {
                flex: 1;
                min-width: 0;
                display: flex;
                align-items: center;
                text-align: left;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .trigger-text.with-label {
                flex-direction: column;
                align-items: flex-start;
                justify-content: center;
                gap: 2px;
                overflow: visible;
            }

            .trigger-label {
                font-size: var(--platform-date-picker-label-size, var(--text-sm));
                line-height: 1;
                color: var(--text-tertiary);
                font-weight: var(--font-normal);
            }

            .trigger-value {
                font-size: var(--platform-date-picker-value-size, var(--text-2xl));
                line-height: 1.05;
                color: var(--text-primary);
                font-weight: var(--font-medium);
            }

            .trigger-value.placeholder {
                color: var(--text-tertiary);
            }

            .trigger-placeholder {
                color: var(--text-tertiary);
            }

            .leading-icon {
                color: var(--text-tertiary);
                flex-shrink: 0;
            }

        `,
    ];

    constructor() {
        super();
        this.mode = 'date';
        this.selection = 'single';
        this.valueFormat = 'iso';
        this.value = null;
        this.min = '';
        this.max = '';
        this.step = 1;
        this.locale = 'ru-RU';
        this.disabled = false;
        this.readonly = false;
        this.required = false;
        this.placeholder = '';
        this.label = '';
        this.leadingIcon = 'calendar';
        this.embedded = false;
        this.hideTriggerIcon = false;
        this.open = false;

        const now = new Date();
        this._viewYear = now.getFullYear();
        this._viewMonth = now.getMonth();
        this._focusedDateIso = formatIsoDate(now);
        this._activeTimeTarget = 'single';
        this._singleDate = null;
        this._rangeStart = null;
        this._rangeEnd = null;
        this._singleTime = null;
        this._rangeStartTime = null;
        this._rangeEndTime = null;

        this._updatingFromExternal = false;
        this._handleDocumentPointerDown = this._onDocumentPointerDown.bind(this);
        this._handleScrollResize = this._onScrollResize.bind(this);
        this._portalHost = null;
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('pointerdown', this._handleDocumentPointerDown, true);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('pointerdown', this._handleDocumentPointerDown, true);
        this._unbindScrollResize();
        this._removePortal();
    }

    _bindScrollResize() {
        window.addEventListener('scroll', this._handleScrollResize, true);
        window.addEventListener('resize', this._handleScrollResize);
    }

    _unbindScrollResize() {
        window.removeEventListener('scroll', this._handleScrollResize, true);
        window.removeEventListener('resize', this._handleScrollResize);
    }

    _onScrollResize() {
        if (this.open) {
            this._positionPopup();
        }
    }

    _ensurePortal() {
        if (this._portalHost) return;
        this._portalHost = document.createElement('div');
        this._portalHost.style.position = 'fixed';
        this._portalHost.style.top = '0';
        this._portalHost.style.left = '0';
        this._portalHost.style.width = '0';
        this._portalHost.style.height = '0';
        this._portalHost.style.overflow = 'visible';
        this._portalHost.style.zIndex = String(nextModalLayerZIndex());
        this._portalHost.style.pointerEvents = 'none';
        document.body.appendChild(this._portalHost);
    }

    _removePortal() {
        if (this._portalHost) {
            render(nothing, this._portalHost);
            this._portalHost.remove();
            this._portalHost = null;
        }
    }

    static _portalCss = `
        .dp-portal-popup {
            position: fixed;
            width: 320px;
            max-width: min(90vw, 360px);
            background: var(--platform-date-picker-popup-bg, var(--glass-solid-medium, #fff));
            border: 1px solid var(--platform-date-picker-popup-border, var(--border-default, #e0e0e0));
            border-radius: var(--radius-xl, 16px);
            box-shadow: 0 8px 32px rgba(0,0,0,0.18);
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            pointer-events: auto;
            font-family: var(--font-family, system-ui, sans-serif);
            color: var(--text-primary, #1a1a1a);
            box-sizing: border-box;
        }
        .dp-portal-popup .calendar-header {
            display: flex; align-items: center; justify-content: space-between; gap: 8px;
        }
        .dp-portal-popup .month-label {
            font-size: var(--text-base, 16px); font-weight: 600; color: var(--text-primary, #1a1a1a);
            text-transform: capitalize;
        }
        .dp-portal-popup .nav-buttons { display: flex; align-items: center; gap: 4px; }
        .dp-portal-popup .icon-btn {
            width: 30px; height: 30px; border-radius: var(--radius-md, 8px);
            border: 1px solid var(--border-default, #e0e0e0); background: var(--glass-solid-medium, #f5f5f5);
            color: var(--text-secondary, #666); display: inline-flex; align-items: center; justify-content: center;
            cursor: pointer; font-size: 16px; line-height: 1;
        }
        .dp-portal-popup .icon-btn:hover { border-color: var(--accent, #5b6abf); color: var(--text-primary, #1a1a1a); }
        .dp-portal-popup .calendar-grid {
            display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 4px;
        }
        .dp-portal-popup .weekday {
            text-align: center; color: var(--text-tertiary, #999); font-size: var(--text-xs, 11px);
            font-weight: 600; padding-bottom: 4px; text-transform: uppercase;
        }
        .dp-portal-popup .day-btn {
            height: 34px; border: 1px solid transparent; border-radius: var(--radius-md, 8px);
            background: transparent; color: var(--text-primary, #1a1a1a); font-size: var(--text-sm, 14px);
            cursor: pointer;
        }
        .dp-portal-popup .day-btn:hover {
            border-color: var(--platform-date-picker-day-hover-border, var(--border-default, #e0e0e0));
            background: var(--platform-date-picker-day-hover-bg, rgba(0,0,0,0.04));
        }
        .dp-portal-popup .day-btn.muted { color: var(--text-disabled, #ccc); }
        .dp-portal-popup .day-btn.today { border-color: var(--accent, #5b6abf); }
        .dp-portal-popup .day-btn.selected { background: var(--accent, #5b6abf); color: var(--text-inverse, #fff); }
        .dp-portal-popup .day-btn.in-range {
            background: var(--platform-date-picker-range-bg, rgba(91,106,191,0.12));
            color: var(--platform-date-picker-range-text, var(--text-primary, #1a1a1a));
        }
        .dp-portal-popup .day-btn:focus-visible { outline: none; box-shadow: var(--focus-ring, 0 0 0 2px rgba(91,106,191,0.4)); }
        .dp-portal-popup .footer-row {
            display: flex; align-items: center; justify-content: space-between; gap: 8px;
        }
        .dp-portal-popup .footer-actions { display: inline-flex; align-items: center; gap: 8px; }
        .dp-portal-popup .text-btn {
            border: 1px solid var(--border-default, #e0e0e0); background: var(--glass-solid-medium, #f5f5f5);
            color: var(--text-secondary, #666); border-radius: var(--radius-md, 8px);
            padding: 4px 8px; font-size: var(--text-xs, 11px); cursor: pointer;
        }
        .dp-portal-popup .text-btn:hover { color: var(--text-primary, #1a1a1a); border-color: var(--accent, #5b6abf); }
        .dp-portal-popup .range-label { font-size: var(--text-xs, 11px); color: var(--text-tertiary, #999); }
        .dp-portal-popup .time-layout { display: grid; gap: 8px; }
        .dp-portal-popup .time-label { font-size: var(--text-xs, 11px); color: var(--text-tertiary, #999); text-transform: uppercase; }
        .dp-portal-popup .time-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
        .dp-portal-popup .time-field {
            display: flex; align-items: center; gap: 4px;
            border: 1px solid var(--border-default, #e0e0e0); border-radius: var(--radius-md, 8px);
            background: var(--glass-solid-medium, #f5f5f5); padding: 4px 8px;
        }
        .dp-portal-popup .time-input {
            width: 100%; border: none; background: transparent;
            color: var(--text-primary, #1a1a1a); font-size: var(--text-sm, 14px); outline: none;
        }
        .dp-portal-popup .divider { color: var(--text-tertiary, #999); font-size: var(--text-sm, 14px); }
    `;

    static _portalStyleSheet = null;

    static _ensurePortalStyleSheet() {
        if (PlatformDatePicker._portalStyleSheet) return;
        const style = document.createElement('style');
        style.setAttribute('data-dp-portal', '');
        style.textContent = PlatformDatePicker._portalCss;
        document.head.appendChild(style);
        PlatformDatePicker._portalStyleSheet = style;
    }

    _renderPortalPopup() {
        if (!this.open || !this._portalHost) return;
        PlatformDatePicker._ensurePortalStyleSheet();
        render(html`
            <div class="dp-portal-popup" role="dialog" aria-modal="false" aria-label="Выбор даты">
                ${this._renderCalendarSection()}
                ${this._renderTimeSection()}
                <div class="footer-row">
                    <div class="range-label">${this._rangeStatusLabel()}</div>
                    <div class="footer-actions">
                        <button type="button" class="text-btn" @click=${() => this._selectToday()}>Сегодня</button>
                        <button type="button" class="text-btn" @click=${() => this._clearValue()}>Очистить</button>
                        ${(this.mode === 'time' || this.mode === 'datetime') ? html`
                            <button type="button" class="text-btn" @click=${() => this._applyTimeChanges()}>Применить</button>
                        ` : ''}
                    </div>
                </div>
            </div>
        `, this._portalHost);

        const popup = this._portalHost.querySelector('.dp-portal-popup');
        if (popup) {
            const dayButton = popup.querySelector(`.day-btn[data-date="${this._focusedDateIso}"]`);
            if (dayButton instanceof HTMLElement) {
                dayButton.focus({ preventScroll: true });
            }
        }
    }

    willUpdate(changedProperties) {
        if (changedProperties.has('mode')) {
            assertEnumValue('mode', this.mode, ['date', 'datetime', 'time']);
        }
        if (changedProperties.has('selection')) {
            assertEnumValue('selection', this.selection, ['single', 'range']);
        }
        if (changedProperties.has('valueFormat')) {
            assertEnumValue('value-format', this.valueFormat, ['iso', 'date']);
        }
        if (changedProperties.has('value')) {
            this._syncInternalFromExternalValue();
        }
    }

    updated(changedProperties) {
        if (!this.open) return;
        this._renderPortalPopup();
        this._positionPopup();
    }

    _syncInternalFromExternalValue() {
        this._updatingFromExternal = true;
        this._singleDate = null;
        this._rangeStart = null;
        this._rangeEnd = null;
        this._singleTime = null;
        this._rangeStartTime = null;
        this._rangeEndTime = null;

        if (this.value === null || this.value === undefined || this.value === '') {
            this._updatingFromExternal = false;
            return;
        }

        if (this.selection === 'single') {
            this._syncSingleValue(this.value);
            this._updatingFromExternal = false;
            return;
        }

        if (typeof this.value !== 'object' || this.value === null) {
            throw new Error('Range value must be object {start, end}');
        }

        const startValue = this.value.start ?? null;
        const endValue = this.value.end ?? null;
        this._syncRangeValue(startValue, endValue);
        this._updatingFromExternal = false;
    }

    _syncSingleValue(value) {
        if (this.mode === 'time') {
            this._singleTime = this._parseIncomingTime(value);
            return;
        }
        const parsedDate = this._parseIncomingDateLike(value);
        this._singleDate = parsedDate;
        this._viewYear = parsedDate.getFullYear();
        this._viewMonth = parsedDate.getMonth();
        this._focusedDateIso = formatIsoDate(parsedDate);
    }

    _syncRangeValue(startValue, endValue) {
        if (this.mode === 'time') {
            this._rangeStartTime = startValue === null ? null : this._parseIncomingTime(startValue);
            this._rangeEndTime = endValue === null ? null : this._parseIncomingTime(endValue);
            return;
        }

        this._rangeStart = startValue === null ? null : this._parseIncomingDateLike(startValue);
        this._rangeEnd = endValue === null ? null : this._parseIncomingDateLike(endValue);

        const anchor = this._rangeStart ?? this._rangeEnd;
        if (anchor) {
            this._viewYear = anchor.getFullYear();
            this._viewMonth = anchor.getMonth();
            this._focusedDateIso = formatIsoDate(anchor);
        }
    }

    _parseIncomingDateLike(value) {
        if (this.valueFormat === 'date') {
            if (!(value instanceof Date)) {
                throw new Error('Value must be Date when value-format=date');
            }
            return normalizeDateForMode(this.mode, value);
        }
        if (typeof value !== 'string') {
            throw new Error('Value must be string when value-format=iso');
        }
        if (this.mode === 'date') {
            return parseIsoDate(value);
        }
        if (this.mode === 'datetime') {
            return parseIsoDateTime(value);
        }
        throw new Error('Date-like parser is unavailable for mode=time');
    }

    _parseIncomingTime(value) {
        if (this.valueFormat === 'date') {
            if (!(value instanceof Date)) {
                throw new Error('Time value must be Date when value-format=date');
            }
            return dateToMinutes(value);
        }
        if (typeof value !== 'string') {
            throw new Error('Time value must be string when value-format=iso');
        }
        return parseIsoTime(value);
    }

    _onDocumentPointerDown(event) {
        if (!this.open) {
            return;
        }
        const path = event.composedPath();
        if (path.includes(this)) return;
        if (this._portalHost && path.includes(this._portalHost)) return;
        this._closePopup();
    }

    _togglePopup() {
        if (this.disabled || this.readonly) {
            return;
        }
        this.open = !this.open;
        if (!this.open) {
            this._unbindScrollResize();
            this._removePortal();
            return;
        }
        const anchorDate = this._singleDate ?? this._rangeStart ?? this._rangeEnd ?? new Date();
        this._viewYear = anchorDate.getFullYear();
        this._viewMonth = anchorDate.getMonth();
        this._focusedDateIso = formatIsoDate(anchorDate);
        this._ensurePortal();
        this._bindScrollResize();
        this.updateComplete.then(() => {
            this._renderPortalPopup();
            this._positionPopup();
        });
    }

    _closePopup() {
        this.open = false;
        this._unbindScrollResize();
        this._removePortal();
    }

    _positionPopup() {
        if (!this._portalHost) return;
        const trigger = this.shadowRoot?.querySelector('.trigger');
        const popup = this._portalHost.querySelector('.dp-portal-popup');
        if (!trigger || !popup) return;

        const triggerRect = trigger.getBoundingClientRect();
        const popupHeight = popup.offsetHeight;
        const popupWidth = popup.offsetWidth;
        const gap = 8;

        const spaceBelow = window.innerHeight - triggerRect.bottom - gap;
        const spaceAbove = triggerRect.top - gap;
        const openBelow = spaceBelow >= popupHeight || spaceBelow >= spaceAbove;

        let top;
        if (openBelow) {
            top = triggerRect.bottom + gap;
        } else {
            top = triggerRect.top - popupHeight - gap;
        }

        let left = triggerRect.left;
        if (left + popupWidth > window.innerWidth - 8) {
            left = window.innerWidth - popupWidth - 8;
        }
        if (left < 8) left = 8;

        popup.style.top = `${top}px`;
        popup.style.left = `${left}px`;
    }

    _shiftMonth(delta) {
        const base = new Date(this._viewYear, this._viewMonth, 1);
        base.setMonth(base.getMonth() + delta);
        this._viewYear = base.getFullYear();
        this._viewMonth = base.getMonth();
    }

    _monthLabel() {
        const date = new Date(this._viewYear, this._viewMonth, 1);
        return date.toLocaleDateString(this.locale, {
            month: 'long',
            year: 'numeric',
        });
    }

    _weekdayLabels() {
        const labels = [];
        const monday = dateAtWeekStart(new Date(2025, 0, 6));
        for (let index = 0; index < DAYS_IN_WEEK; index += 1) {
            const value = new Date(monday);
            value.setDate(monday.getDate() + index);
            labels.push(value.toLocaleDateString(this.locale, { weekday: 'short' }));
        }
        return labels;
    }

    _calendarCells() {
        const firstDay = new Date(this._viewYear, this._viewMonth, 1);
        const firstWeekDate = dateAtWeekStart(firstDay);
        const cells = [];
        for (let index = 0; index < 42; index += 1) {
            const cellDate = new Date(firstWeekDate);
            cellDate.setDate(firstWeekDate.getDate() + index);
            cells.push({
                date: cellDate,
                iso: formatIsoDate(cellDate),
                inCurrentMonth: cellDate.getMonth() === this._viewMonth,
            });
        }
        return cells;
    }

    _isSelected(cellDate) {
        if (this.selection === 'single') {
            if (this.mode === 'time') {
                return false;
            }
            if (!this._singleDate) {
                return false;
            }
            return compareDateOnly(cellDate, this._singleDate) === 0;
        }

        if (!this._rangeStart && !this._rangeEnd) {
            return false;
        }
        if (this._rangeStart && compareDateOnly(cellDate, this._rangeStart) === 0) {
            return true;
        }
        if (this._rangeEnd && compareDateOnly(cellDate, this._rangeEnd) === 0) {
            return true;
        }
        return false;
    }

    _isInRange(cellDate) {
        if (this.selection !== 'range' || !this._rangeStart || !this._rangeEnd) {
            return false;
        }
        const compareStart = compareDateOnly(cellDate, this._rangeStart);
        const compareEnd = compareDateOnly(cellDate, this._rangeEnd);
        return compareStart > 0 && compareEnd < 0;
    }

    _isToday(cellDate) {
        const today = new Date();
        return compareDateOnly(cellDate, today) === 0;
    }

    _commitDateSelection(date, finalize = true) {
        if (this.selection === 'single') {
            this._singleDate = normalizeDateForMode(this.mode, date);
            this._setExposedValueFromInternal();
            this._emitValueEvent('input');
            if (finalize) {
                this._emitValueEvent('change');
                if (this.mode === 'date') {
                    this._closePopup();
                }
            }
            return;
        }

        if (!this._rangeStart || (this._rangeStart && this._rangeEnd)) {
            this._rangeStart = normalizeDateForMode(this.mode, date);
            this._rangeEnd = null;
            this._activeTimeTarget = 'start';
            this._setExposedValueFromInternal();
            this._emitValueEvent('input');
            return;
        }

        const normalizedDate = normalizeDateForMode(this.mode, date);
        if (compareDateOnly(normalizedDate, this._rangeStart) < 0) {
            this._rangeEnd = this._rangeStart;
            this._rangeStart = normalizedDate;
        } else {
            this._rangeEnd = normalizedDate;
        }
        this._activeTimeTarget = 'end';
        this._setExposedValueFromInternal();
        this._emitValueEvent('input');
        if (finalize) {
            this._emitValueEvent('change');
            if (this.mode === 'date') {
                this._closePopup();
            }
        }
    }

    _onDayClick(cell) {
        if (!cell.inCurrentMonth) {
            this._viewYear = cell.date.getFullYear();
            this._viewMonth = cell.date.getMonth();
        }
        this._focusedDateIso = cell.iso;
        this._commitDateSelection(cell.date, true);
    }

    _onGridKeyDown(event) {
        const focused = parseIsoDate(this._focusedDateIso);
        if (event.key === 'Escape') {
            event.preventDefault();
            this._closePopup();
            return;
        }
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            this._commitDateSelection(focused, true);
            return;
        }

        let changed = false;
        if (event.key === 'ArrowLeft') {
            focused.setDate(focused.getDate() - 1);
            changed = true;
        } else if (event.key === 'ArrowRight') {
            focused.setDate(focused.getDate() + 1);
            changed = true;
        } else if (event.key === 'ArrowUp') {
            focused.setDate(focused.getDate() - 7);
            changed = true;
        } else if (event.key === 'ArrowDown') {
            focused.setDate(focused.getDate() + 7);
            changed = true;
        } else if (event.key === 'Home') {
            const day = focused.getDay();
            const shift = day === 0 ? 6 : day - 1;
            focused.setDate(focused.getDate() - shift);
            changed = true;
        } else if (event.key === 'End') {
            const day = focused.getDay();
            const shift = day === 0 ? 0 : 7 - day;
            focused.setDate(focused.getDate() + shift);
            changed = true;
        } else if (event.key === 'PageUp') {
            if (event.shiftKey) {
                focused.setFullYear(focused.getFullYear() - 1);
            } else {
                focused.setMonth(focused.getMonth() - 1);
            }
            changed = true;
        } else if (event.key === 'PageDown') {
            if (event.shiftKey) {
                focused.setFullYear(focused.getFullYear() + 1);
            } else {
                focused.setMonth(focused.getMonth() + 1);
            }
            changed = true;
        }

        if (!changed) {
            return;
        }
        event.preventDefault();
        this._focusedDateIso = formatIsoDate(focused);
        this._viewYear = focused.getFullYear();
        this._viewMonth = focused.getMonth();
    }

    _setTimeValue(minutesValue, target) {
        if (this.mode === 'datetime') {
            if (minutesValue === null) {
                return;
            }
            if (!Number.isInteger(minutesValue) || minutesValue < 0 || minutesValue > 1439) {
                throw new Error('Time value must be integer from 0 to 1439');
            }
            if (this.selection === 'single') {
                if (!this._singleDate) {
                    return;
                }
                this._singleDate = applyMinutes(this._singleDate, minutesValue);
                return;
            }
            if (target === 'start') {
                if (!this._rangeStart) {
                    return;
                }
                this._rangeStart = applyMinutes(this._rangeStart, minutesValue);
                return;
            }
            if (!this._rangeEnd) {
                return;
            }
            this._rangeEnd = applyMinutes(this._rangeEnd, minutesValue);
            return;
        }
        if (minutesValue === null) {
            if (target === 'single') {
                this._singleTime = null;
            } else if (target === 'start') {
                this._rangeStartTime = null;
            } else {
                this._rangeEndTime = null;
            }
            return;
        }
        if (!Number.isInteger(minutesValue) || minutesValue < 0 || minutesValue > 1439) {
            throw new Error('Time value must be integer from 0 to 1439');
        }
        if (target === 'single') {
            this._singleTime = minutesValue;
        } else if (target === 'start') {
            this._rangeStartTime = minutesValue;
        } else {
            this._rangeEndTime = minutesValue;
        }
    }

    _targetTimeValue(target) {
        if (this.mode === 'datetime') {
            if (this.selection === 'single') {
                return this._singleDate ? dateToMinutes(this._singleDate) : null;
            }
            if (target === 'start') {
                return this._rangeStart ? dateToMinutes(this._rangeStart) : null;
            }
            return this._rangeEnd ? dateToMinutes(this._rangeEnd) : null;
        }
        if (target === 'single') {
            return this._singleTime;
        }
        if (target === 'start') {
            return this._rangeStartTime;
        }
        return this._rangeEndTime;
    }

    _onTimePartInput(target, part, event) {
        const raw = event.target.value;
        if (raw === '') {
            return;
        }
        const asNumber = Number(raw);
        if (!Number.isInteger(asNumber)) {
            return;
        }

        const current = this._targetTimeValue(target) ?? 0;
        const currentHours = Math.floor(current / 60);
        const currentMinutes = current % 60;
        const nextHours = part === 'hours' ? asNumber : currentHours;
        const nextMinutes = part === 'minutes' ? asNumber : currentMinutes;

        if (nextHours < 0 || nextHours > 23) {
            return;
        }
        if (nextMinutes < 0 || nextMinutes > 59) {
            return;
        }

        this._setTimeValue((nextHours * 60) + nextMinutes, target);
        this._setExposedValueFromInternal();
        this._emitValueEvent('input');
    }

    _applyTimeChanges() {
        this._setExposedValueFromInternal();
        this._emitValueEvent('change');
        if (this.mode === 'time' || this.mode === 'datetime') {
            this._closePopup();
        }
    }

    _selectToday() {
        if (this.mode === 'time') {
            const now = new Date();
            const value = (now.getHours() * 60) + now.getMinutes();
            if (this.selection === 'single') {
                this._singleTime = value;
            } else {
                this._rangeStartTime = value;
                this._rangeEndTime = value;
            }
            this._setExposedValueFromInternal();
            this._emitValueEvent('input');
            this._emitValueEvent('change');
            return;
        }
        const now = new Date();
        this._viewYear = now.getFullYear();
        this._viewMonth = now.getMonth();
        this._focusedDateIso = formatIsoDate(now);
        if (this.selection === 'range' && this.mode === 'date') {
            const normalized = normalizeDateForMode(this.mode, now);
            this._rangeStart = normalized;
            this._rangeEnd = normalized;
            this._setExposedValueFromInternal();
            this._emitValueEvent('input');
            this._emitValueEvent('change');
            this._closePopup();
            return;
        }
        this._commitDateSelection(now, true);
    }

    _clearValue() {
        this._singleDate = null;
        this._rangeStart = null;
        this._rangeEnd = null;
        this._singleTime = null;
        this._rangeStartTime = null;
        this._rangeEndTime = null;
        this.value = this.selection === 'single' ? null : { start: null, end: null };
        this._emitValueEvent('input');
        this._emitValueEvent('change');
    }

    _setExposedValueFromInternal() {
        const previousFlag = this._updatingFromExternal;
        this._updatingFromExternal = true;
        this.value = this._buildExternalValue();
        this._updatingFromExternal = previousFlag;
    }

    _buildExternalValue() {
        if (this.selection === 'single') {
            return this._buildExternalSingleValue();
        }
        return this._buildExternalRangeValue();
    }

    _buildExternalSingleValue() {
        if (this.mode === 'time') {
            if (this._singleTime === null) {
                return null;
            }
            if (this.valueFormat === 'date') {
                return minutesToDate(this._singleTime);
            }
            return formatIsoTime(this._singleTime);
        }

        if (!this._singleDate) {
            return null;
        }
        if (this.valueFormat === 'date') {
            return cloneDate(this._singleDate);
        }
        if (this.mode === 'date') {
            return formatIsoDate(this._singleDate);
        }
        return formatIsoDateTime(this._singleDate);
    }

    _buildExternalRangeValue() {
        if (this.mode === 'time') {
            const startValue = this._rangeStartTime === null
                ? null
                : (this.valueFormat === 'date' ? minutesToDate(this._rangeStartTime) : formatIsoTime(this._rangeStartTime));
            const endValue = this._rangeEndTime === null
                ? null
                : (this.valueFormat === 'date' ? minutesToDate(this._rangeEndTime) : formatIsoTime(this._rangeEndTime));
            return toRangeValue(startValue, endValue, this.valueFormat);
        }

        const startValue = this._rangeStart === null
            ? null
            : (this.valueFormat === 'date'
                ? cloneDate(this._rangeStart)
                : (this.mode === 'date' ? formatIsoDate(this._rangeStart) : formatIsoDateTime(this._rangeStart)));

        const endValue = this._rangeEnd === null
            ? null
            : (this.valueFormat === 'date'
                ? cloneDate(this._rangeEnd)
                : (this.mode === 'date' ? formatIsoDate(this._rangeEnd) : formatIsoDateTime(this._rangeEnd)));

        return toRangeValue(startValue, endValue, this.valueFormat);
    }

    _emitValueEvent(eventName) {
        if (this._updatingFromExternal) {
            return;
        }
        this.dispatchEvent(new CustomEvent(eventName, {
            detail: {
                value: this.value,
                mode: this.mode,
                selection: this.selection,
                valueFormat: this.valueFormat,
            },
            bubbles: true,
            composed: true,
        }));
    }

    _displayValue() {
        if (this.selection === 'single') {
            return this._displaySingleValue();
        }
        return this._displayRangeValue();
    }

    _displaySingleValue() {
        if (this.mode === 'time') {
            if (this._singleTime === null) {
                return '';
            }
            return formatIsoTime(this._singleTime);
        }
        if (!this._singleDate) {
            return '';
        }
        if (this.mode === 'date') {
            return this._singleDate.toLocaleDateString(this.locale);
        }
        return `${this._singleDate.toLocaleDateString(this.locale)} ${pad2(this._singleDate.getHours())}:${pad2(this._singleDate.getMinutes())}`;
    }

    _displayRangeValue() {
        if (this.mode === 'time') {
            const start = this._rangeStartTime === null ? '' : formatIsoTime(this._rangeStartTime);
            const end = this._rangeEndTime === null ? '' : formatIsoTime(this._rangeEndTime);
            if (!start && !end) {
                return '';
            }
            return `${start || '...'} - ${end || '...'}`;
        }

        const start = this._rangeStart ? this._rangeStart.toLocaleDateString(this.locale) : '';
        const end = this._rangeEnd ? this._rangeEnd.toLocaleDateString(this.locale) : '';
        if (!start && !end) {
            return '';
        }
        if (this._rangeStart && this._rangeEnd && compareDateOnly(this._rangeStart, this._rangeEnd) === 0) {
            return start;
        }
        return `${start || '...'} - ${end || '...'}`;
    }

    _placeholderValue() {
        if (this.placeholder) {
            return this.placeholder;
        }
        if (this.selection === 'range') {
            if (this.mode === 'time') {
                return 'Выберите диапазон времени';
            }
            return 'Выберите диапазон дат';
        }
        if (this.mode === 'time') {
            return 'Выберите время';
        }
        if (this.mode === 'datetime') {
            return 'Выберите дату и время';
        }
        return 'Выберите дату';
    }

    _rangeStatusLabel() {
        if (this.selection !== 'range') {
            return '';
        }
        if (!this._rangeStart) {
            return 'Сначала выберите начальную дату';
        }
        if (!this._rangeEnd) {
            return 'Выберите конечную дату';
        }
        return 'Диапазон выбран';
    }

    _renderCalendarSection() {
        if (this.mode === 'time') {
            return null;
        }
        const weekLabels = this._weekdayLabels();
        const cells = this._calendarCells();
        return html`
            <div class="calendar-header">
                <div class="month-label" aria-live="polite">${this._monthLabel()}</div>
                <div class="nav-buttons">
                    <button type="button" class="icon-btn" @click=${() => this._shiftMonth(-1)} aria-label="Предыдущий месяц">
                        <platform-icon name="chevron-left" size="16"></platform-icon>
                    </button>
                    <button type="button" class="icon-btn" @click=${() => this._shiftMonth(1)} aria-label="Следующий месяц">
                        <platform-icon name="chevron-right" size="16"></platform-icon>
                    </button>
                </div>
            </div>
            <div class="calendar-grid" role="grid" aria-label="Календарь" @keydown=${(e) => this._onGridKeyDown(e)}>
                ${weekLabels.map((label) => html`<div class="weekday">${label}</div>`)}
                ${cells.map((cell) => {
                    const classes = [
                        'day-btn',
                        !cell.inCurrentMonth ? 'muted' : '',
                        this._isToday(cell.date) ? 'today' : '',
                        this._isSelected(cell.date) ? 'selected' : '',
                        this._isInRange(cell.date) ? 'in-range' : '',
                    ].filter(Boolean).join(' ');
                    return html`
                        <button
                            type="button"
                            class=${classes}
                            data-date=${cell.iso}
                            @click=${() => this._onDayClick(cell)}
                            tabindex=${cell.iso === this._focusedDateIso ? '0' : '-1'}
                            aria-selected=${this._isSelected(cell.date) ? 'true' : 'false'}
                        >
                            ${cell.date.getDate()}
                        </button>
                    `;
                })}
            </div>
        `;
    }

    _renderTimeField(target, label) {
        const value = this._targetTimeValue(target);
        const hours = value === null ? '' : String(Math.floor(value / 60));
        const minutes = value === null ? '' : String(value % 60);
        return html`
            <div class="time-layout">
                <div class="time-label">${label}</div>
                <div class="time-row">
                    <label class="time-field">
                        <span class="divider">ч</span>
                        <input
                            class="time-input"
                            type="number"
                            min="0"
                            max="23"
                            .value=${hours}
                            @input=${(event) => this._onTimePartInput(target, 'hours', event)}
                        />
                    </label>
                    <label class="time-field">
                        <span class="divider">м</span>
                        <input
                            class="time-input"
                            type="number"
                            min="0"
                            max="59"
                            .value=${minutes}
                            @input=${(event) => this._onTimePartInput(target, 'minutes', event)}
                        />
                    </label>
                </div>
            </div>
        `;
    }

    _renderTimeSection() {
        if (this.mode !== 'time' && this.mode !== 'datetime') {
            return null;
        }
        if (this.selection === 'single') {
            return this._renderTimeField('single', 'Время');
        }
        return html`
            ${this._renderTimeField('start', 'Начало')}
            ${this._renderTimeField('end', 'Конец')}
        `;
    }

    render() {
        const displayValue = this._displayValue();
        const hasLabel = typeof this.label === 'string' && this.label.trim().length > 0;
        const showTrailingIcon = !this.hideTriggerIcon && !hasLabel;
        return html`
            <button
                type="button"
                class="trigger ${hasLabel ? 'with-label' : ''}"
                @click=${this._togglePopup}
                aria-expanded=${this.open ? 'true' : 'false'}
                ?disabled=${this.disabled}
            >
                ${hasLabel ? html`
                    <platform-icon class="leading-icon" name=${this.leadingIcon || 'calendar'} size="22"></platform-icon>
                ` : ''}
                <span class="trigger-text ${hasLabel ? 'with-label' : ''} ${displayValue ? '' : 'trigger-placeholder'}">
                    ${hasLabel ? html`
                        <span class="trigger-label">${this.label}</span>
                        <span class="trigger-value ${displayValue ? '' : 'placeholder'}">${displayValue || this._placeholderValue()}</span>
                    ` : html`
                        ${displayValue || this._placeholderValue()}
                    `}
                </span>
                ${showTrailingIcon ? html`
                    <platform-icon name=${this.open ? 'chevron-up' : 'calendar'} size="16"></platform-icon>
                ` : ''}
            </button>
        `;
    }
}

customElements.define('platform-date-picker', PlatformDatePicker);
