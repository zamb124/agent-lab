/**
 * Утилиты записи голоса через MediaRecorder.
 * Sync message-composer (голосовые сообщения).
 */

/**
 * WKWebView и часть встроенных браузеров отдают только legacy getUserMedia.
 * @param {MediaStreamConstraints} constraints
 * @returns {Promise<MediaStream>}
 */
declare global {
    interface Navigator {
        getUserMedia?: (c: MediaStreamConstraints, ok: (s: MediaStream) => void, err: (e: unknown) => void) => void;
        webkitGetUserMedia?: (c: MediaStreamConstraints, ok: (s: MediaStream) => void, err: (e: unknown) => void) => void;
        mozGetUserMedia?: (c: MediaStreamConstraints, ok: (s: MediaStream) => void, err: (e: unknown) => void) => void;
    }
}

export function getUserMediaCompat(constraints: MediaStreamConstraints): Promise<MediaStream> {
    const nav = typeof navigator !== 'undefined' ? navigator : null;
    if (nav?.mediaDevices && typeof nav.mediaDevices.getUserMedia === 'function') {
        return nav.mediaDevices.getUserMedia(constraints);
    }
    const legacy = nav && (nav.getUserMedia || nav.webkitGetUserMedia || nav.mozGetUserMedia);
    if (typeof legacy === 'function') {
        return new Promise<MediaStream>((resolve, reject) => {
            legacy.call(nav, constraints, resolve, reject);
        });
    }
    return Promise.reject(new Error('NO_GET_USER_MEDIA'));
}

/**
 * @returns {boolean}
 */
export function hasGetUserMediaApi(): boolean {
    const nav = typeof navigator !== 'undefined' ? navigator : null;
    if (nav?.mediaDevices && typeof nav.mediaDevices.getUserMedia === 'function') {
        return true;
    }
    return Boolean(nav && (nav.getUserMedia || nav.webkitGetUserMedia || nav.mozGetUserMedia));
}

/**
 * Safari / iOS не декодирует WebM; приоритет MP4/AAC.
 * @returns {string}
 */
export function pickVoiceMimeType(): string {
    if (typeof MediaRecorder === 'undefined') {
        return '';
    }
    const variants = [
        'audio/mp4;codecs=mp4a.40.2',
        'audio/mp4',
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
    ];
    for (const variant of variants) {
        if (MediaRecorder.isTypeSupported(variant)) {
            return variant;
        }
    }
    return '';
}
