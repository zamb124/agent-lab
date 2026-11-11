/**
 * Скан через камеру ТСД (`<stock-tsd-camera-scanner>`).
 *
 * Progressive enhancement: элемент рендерит оверлей только когда открыт;
 * доступность решает страница — кнопка показывается лишь при наличии
 * `BarcodeDetector` в рантайме (Android Chrome, Safari 17+). Поток
 * `environment`-камеры гоняется через rAF-цикл `detect`, первый код
 * диспатчит `tsd-scan` и закрывает оверлей.
 */

import { html, css } from 'lit';
import type { PropertyDeclarations } from 'lit';
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
    return typeof window !== 'undefined' && window.BarcodeDetector !== undefined && typeof navigator.mediaDevices?.getUserMedia === 'function';
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
        const ctor = window.BarcodeDetector;
        if (ctor === undefined) {
            this._error = true;
            return;
        }
        try {
            this._stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
        } catch {
            this._error = true;
            return;
        }
        await this.updateComplete;
        const video = this.renderRoot.querySelector('video');
        if (!(video instanceof HTMLVideoElement)) {
            this._stop();
            return;
        }
        this._video = video;
        video.srcObject = this._stream;
        await video.play();
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

    private _stop(): void {
        cancelAnimationFrame(this._raf);
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
