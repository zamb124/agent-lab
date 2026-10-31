/**
 * Пакетирует вход микрофона в Float32 блоки (~4096 кадров) и шлёт в main thread через MessagePort.
 * Работает на audio rendering thread — надёжнее чем устаревший ScriptProcessorNode.
 *
 * Realm-файл: исполняется в AudioWorkletGlobalScope, собирается esbuild'ом в embed-dist.
 * Типы realm'а объявлены локально — lib.webworker несовместим с lib.dom в общем tsconfig.
 */

declare class AudioWorkletProcessor {
    readonly port: MessagePort;
    constructor();
    process(inputs: Float32Array[][], outputs: Float32Array[][], parameters?: Record<string, Float32Array>): boolean;
}

declare function registerProcessor(name: string, processorCtor: new () => AudioWorkletProcessor): void;

const VOICE_MIC_CAPTURE_BATCH_SAMPLES = 4096;

class VoiceMicCaptureProcessor extends AudioWorkletProcessor {
    private readonly _pending = new Float32Array(VOICE_MIC_CAPTURE_BATCH_SAMPLES);
    private _filled = 0;

    override process(inputs: Float32Array[][], outputs: Float32Array[][]): boolean {
        const inBus = inputs[0];
        const outBus = outputs[0];
        if (!inBus || !outBus || !inBus[0] || !outBus[0]) {
            return true;
        }
        const inCh = inBus[0];
        const outCh = outBus[0];
        const block = Math.min(inCh.length, outCh.length);
        if (block === 0) {
            return true;
        }
        outCh.set(inCh.subarray(0, block));
        let read = 0;
        while (read < block) {
            const chunk = VOICE_MIC_CAPTURE_BATCH_SAMPLES - this._filled;
            const take = Math.min(chunk, block - read);
            this._pending.set(inCh.subarray(read, read + take), this._filled);
            this._filled += take;
            read += take;
            if (this._filled >= VOICE_MIC_CAPTURE_BATCH_SAMPLES) {
                const pkt = new Float32Array(VOICE_MIC_CAPTURE_BATCH_SAMPLES);
                pkt.set(this._pending);
                this.port.postMessage(pkt);
                this._filled = 0;
            }
        }
        return true;
    }
}

registerProcessor('voice-mic-capture', VoiceMicCaptureProcessor);
