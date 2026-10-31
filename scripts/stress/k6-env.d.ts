/**
 * Минимальные ambient-декларации k6 runtime (goja) для стресс-скриптов.
 * Пакетного @types/k6 в зависимостях нет — контракт фиксируется здесь.
 */

declare const __ENV: Record<string, string>;

declare module 'k6' {
    export function check(response: unknown, checks: Record<string, (res: any) => boolean>): boolean;
    export function sleep(seconds: number): void;
    export function fail(message?: string): never;
    export function group<T>(name: string, fn: () => T): T;
    export function randomSeed(seed: number): void;
}

declare module 'k6/http' {
    export interface K6Response {
        status: number;
        body: string;
        timings: { duration: number; [key: string]: number };
        json(selector?: string): any;
        [key: string]: unknown;
    }
    export interface K6RequestParams {
        headers?: Record<string, string>;
        tags?: Record<string, string>;
        [key: string]: unknown;
    }
    const http: {
        get(url: string, params?: K6RequestParams): K6Response;
        post(url: string, body?: string | Record<string, unknown>, params?: K6RequestParams): K6Response;
        put(url: string, body?: string | Record<string, unknown>, params?: K6RequestParams): K6Response;
        del(url: string, params?: K6RequestParams): K6Response;
        request(method: string, url: string, body?: string | Record<string, unknown>, params?: K6RequestParams): K6Response;
        [key: string]: unknown;
    };
    export default http;
}

declare module 'k6/metrics' {
    export class Counter {
        constructor(name: string, isTime?: boolean);
        add(value?: number, tags?: Record<string, string>): void;
    }
    export class Trend {
        constructor(name: string, isTime?: boolean);
        add(value: number, tags?: Record<string, string>): void;
    }
    export class Gauge {
        constructor(name: string, isTime?: boolean);
        add(value: number, tags?: Record<string, string>): void;
    }
    export class Rate {
        constructor(name: string, isTime?: boolean);
        add(value: number | boolean, tags?: Record<string, string>): void;
    }
}

declare module 'k6/execution' {
    interface VuInfo {
        idInTest: number;
        idInInstance: number;
        iterationInInstance: number;
        iterationInScenario: number;
    }
    interface ScenarioInfo {
        name: string;
        executor: string;
        iterationInTest: number;
        iterationInInstance: number;
    }
    const exec: {
        vu: VuInfo;
        scenario: ScenarioInfo;
        test: { options: Record<string, unknown> };
        instance: { iterationsCompleted: number };
    };
    export default exec;
}
