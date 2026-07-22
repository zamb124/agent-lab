/**
 * Группировка list-писем в треды (Message-ID / In-Reply-To / References / subject).
 */

const MESSAGE_ID_TOKEN_RE = /<[^>\s]+>/g;
const SUBJECT_PREFIX_RE = /^\s*((re|fw|fwd|sv|aw|antw|ответ|пересл)\s*:\s*)+/i;

/**
 * @param {string} raw
 * @returns {string}
 */
export function normalizeMessageId(raw) {
    if (typeof raw !== 'string') {
        throw new Error('normalizeMessageId: raw must be string');
    }
    let value = raw.trim();
    if (!value) {
        throw new Error('normalizeMessageId: empty');
    }
    if (!value.startsWith('<')) {
        value = `<${value}`;
    }
    if (!value.endsWith('>')) {
        value = `${value}>`;
    }
    return value;
}

/**
 * @param {string | null | undefined} value
 * @returns {string[]}
 */
export function parseMessageIdTokens(value) {
    if (typeof value !== 'string') {
        return [];
    }
    const stripped = value.trim();
    if (!stripped) {
        return [];
    }
    const tokens = stripped.match(MESSAGE_ID_TOKEN_RE);
    if (tokens && tokens.length > 0) {
        return tokens.map((token) => normalizeMessageId(token));
    }
    return [normalizeMessageId(stripped)];
}

/**
 * @param {string | null | undefined} subject
 * @returns {string}
 */
export function normalizeMailSubject(subject) {
    if (typeof subject !== 'string') {
        return '';
    }
    const stripped = subject.replace(/\s+/g, ' ').trim();
    if (!stripped) {
        return '';
    }
    return stripped.replace(SUBJECT_PREFIX_RE, '').trim().toLowerCase();
}

/**
 * @param {{ message_id?: string | null, in_reply_to?: string | null, references?: string | null, subject?: string | null, uid?: string }} msg
 * @returns {string}
 */
export function threadRootId(msg) {
    if (!msg || typeof msg !== 'object') {
        throw new Error('threadRootId: msg required');
    }
    const references = parseMessageIdTokens(msg.references);
    if (references.length > 0) {
        return references[0];
    }
    const inReply = parseMessageIdTokens(msg.in_reply_to);
    if (inReply.length > 0) {
        return inReply[0];
    }
    const own = parseMessageIdTokens(msg.message_id);
    if (own.length > 0) {
        return own[0];
    }
    const subjectKey = normalizeMailSubject(msg.subject);
    if (subjectKey) {
        return `subject:${subjectKey}`;
    }
    if (typeof msg.uid !== 'string' || !msg.uid) {
        throw new Error('threadRootId: uid required for fallback');
    }
    return `uid:${msg.uid}`;
}

/**
 * @param {unknown} dateValue
 * @returns {number}
 */
function dateTs(dateValue) {
    if (typeof dateValue !== 'string' && typeof dateValue !== 'number') {
        return 0;
    }
    const ts = Date.parse(String(dateValue));
    return Number.isFinite(ts) ? ts : 0;
}

/**
 * @param {Array<{
 *   uid: string,
 *   message_id?: string | null,
 *   in_reply_to?: string | null,
 *   references?: string | null,
 *   subject?: string | null,
 *   from_address?: string | null,
 *   snippet?: string | null,
 *   attachment_count?: number,
 *   unread?: boolean,
 *   date?: string | null,
 * }>} messages
 * @returns {Array<{
 *   threadId: string,
 *   messages: typeof messages,
 *   latest: (typeof messages)[number],
 *   unreadCount: number,
 *   participants: string[],
 *   attachmentCount: number,
 *   subject: string,
 * }>}
 */
export function groupMailThreads(messages) {
    if (!Array.isArray(messages)) {
        throw new Error('groupMailThreads: messages must be an array');
    }
    /** @type {Map<string, typeof messages>} */
    const buckets = new Map();
    for (const msg of messages) {
        if (!msg || typeof msg.uid !== 'string' || !msg.uid) {
            throw new Error('groupMailThreads: each message needs uid');
        }
        const threadId = threadRootId(msg);
        const bucket = buckets.get(threadId);
        if (bucket) {
            bucket.push(msg);
        } else {
            buckets.set(threadId, [msg]);
        }
    }
    const threads = [];
    for (const [threadId, items] of buckets) {
        const ordered = [...items].sort((left, right) => {
            const delta = dateTs(left.date) - dateTs(right.date);
            if (delta !== 0) {
                return delta;
            }
            return String(left.uid).localeCompare(String(right.uid), 'en');
        });
        const latest = ordered[ordered.length - 1];
        const participants = [];
        const seen = new Set();
        for (const item of ordered) {
            const from = typeof item.from_address === 'string' ? item.from_address : '';
            if (!from || seen.has(from)) {
                continue;
            }
            seen.add(from);
            participants.push(from);
        }
        const unreadCount = ordered.reduce(
            (count, item) => (item.unread === true ? count + 1 : count),
            0,
        );
        const attachmentCount = ordered.reduce(
            (count, item) => count + (typeof item.attachment_count === 'number' ? item.attachment_count : 0),
            0,
        );
        let ragIndexStatus = 'skipped';
        for (const item of ordered) {
            const status = typeof item.rag_index_status === 'string' ? item.rag_index_status : 'skipped';
            if (status === 'failed') {
                ragIndexStatus = 'failed';
                break;
            }
            if (status === 'pending' && ragIndexStatus !== 'failed') {
                ragIndexStatus = 'pending';
            }
        }
        const rawSubject = typeof latest.subject === 'string' ? latest.subject : '';
        const subject = normalizeMailSubject(rawSubject)
            ? rawSubject.replace(SUBJECT_PREFIX_RE, '').trim() || rawSubject
            : rawSubject;
        threads.push({
            threadId,
            messages: ordered,
            latest,
            unreadCount,
            participants,
            attachmentCount,
            ragIndexStatus,
            subject,
        });
    }
    threads.sort((left, right) => {
        const delta = dateTs(right.latest.date) - dateTs(left.latest.date);
        if (delta !== 0) {
            return delta;
        }
        return String(right.latest.uid).localeCompare(String(left.latest.uid), 'en');
    });
    return threads;
}

/**
 * @param {ReturnType<typeof groupMailThreads>} threads
 * @param {string} uid
 * @returns {ReturnType<typeof groupMailThreads>[number] | null}
 */
export function findThreadByUid(threads, uid) {
    if (!Array.isArray(threads) || typeof uid !== 'string' || !uid) {
        return null;
    }
    for (const thread of threads) {
        if (thread.messages.some((item) => item.uid === uid)) {
            return thread;
        }
    }
    return null;
}

/**
 * Найти сообщение в треде по Message-ID (In-Reply-To / References lookup).
 *
 * @param {Array<{ message_id?: string | null }>} messages
 * @param {string | null | undefined} messageId
 * @returns {(typeof messages)[number] | null}
 */
export function findThreadMessageByMessageId(messages, messageId) {
    if (!Array.isArray(messages)) {
        throw new Error('findThreadMessageByMessageId: messages must be an array');
    }
    const targets = parseMessageIdTokens(messageId);
    if (targets.length === 0) {
        return null;
    }
    const targetSet = new Set(targets);
    for (const item of messages) {
        if (!item || typeof item !== 'object') {
            continue;
        }
        const ownIds = parseMessageIdTokens(item.message_id);
        if (ownIds.some((id) => targetSet.has(id))) {
            return item;
        }
    }
    return null;
}

/**
 * Компактный превью-текст для reply-quote (snippet / body_text).
 *
 * @param {{ snippet?: string | null, body_text?: string | null } | null | undefined} message
 * @param {number} [maxLen=80]
 * @returns {string}
 */
export function mailReplyPreviewText(message, maxLen = 80) {
    if (typeof maxLen !== 'number' || !Number.isFinite(maxLen) || maxLen < 1) {
        throw new Error('mailReplyPreviewText: maxLen must be a positive number');
    }
    if (!message || typeof message !== 'object') {
        return '';
    }
    let raw = '';
    if (typeof message.snippet === 'string' && message.snippet.trim()) {
        raw = message.snippet;
    } else if (typeof message.body_text === 'string' && message.body_text.trim()) {
        raw = message.body_text;
    }
    const collapsed = raw.replace(/\s+/g, ' ').trim();
    if (!collapsed) {
        return '';
    }
    if (collapsed.length <= maxLen) {
        return collapsed;
    }
    return `${collapsed.slice(0, Math.max(1, maxLen - 1)).trimEnd()}…`;
}
