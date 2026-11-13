/**
 * Скан через камеру ТСД (`<stock-tsd-camera-scanner>`).
 *
 * Progressive enhancement: элемент рендерит оверлей только когда открыт;
 * кнопка показывается при наличии `getUserMedia` в рантайме. Быстрый
 * путь — нативный `BarcodeDetector` (Android Chrome); где его нет
 * (iOS Safari, старые WebView) лениво подгружается ZXing-декодер —
 * чанк `@zxing/browser` доезжает только в таких браузерах. Поток
 * `environment`-камеры один на оба пути, первый код диспатчит
 * `tsd-scan` и закрывает оверлей.
 */

import { html, css } from 'lit';
import type { PropertyDeclarations } from 'lit';
import type { IScannerControls } from '@zxing/browser';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

interface TsdBarcodeDetection {
    rawValue: string;
}

interface TsdBarcodeDetectorCtor {
    new (options?: { formats?: string[] }): { detect(source: CanvasImageSource): Promise<TsdBarcodeDetection[]> };
}

declare global {
    interface Window {
        BarcodeDetector?: TsdBarcodeDetectorCtor;
    }
}

export function tsdCameraScanSupported(): boolean {
    return typeof window !== 'undefined' && typeof navigator.mediaDevices?.getUserMedia === 'function';
}

export class StockTsdCameraScanner extends PlatformElement {
    static override properties: PropertyDeclarations = {
        active: { type: Boolean },
        _error: { state: true },
    };

    active = false;
    private _error = false;

    private _stream: MediaStream | null = null;
    private _raf = 0;
    private _video: HTMLVideoElement | null = null;
    private _zxing: IScannerControls | null = null;
    private _generation = 0;

    static override styles = [
        PlatformElement.styles,
        css`
        .overlay {
            position: fixed;
            inset: 0;
            z-index: 1000;
            display: flex;
            flex-direction: column;
            background: #000;
        }
        video {
            flex: 1;
            width: 100%;
            object-fit: cover;
        }
        .frame {
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            pointer-events: none;
        }
        .reticle {
            width: min(70vw, 320px);
            height: min(40vh, 200px);
            border: 3px solid var(--accent, #4f7cff);
            border-radius: 16px;
            box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.35);
        }
        .close {
            position: absolute;
            top: calc(var(--platform-safe-top, 0px) + 16px);
            right: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            width: var(--tsd-touch-min, 56px);
            height: var(--tsd-touch-min, 56px);
            border: none;
            border-radius: 50%;
            background: rgba(0, 0, 0, 0.55);
            color: #fff;
            cursor: pointer;
        }
        .error {
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            font-size: 18px;
            padding: 24px;
            text-align: center;
        }
    `,
    ];

    override updated(changed: Map<string, unknown>): void {
        if (changed.has('active')) {
            if (this.active) void this._start();
            else this._stop();
        }
    }

    override disconnectedCallback(): void {
        this._stop();
        super.disconnectedCallback();
    }

    private async _start(): Promise<void> {
        this._error = false;
        // Быстрый open→close→open запускает второй getUserMedia до
        // завершения первого — без поколения первый поток теряется
        // и камера горит вечно в WebView.
        const generation = ++this._generation;
        let stream: MediaStream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
        } catch {
            if (generation === this._generation) this._error = true;
            return;
        }
        if (generation !== this._generation) {
            for (const track of stream.getTracks()) track.stop();
            return;
        }
        this._stream = stream;
        await this.updateComplete;
        const video = this.renderRoot.querySelector('video');
        if (!(video instanceof HTMLVideoElement)) {
            this._stop();
            return;
        }
        this._video = video;
        video.srcObject = this._stream;
        try {
            await video.play();
        } catch {
            // autoplay-политика WebView: без кадров detect-цикл молчал бы вечно
            this._stop();
            this._error = true;
            return;
        }
        const ctor = window.BarcodeDetector;
        if (ctor === undefined) {
            await this._startZxing(video, generation);
            return;
        }
        const detector = new ctor();
        const tick = async (): Promise<void> => {
            if (this._video === null || !this.active) return;
            try {
                const found = await detector.detect(this._video);
                const first = found[0];
                if (first !== undefined && first.rawValue.length > 0) {
                    this.emit('tsd-scan', { code: first.rawValue });
                    this.active = false;
                    return;
                }
            } catch {
                // кадр не готов — следующий тик
            }
            this._raf = requestAnimationFrame(() => void tick());
        };
        this._raf = requestAnimationFrame(() => void tick());
    }

    /** Декодер на ZXing для браузеров без BarcodeDetector (iOS Safari):
     *  чанк `@zxing/browser` тянется лениво и только в таком рантайме.
     *  Поток уже наш — `decodeFromStream` его не открывает заново. */
    private async _startZxing(video: HTMLVideoElement, generation: number): Promise<void> {
        const stream = this._stream;
        if (stream === null) return;
        try {
            const { BrowserMultiFormatReader } = await import('@zxing/browser');
            if (generation !== this._generation) return;
            const reader = new BrowserMultiFormatReader();
            const controls = await reader.decodeFromStream(stream, video, (result) => {
                if (!this.active) return;
                const code = result?.getText() ?? '';
                if (code !== '') {
                    this.emit('tsd-scan', { code });
                    this.active = false;
                }
            });
            // Оверлей закрыли, пока декодер поднимался — поток уже
            // остановлен _stop, контролы тушим здесь же.
            if (generation !== this._generation) {
                controls.stop();
                return;
            }
            this._zxing = controls;
        } catch {
            if (generation === this._generation) {
                this._stop();
                this._error = true;
            }
        }
    }

    private _stop(): void {
        this._generation += 1;
        cancelAnimationFrame(this._raf);
        this._zxing?.stop();
        this._zxing = null;
        if (this._video !== null) {
            this._video.srcObject = null;
            this._video = null;
        }
        if (this._stream !== null) {
            for (const track of this._stream.getTracks()) track.stop();
            this._stream = null;
        }
    }

    private _close(): void {
        this.active = false;
        this.emit('tsd-scan-close');
    }

    override render() {
        if (!this.active) return html``;
        return html`
            <div class="overlay">
                <video playsinline muted></video>
                <div class="frame"><div class="reticle"></div></div>
                ${this._error ? html`<div class="error"><slot name="error"></slot></div>` : ''}
                <button class="close" @click=${() => this._close()} aria-label="close">
                    <platform-icon name="close" size="26"></platform-icon>
                </button>
            </div>
        `;
    }
}

customElements.define('stock-tsd-camera-scanner', StockTsdCameraScanner);
