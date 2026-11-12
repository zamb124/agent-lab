/**
 * Shop AI ops: `shop/ai/*_requested` отвечает мгновенно `{call_id}`,
 * терминальный результат приходит push-событием `shop/ai_call/finished`.
 * Op ждёт push на platform bus по call_id и диспатчит SUCCEEDED с
 * терминальным `result`; `failed` диспатчит FAILED с `error`/`error_code`.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
    shopAiDescribeOp,
    shopAiGeneratePhotoOp,
    shopAiSuggestOptionsOp,
} from '../../../../apps/shop/ui/events/resources/shop.resource.js';
import { platformWs } from '@platform/lib/events/effects/ws.effect.js';
import {
    setPlatformBus,
    resetPlatformBusForTests,
} from '@platform/lib/events/bus-singleton.js';
import { installDomShim } from '../../helpers/dom-shim.js';
import {
    buildPlatformBus,
    buildCtx,
    type DispatchedRecord,
} from '../../helpers/bus-fixtures.js';
import { prop } from '../../helpers/prop.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
const FINISHED = 'shop/ai_call/finished';

type TestBus = ReturnType<typeof buildPlatformBus>;

async function _flush() {
    // Микротаски: resolve platformWs.request → присвоение callId → race armed.
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
}

function _succeeded(dispatched: DispatchedRecord[], op: typeof shopAiDescribeOp): DispatchedRecord | undefined {
    return dispatched.find((d) => d.type === op.events.SUCCEEDED);
}

function _failed(dispatched: DispatchedRecord[], op: typeof shopAiDescribeOp): DispatchedRecord | undefined {
    return dispatched.find((d) => d.type === op.events.FAILED);
}

describe('shop ai ops: call_id → shop/ai_call/finished', () => {
    let bus: TestBus;
    let dispatched: DispatchedRecord[];

    beforeEach(() => {
        installDomShim();
        resetFactories();
        resetPlatformBusForTests();
        bus = buildPlatformBus();
        setPlatformBus(bus);
        dispatched = [];
    });
    afterEach(() => {
        vi.restoreAllMocks();
        resetPlatformBusForTests();
        resetFactories();
    });

    it('SUCCEEDED с терминальным result при completed', async () => {
        const spy = vi.spyOn(platformWs, 'request').mockResolvedValue({ call_id: 'call-1' });
        const run = shopAiDescribeOp.run(
            { shop_id: 's1', name: 'Борщ', category_name: null },
            buildCtx(() => bus.getState(), dispatched),
        );
        await vi.waitFor(() => expect(spy).toHaveBeenCalled());
        expect(spy).toHaveBeenCalledWith(expect.objectContaining({
            type: 'shop/ai/describe_requested',
            expectedSucceeded: 'shop/ai/describe_succeeded',
            expectedFailed: 'shop/ai/describe_failed',
        }));
        await _flush();
        bus.dispatch(FINISHED, {
            call_id: 'call-1', shop_id: 's1', verb: 'describe_product',
            status: 'completed', result: { text: 'Наваристый борщ' },
        });
        await run;
        const ok = _succeeded(dispatched, shopAiDescribeOp);
        expect(ok).toBeDefined();
        expect(prop(ok?.payload, 'result')).toEqual({ text: 'Наваристый борщ' });
    });

    it('игнорирует finished с чужим call_id', async () => {
        vi.spyOn(platformWs, 'request').mockResolvedValue({ call_id: 'call-mine' });
        const run = shopAiSuggestOptionsOp.run(
            { shop_id: 's1', product_name: 'Пицца', group_name: null },
            buildCtx(() => bus.getState(), dispatched),
        );
        await _flush();
        bus.dispatch(FINISHED, {
            call_id: 'other-call', shop_id: 's1', verb: 'suggest_options',
            status: 'completed', result: { items: [] },
        });
        await _flush();
        expect(_succeeded(dispatched, shopAiSuggestOptionsOp)).toBeUndefined();
        bus.dispatch(FINISHED, {
            call_id: 'call-mine', shop_id: 's1', verb: 'suggest_options',
            status: 'completed', result: { items: [{ name: 'Сыр' }] },
        });
        await run;
        expect(prop(_succeeded(dispatched, shopAiSuggestOptionsOp)?.payload, 'result'))
            .toEqual({ items: [{ name: 'Сыр' }] });
    });

    it('failed событие диспатчит FAILED с error и error_code', async () => {
        vi.spyOn(platformWs, 'request').mockResolvedValue({ call_id: 'call-err' });
        const run = shopAiGeneratePhotoOp.run(
            { shop_id: 's1', name: 'Ролл', description: null },
            buildCtx(() => bus.getState(), dispatched),
        );
        await _flush();
        bus.dispatch(FINISHED, {
            call_id: 'call-err', shop_id: 's1', verb: 'generate_product_photo',
            status: 'failed', error: 'flow exploded', error_code: 'a2a_task_failed',
        });
        await run;
        const fail = _failed(dispatched, shopAiGeneratePhotoOp);
        expect(fail).toBeDefined();
        expect(prop(fail?.payload, 'message')).toBe('flow exploded');
        expect(prop(fail?.payload, 'code')).toBe('a2a_task_failed');
    });

    it('failed без error_code даёт дефолтный код и читаемую ошибку', async () => {
        vi.spyOn(platformWs, 'request').mockResolvedValue({ call_id: 'call-noerr' });
        const run = shopAiDescribeOp.run(
            { shop_id: 's1', name: 'Суп', category_name: null },
            buildCtx(() => bus.getState(), dispatched),
        );
        await _flush();
        bus.dispatch(FINISHED, {
            call_id: 'call-noerr', shop_id: 's1', verb: 'describe_product',
            status: 'failed',
        });
        await run;
        const fail = _failed(dispatched, shopAiDescribeOp);
        expect(prop(fail?.payload, 'message')).toBe('shop ai call failed');
        expect(prop(fail?.payload, 'code')).toBe('ai_call_failed');
    });

    it('ack без call_id — FAILED protocol_error', async () => {
        vi.spyOn(platformWs, 'request').mockResolvedValue({ status: 'submitted' });
        const run = shopAiDescribeOp.run(
            { shop_id: 's1', name: 'Суп', category_name: null },
            buildCtx(() => bus.getState(), dispatched),
        );
        await run;
        const fail = _failed(dispatched, shopAiDescribeOp);
        expect(prop(fail?.payload, 'code')).toBe('protocol_error');
    });

    it('completed без result — SUCCEEDED с result null', async () => {
        vi.spyOn(platformWs, 'request').mockResolvedValue({ call_id: 'call-null' });
        const run = shopAiDescribeOp.run(
            { shop_id: 's1', name: 'Суп', category_name: null },
            buildCtx(() => bus.getState(), dispatched),
        );
        await _flush();
        bus.dispatch(FINISHED, {
            call_id: 'call-null', shop_id: 's1', verb: 'describe_product',
            status: 'completed', result: null,
        });
        await run;
        const ok = _succeeded(dispatched, shopAiDescribeOp);
        expect(ok).toBeDefined();
        expect(prop(ok?.payload, 'result')).toBeNull();
    });
});
