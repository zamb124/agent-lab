/**
 * EventLog - упорядоченный лог всех событий, прошедших через EventBus.
 *
 * Лог — источник правды. State пересобирается через reduce(events, initialState).
 * In-memory ring-буфер фиксированной ёмкости; для devtools/replay в dev-режиме
 * полный лог дополнительно копится в _devTrail (без ограничения).
 */

const DEFAULT_CAPACITY = 1000;

export class EventLog {
    constructor({ capacity = DEFAULT_CAPACITY, devMode = false } = {}) {
        this._capacity = capacity;
        this._devMode = devMode;
        this._buffer = [];
        this._devTrail = devMode ? [] : null;
        this._counter = 0;
    }

    append(event) {
        this._counter += 1;
        this._buffer.push(event);
        if (this._buffer.length > this._capacity) {
            this._buffer.splice(0, this._buffer.length - this._capacity);
        }
        if (this._devTrail) {
            this._devTrail.push(event);
        }
    }

    get size() {
        return this._counter;
    }

    get bufferLength() {
        return this._buffer.length;
    }

    /** Снимок последних N событий (по умолчанию весь буфер). */
    snapshot(limit) {
        if (typeof limit !== 'number' || limit <= 0 || limit >= this._buffer.length) {
            return this._buffer.slice();
        }
        return this._buffer.slice(this._buffer.length - limit);
    }

    /** Полный dev-trail (только в devMode). Используется devtools. */
    devTrail() {
        if (!this._devTrail) {
            throw new Error('EventLog.devTrail() unavailable: dev mode is off');
        }
        return this._devTrail.slice();
    }

    /** Очистить всё. Только для тестов. */
    reset() {
        this._buffer = [];
        if (this._devTrail) {
            this._devTrail = [];
        }
        this._counter = 0;
    }
}
