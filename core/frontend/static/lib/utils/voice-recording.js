/**
 * Утилиты записи голоса через MediaRecorder.
 * Общие для CRM (daily-notes, note-content) и Sync (message-composer).
 */

/**
 * WKWebView и часть встроенных браузеров отдают только legacy getUserMedia.
 * @param {MediaStreamConstraints} constraints
 * @returns {Promise<MediaStream>}
 */
export function getUserMediaCompat(constraints) {
    const nav = typeof navigator !== 'undefined' ? navigator : null;
    if (nav?.mediaDevices && typeof nav.mediaDevices.getUserMedia === 'function') {
        return nav.mediaDevices.getUserMedia(constraints);
    }
    const legacy = nav && (nav.getUserMedia || nav.webkitGetUserMedia || nav.mozGetUserMedia);
    if (typeof legacy === 'function') {
        return new Promise((resolve, reject) => {
            legacy.call(nav, constraints, resolve, reject);
        });
    }
    return Promise.reject(new Error('NO_GET_USER_MEDIA'));
}

/**
 * @returns {boolean}
 */
export function hasGetUserMediaApi() {
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
export function pickVoiceMimeType() {
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
