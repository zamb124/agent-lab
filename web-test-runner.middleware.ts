/// <reference types="node" />
/**
 * Middleware для @web/test-runner: то же соглашение URL, что у FastAPI-статики
 * (`/static/core/...` → `core/frontend/static/...`), плюс минимальные ответы для
 * bootstrap-эффектов (file-types, i18n, health, sw) и GET CRM offset-page.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Middleware } from '@web/dev-server-core';

const rootDir = path.dirname(fileURLToPath(import.meta.url));

type MiddlewareContext = Parameters<Middleware>[0];

function _pathname(context: MiddlewareContext): string {
    if (context.URL && typeof context.URL.pathname === 'string') {
        return context.URL.pathname;
    }
    const href = context.request?.href || context.url;
    return new URL(href, 'http://localhost').pathname;
}

function _search(context: MiddlewareContext): string {
    if (context.URL && typeof context.URL.search === 'string') {
        return context.URL.search;
    }
    const href = context.request?.href || context.url;
    return new URL(href, 'http://localhost').search;
}

function _loadPlatformI18nBundle(locale: string): Record<string, unknown> {
    const lang = locale === 'en' ? 'en' : 'ru';
    const filePath = path.join(rootDir, 'core/i18n/translations', lang, 'platform.json');
    const platform = JSON.parse(fs.readFileSync(filePath, 'utf8')) as Record<string, unknown>;
    return { ...platform, platform };
}

// --- Stateful customer-auth API emulator ----------------------------------
// Реальный HTTP-контракт public customer-auth поверх памяти dev-server'а:
// те же пути/статусы/Set-Cookie, что у core/api/customer_auth.py — без моков.

const EMU_BASE = '/customer-auth-emu';
const EMU_COMPANY = 'cmp_emu';
const EMU_CUSTOMER = {
    customer_id: 'cust_emu1',
    phone_e164: '+79991112233',
    scope_company_id: EMU_COMPANY,
    name: 'Эму Клиентов',
};
const EMU_METHODS = [
    { kind: 'telegram_contact', ui: 'contact_share', priority: 6, provider: 'telegram' },
    { kind: 'max_contact', ui: 'contact_share', priority: 5, provider: 'max' },
    { kind: 'yandex_id', ui: 'oauth', priority: 4, provider: 'yandex' },
    { kind: 'vk_id', ui: 'oauth', priority: 3, provider: 'vk' },
    { kind: 'sber_id', ui: 'oauth', priority: 2, provider: 'sber' },
    { kind: 'sms_code', ui: 'code_input', priority: 1, provider: 'phone' },
    { kind: 'emulator', ui: 'auto', priority: 0, provider: 'emulator' },
];

interface EmuChallenge {
    status: 'pending' | 'confirmed' | 'failed' | 'expired';
    phone: string;
    code?: string;
    oauth_state?: string;
    method?: string;
    attempts: number;
    confirmed: boolean;
}
const emuChallenges = new Map<string, EmuChallenge>();
const emuOutbox: { to: string; code: string }[] = [];
let emuSeq = 0;
let emuSessionCustomer: Record<string, unknown> | null = null;

function _emuJson(context: MiddlewareContext, status: number, body: unknown): void {
    context.status = status;
    context.body = JSON.stringify(body);
    context.set('content-type', 'application/json; charset=utf-8');
}

function _emuCookie(context: MiddlewareContext): void {
    context.set('set-cookie', 'customer_token=emu-session; path=/; samesite=lax');
}

async function _emuBody(context: MiddlewareContext): Promise<Record<string, unknown>> {
    const req = (context as unknown as { req?: NodeJS.ReadableStream }).req;
    const chunks: Uint8Array[] = [];
    if (req && typeof (req as never)[Symbol.asyncIterator] === 'function') {
        for await (const chunk of req as AsyncIterable<Uint8Array>) chunks.push(chunk);
    }
    if (!chunks.length) return {};
    try {
        return JSON.parse(Buffer.concat(chunks).toString('utf8')) as Record<string, unknown>;
    } catch {
        return {};
    }
}

function _maskPhone(phone: string): string {
    return phone.length > 4 ? `${phone.slice(0, 3)}***${phone.slice(-4)}` : phone;
}

async function _emuHandle(
    context: MiddlewareContext, method: string | undefined, pathname: string, search: string,
): Promise<boolean> {
    const rel = pathname.slice(EMU_BASE.length);
    if (method === 'GET' && rel === '/me') {
        if (emuSessionCustomer) {
            _emuJson(context, 200, emuSessionCustomer);
        } else {
            _emuJson(context, 401, { detail: 'session_required' });
        }
        return true;
    }
    if (method === 'POST' && rel === '/start') {
        const body = await _emuBody(context);
        const phone = String(body.phone || '');
        if (phone && !/^\+7\d{10}$/.test(phone)) {
            _emuJson(context, 400, { detail: 'invalid_phone' });
            return true;
        }
        emuSeq += 1;
        const id = `phc_emu${emuSeq}`;
        emuChallenges.set(id, { status: 'pending', phone, attempts: 0, confirmed: false });
        _emuJson(context, 200, {
            status: 'challenge_pending',
            challenge_id: id,
            phone_masked: phone ? _maskPhone(phone) : null,
            methods: EMU_METHODS,
        });
        return true;
    }
    if (method === 'POST' && rel === '/method') {
        const body = await _emuBody(context);
        const id = String(body.challenge_id || '');
        const challenge = emuChallenges.get(id);
        if (!challenge || challenge.status !== 'pending') {
            _emuJson(context, 410, { detail: 'challenge_expired' });
            return true;
        }
        const m = String(body.method || '');
        challenge.method = m;
        if (m === 'sms_code') {
            challenge.code = String(100000 + Math.floor(Math.random() * 900000));
            emuOutbox.push({ to: challenge.phone, code: challenge.code });
            _emuJson(context, 200, {
                status: 'challenge_sent', challenge_id: id, kind: 'code', method: m,
                channel: 'sms', expires_in: 300, resend_after: 60,
            });
            return true;
        }
        if (m === 'emulator' || m === 'telegram_contact' || m === 'max_contact') {
            const link = m === 'emulator' ? null
                : `https://t.me/emu_bot?start=${id}`;
            _emuJson(context, 200, {
                status: 'awaiting_contact', challenge_id: id, kind: 'direct', method: m,
                expires_in: 600, deep_link: link,
            });
            return true;
        }
        const slug = m.replace(/_id$/, '');
        emuSeq += 1;
        challenge.oauth_state = `st${emuSeq}`;
        const origin = `http://${String((context.request as { headers?: Record<string, string> })?.headers?.host || 'localhost')}`;
        const cb = `${origin}${EMU_BASE}/oauth/${slug}/callback`;
        _emuJson(context, 200, {
            status: 'awaiting_oauth', challenge_id: id, kind: 'direct', method: m,
            expires_in: 600,
            oauth_url: `${origin}${EMU_BASE}/oauth/${slug}/authorize`
                + `?response_type=code&client_id=emu-client&redirect_uri=${encodeURIComponent(cb)}`
                + `&state=${challenge.oauth_state}`,
        });
        return true;
    }
    if (method === 'POST' && rel === '/verify') {
        const body = await _emuBody(context);
        const id = String(body.challenge_id || '');
        const challenge = emuChallenges.get(id);
        if (!challenge || challenge.status !== 'pending') {
            _emuJson(context, 410, { detail: 'challenge_expired' });
            return true;
        }
        if (body.code === undefined && body.direct === undefined) {
            _emuJson(context, 400, { detail: 'code_or_direct_required' });
            return true;
        }
        if (body.direct !== undefined && body.direct !== null) {
            const direct = body.direct as Record<string, unknown>;
            const directPhone = String(direct.contact_phone || '');
            if (challenge.phone && directPhone && directPhone !== challenge.phone) {
                _emuJson(context, 400, { detail: 'provider_mismatch' });
                return true;
            }
            challenge.status = 'confirmed';
            emuSessionCustomer = {
                ...EMU_CUSTOMER,
                phone_e164: challenge.phone || directPhone || EMU_CUSTOMER.phone_e164,
            };
            _emuCookie(context);
            _emuJson(context, 200, { status: 'confirmed', customer: emuSessionCustomer });
            return true;
        }
        challenge.attempts += 1;
        if (challenge.attempts > 5) {
            challenge.status = 'failed';
            _emuJson(context, 429, { detail: 'attempts_exceeded' });
            return true;
        }
        if (String(body.code) !== challenge.code) {
            _emuJson(context, 400, { detail: 'code_invalid' });
            return true;
        }
        challenge.status = 'confirmed';
        emuSessionCustomer = { ...EMU_CUSTOMER, phone_e164: challenge.phone || EMU_CUSTOMER.phone_e164 };
        _emuCookie(context);
        _emuJson(context, 200, { status: 'confirmed', customer: emuSessionCustomer });
        return true;
    }
    if (method === 'GET' && rel.startsWith('/status')) {
        const qs = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
        const challenge = emuChallenges.get(qs.get('challenge_id') || '');
        if (!challenge) {
            _emuJson(context, 200, { status: 'expired', challenge_id: qs.get('challenge_id') });
            return true;
        }
        if (challenge.status === 'confirmed') {
            _emuCookie(context);
            _emuJson(context, 200, {
                status: 'confirmed', challenge_id: qs.get('challenge_id'),
                customer: emuSessionCustomer,
            });
            return true;
        }
        _emuJson(context, 200, { status: challenge.status, challenge_id: qs.get('challenge_id') });
        return true;
    }
    if (method === 'POST' && rel === '/logout') {
        emuSessionCustomer = null;
        context.set('set-cookie', 'customer_token=; path=/; max-age=0');
        context.status = 200;
        return true;
    }
    // OAuth: authorize → 302 code+state; callback → confirm + cookie + 302.
    const authMatch = rel.match(/^\/oauth\/(\w+)\/authorize$/);
    if (method === 'GET' && authMatch) {
        const qs = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
        const redirect = qs.get('redirect_uri') || '';
        const state = qs.get('state') || '';
        const sep = redirect.includes('?') ? '&' : '?';
        context.status = 302;
        context.set('location', `${redirect}${sep}code=emu-${authMatch[1]}-code&state=${state}`);
        return true;
    }
    const cbMatch = rel.match(/^\/oauth\/(\w+)\/callback$/);
    if (method === 'GET' && cbMatch) {
        const qs = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
        const state = qs.get('state') || '';
        let found: EmuChallenge | undefined;
        for (const ch of emuChallenges.values()) {
            if (ch.oauth_state === state) found = ch;
        }
        if (!found || found.status !== 'pending') {
            _emuJson(context, 410, { detail: 'challenge_expired' });
            return true;
        }
        found.status = 'confirmed';
        emuSessionCustomer = { ...EMU_CUSTOMER, phone_e164: found.phone || EMU_CUSTOMER.phone_e164 };
        _emuCookie(context);
        context.status = 302;
        context.set('location', 'http://localhost/back');
        return true;
    }
    // Тестовые контрольные хуки эмулятора (канал доставки + «webhook» провайдера).
    if (method === 'GET' && rel === '/_outbox') {
        _emuJson(context, 200, { messages: emuOutbox });
        return true;
    }
    if (method === 'POST' && rel === '/_confirm') {
        const body = await _emuBody(context);
        const challenge = emuChallenges.get(String(body.challenge_id || ''));
        if (challenge) {
            challenge.status = 'confirmed';
            emuSessionCustomer = { ...EMU_CUSTOMER, phone_e164: challenge.phone || EMU_CUSTOMER.phone_e164 };
        }
        _emuJson(context, 200, { ok: Boolean(challenge) });
        return true;
    }
    return false;
}

export const browserTestDevMiddleware: Middleware = async (context, next) => {
    const pathname = _pathname(context);
    const method = context.method;

    if (method === 'GET' && pathname === '/health') {
        context.status = 200;
        context.body = 'ok';
        context.set('content-type', 'text/plain; charset=utf-8');
        return;
    }
    if (method === 'GET' && pathname === '/sw.js') {
        context.status = 200;
        context.body = '// test runner stub\n';
        context.set('content-type', 'application/javascript; charset=utf-8');
        return;
    }
    if (method === 'GET' && pathname === '/api/platform/file-types') {
        context.status = 200;
        context.body = JSON.stringify({ categories: [], registry: [] });
        context.set('content-type', 'application/json; charset=utf-8');
        return;
    }
    if (method === 'GET' && pathname.startsWith('/api/i18n/')) {
        const locale = decodeURIComponent(pathname.slice('/api/i18n/'.length).split('/')[0] || 'ru');
        context.status = 200;
        context.body = JSON.stringify(_loadPlatformI18nBundle(locale));
        context.set('content-type', 'application/json; charset=utf-8');
        return;
    }
    if (
        method === 'GET'
        && pathname.startsWith('/crm/api/')
        && pathname.includes('entity-types')
        && !pathname.endsWith('.js')
    ) {
        context.status = 200;
        context.body = JSON.stringify({
            items: [],
            total: 0,
            limit: 200,
            offset: 0,
        });
        context.set('content-type', 'application/json; charset=utf-8');
        return;
    }

    if (pathname.startsWith(EMU_BASE + '/') || pathname === EMU_BASE) {
        if (await _emuHandle(context, method, pathname, _search(context))) return;
    }

    if (pathname.startsWith('/static/core/')) {
        const rest = pathname.slice('/static/core/'.length);
        context.url = `/core/frontend/static/${rest}${_search(context)}`;
    }
    // Vendor-ассеты SPA: прод отдаёт их из `apps/<svc>/ui-dist/vendor/` по
    // `/<svc>/ui/static/vendor/…`; в WTR бандла нет — мапим на исходники ui/vendor.
    const vendorMatch = /^\/([a-z0-9_]+)\/ui\/static\/vendor\/(.+)$/.exec(pathname);
    if (pathname.startsWith('/') && vendorMatch) {
        const [, svc, rest] = vendorMatch;
        context.url = `/apps/${svc}/ui/vendor/${rest}${_search(context)}`;
    }
    return next();
};
