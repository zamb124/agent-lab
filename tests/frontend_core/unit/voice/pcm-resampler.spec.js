import { describe, it, expect } from 'vitest';
import {
    applyFirToFloat,
    designFirLowpassHamming,
    resampleMonoToPcm16ArrayBuffer,
    spliceIntoOutboundFrames,
    VOICE_CAPTURE_SAMPLE_RATE,
    VOICE_OUTBOUND_FRAME_SAMPLES,
} from '@platform/lib/voice/voice-media-session.js';

describe('resampleMonoToPcm16ArrayBuffer', () => {
    it('даёт PCM на втором и третьем батче 48 kHz после хвоста (индекс в merged — локальный от inputBase)', () => {
        const sr = 48000;
        /** @type {{ tail: Float32Array, nextOutSampleIndex: number, inputBase: number }} */
        const state = {
            tail: new Float32Array(0),
            nextOutSampleIndex: 0,
            inputBase: 0,
        };
        const mk = () => new Float32Array(4096).fill(0.05);

        const out1 = resampleMonoToPcm16ArrayBuffer(mk(), sr, state);
        expect(out1).toBeInstanceOf(ArrayBuffer);
        const n1 = new Int16Array(out1).length;
        const expR = sr / VOICE_CAPTURE_SAMPLE_RATE;
        expect(Math.abs(n1 - Math.floor((4096 - 1) / expR))).toBeLessThanOrEqual(2);

        const out2 = resampleMonoToPcm16ArrayBuffer(mk(), sr, state);
        expect(out2).toBeInstanceOf(ArrayBuffer);
        expect(new Int16Array(out2).length).toBeGreaterThan(500);

        const out3 = resampleMonoToPcm16ArrayBuffer(mk(), sr, state);
        expect(out3).toBeInstanceOf(ArrayBuffer);
        expect(new Int16Array(out3).length).toBeGreaterThan(500);
    });
});

describe('designFirLowpassHamming', () => {
    it('DC gain нормализован к 1 (сумма коэффициентов = 1)', () => {
        const taps = designFirLowpassHamming(31, 7500 / 48000);
        let sum = 0;
        for (const v of taps) sum += v;
        expect(sum).toBeCloseTo(1.0, 6);
    });

    it('симметричный (linear phase)', () => {
        const taps = designFirLowpassHamming(31, 7500 / 48000);
        for (let i = 0; i < taps.length; i++) {
            expect(taps[i]).toBeCloseTo(taps[taps.length - 1 - i], 6);
        }
    });

    it('бросает на чётном numTaps', () => {
        expect(() => designFirLowpassHamming(30, 0.1)).toThrow();
    });
});

describe('applyFirToFloat', () => {
    it('константный сигнал после прогрева даёт ту же константу', () => {
        const taps = designFirLowpassHamming(31, 7500 / 48000);
        const history = new Float32Array(30);
        const chunk = new Float32Array(200).fill(0.3);
        const out = applyFirToFloat(chunk, taps, history);
        for (let i = 50; i < out.length; i++) {
            expect(out[i]).toBeCloseTo(0.3, 5);
        }
    });

    it('подавляет высокочастотный шум (Nyquist tone)', () => {
        const taps = designFirLowpassHamming(31, 7500 / 48000);
        const history = new Float32Array(30);
        const chunk = new Float32Array(400);
        for (let i = 0; i < chunk.length; i++) chunk[i] = i % 2 === 0 ? 1.0 : -1.0;
        const out = applyFirToFloat(chunk, taps, history);
        let energy = 0;
        for (let i = 100; i < out.length; i++) energy += out[i] * out[i];
        expect(energy).toBeLessThan(0.5 * (out.length - 100));
    });
});

describe('spliceIntoOutboundFrames', () => {
    it('кратный 320 буфер → ровно N кадров, без остатка', () => {
        const tailState = { tail: new Int16Array(0) };
        const buf = new Int16Array(VOICE_OUTBOUND_FRAME_SAMPLES * 3).buffer;
        const frames = spliceIntoOutboundFrames(buf, tailState);
        expect(frames).toHaveLength(3);
        for (const f of frames) {
            expect(new Int16Array(f).length).toBe(VOICE_OUTBOUND_FRAME_SAMPLES);
        }
        expect(tailState.tail.length).toBe(0);
    });

    it('некратный буфер → tail сохраняется и догружает следующий кадр', () => {
        const tailState = { tail: new Int16Array(0) };
        const buf1 = new Int16Array(VOICE_OUTBOUND_FRAME_SAMPLES + 100).buffer;
        const frames1 = spliceIntoOutboundFrames(buf1, tailState);
        expect(frames1).toHaveLength(1);
        expect(tailState.tail.length).toBe(100);

        const buf2 = new Int16Array(VOICE_OUTBOUND_FRAME_SAMPLES - 100).buffer;
        const frames2 = spliceIntoOutboundFrames(buf2, tailState);
        expect(frames2).toHaveLength(1);
        expect(tailState.tail.length).toBe(0);
    });

    it('пустой буфер при пустом tail → []', () => {
        const tailState = { tail: new Int16Array(0) };
        const frames = spliceIntoOutboundFrames(new ArrayBuffer(0), tailState);
        expect(frames).toEqual([]);
    });

    it('малый чанк (< 320) кладётся в tail без отправки', () => {
        const tailState = { tail: new Int16Array(0) };
        const buf = new Int16Array(50).buffer;
        const frames = spliceIntoOutboundFrames(buf, tailState);
        expect(frames).toEqual([]);
        expect(tailState.tail.length).toBe(50);
    });
});

describe('VOICE_CAPTURE_SAMPLE_RATE export', () => {
    it('= 16000', () => {
        expect(VOICE_CAPTURE_SAMPLE_RATE).toBe(16000);
    });
});
