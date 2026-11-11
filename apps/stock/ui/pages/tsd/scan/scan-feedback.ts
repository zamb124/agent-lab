/**
 * Обратная связь скана ТСД: звук + вибрация + цветовая вспышка.
 *
 * Звук синтезируется WebAudio (без ассетов): ok — короткий высокий сигнал,
 * error — низкий двойной. Вибрация — `navigator.vibrate` там, где есть
 * (Android; на iOS безопасно no-op). Вспышку рисует экран — контроллер
 * только сообщает исход, DOM-эффект остаётся за страницей.
 */

export type TsdScanOutcome = 'ok' | 'error';

let _audioCtx: AudioContext | null = null;

function _beep(outcome: TsdScanOutcome): void {
    if (typeof AudioContext === 'undefined') return;
    if (_audioCtx === null) _audioCtx = new AudioContext();
    const ctx = _audioCtx;
    if (ctx.state === 'suspended') void ctx.resume();
    const play = (freq: number, startAt: number, duration: number): void => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'square';
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.08, startAt);
        gain.gain.exponentialRampToValueAtTime(0.001, startAt + duration);
        osc.connect(gain).connect(ctx.destination);
        osc.start(startAt);
        osc.stop(startAt + duration);
    };
    const t = ctx.currentTime;
    if (outcome === 'ok') {
        play(1568, t, 0.09);
    } else {
        play(392, t, 0.12);
        play(311, t + 0.13, 0.18);
    }
}

export function tsdScanFeedback(outcome: TsdScanOutcome): void {
    _beep(outcome);
    if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
        navigator.vibrate(outcome === 'ok' ? 40 : [60, 40, 60]);
    }
}
