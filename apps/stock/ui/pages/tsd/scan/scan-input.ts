/**
 * Ввод сканов ТСД: аппаратный сканер как клавиатура + ручной ввод.
 *
 * HID-сканер шлёт символы пачкой (межсимвольная пауза в разы меньше
 * человеческой) и завершает Enter. Контроллер отличает пачку от ручного
 * набора по интервалу: символы внутри окна `_burstMs` — скан, накопление
 * в буфере; Enter при непустом буфере — завершение кода. Медленный ввод
 * игнорируется, чтобы сканер не перехватывал обычную клавиатуру в формах.
 */

export const TSD_SCAN_MIN_LENGTH = 3;
const DEFAULT_BURST_MS = 40;

export class TsdScanInput {
    private _buffer = '';
    private _lastKeyAt = 0;
    private _burst = false;
    private _timer: ReturnType<typeof setTimeout> | null = null;
    private readonly _burstMs: number;
    private readonly _onScan: (code: string) => void;
    private readonly _target: Window;
    private readonly _keyHandler: (event: KeyboardEvent) => void;
    private _attached = false;

    constructor(onScan: (code: string) => void, opts: { burstMs?: number; target?: Window } = {}) {
        this._onScan = onScan;
        this._burstMs = opts.burstMs ?? DEFAULT_BURST_MS;
        this._target = opts.target ?? window;
        this._keyHandler = (event) => this._onKey(event);
    }

    attach(): void {
        if (this._attached) return;
        this._target.addEventListener('keydown', this._keyHandler as EventListener, true);
        this._attached = true;
    }

    detach(): void {
        if (!this._attached) return;
        this._target.removeEventListener('keydown', this._keyHandler as EventListener, true);
        this._attached = false;
        this._reset();
    }

    /** Ручной ввод из поля на экране — тот же контракт, без эвристики. */
    submit(code: string): void {
        const normalized = code.trim();
        if (normalized.length < TSD_SCAN_MIN_LENGTH) return;
        this._onScan(normalized);
    }

    private _onKey(event: KeyboardEvent): void {
        if (event.ctrlKey || event.metaKey || event.altKey) return;
        const now = Date.now();
        if (event.key === 'Enter') {
            if (this._burst && this._buffer.length >= TSD_SCAN_MIN_LENGTH) {
                event.preventDefault();
                event.stopPropagation();
                const code = this._buffer;
                this._reset();
                this._onScan(code);
                return;
            }
            this._reset();
            return;
        }
        if (event.key.length !== 1) {
            this._reset();
            return;
        }
        const gap = now - this._lastKeyAt;
        this._lastKeyAt = now;
        if (gap > this._burstMs * 4) this._reset();
        this._buffer += event.key;
        this._fastCount = gap <= this._burstMs ? this._fastCount + 1 : 0;
        if (this._fastCount >= 2) this._burst = true;
        if (this._timer !== null) clearTimeout(this._timer);
        this._timer = setTimeout(() => this._reset(), this._burstMs * 4);
    }

    private _fastCount = 0;

    private _reset(): void {
        this._buffer = '';
        this._burst = false;
        this._fastCount = 0;
        if (this._timer !== null) {
            clearTimeout(this._timer);
            this._timer = null;
        }
    }
}
