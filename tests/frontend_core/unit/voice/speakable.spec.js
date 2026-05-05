/**
 * speakable.js — JS-зеркало `apps/flows/src/streaming/speakable.py`.
 *
 * Тесты проверяют:
 *  - whitelist имён артефактов;
 *  - negative-override через `metadata.speak === false`;
 *  - выборку только TextPart из `artifact.parts`;
 *  - склейку всех text-частей через `extractSpeakableText`.
 *
 * Пары с Python: при любом расхождении whitelist ломается CI-проверка
 * `scripts/check_speakable_parity.py`.
 */

import { describe, it, expect } from 'vitest';
import {
    SPEAKABLE_ARTIFACT_NAMES,
    SPEAK_FLAG_KEY,
    isSpeakableArtifact,
    iterSpeakableTextParts,
    extractSpeakableText,
} from '@platform/lib/voice/speakable.js';

describe('speakable whitelist', () => {
    it('SPEAKABLE_ARTIFACT_NAMES содержит response и operator_reply', () => {
        expect(SPEAKABLE_ARTIFACT_NAMES.has('response')).toBe(true);
        expect(SPEAKABLE_ARTIFACT_NAMES.has('operator_reply')).toBe(true);
        expect(SPEAKABLE_ARTIFACT_NAMES.has('reasoning')).toBe(false);
    });

    it('SPEAK_FLAG_KEY — "speak"', () => {
        expect(SPEAK_FLAG_KEY).toBe('speak');
    });

    it('SPEAKABLE_ARTIFACT_NAMES заморожен: содержит только whitelist', () => {
        expect(SPEAKABLE_ARTIFACT_NAMES.size).toBe(2);
        expect(Object.isFrozen(SPEAKABLE_ARTIFACT_NAMES)).toBe(true);
    });
});

describe('isSpeakableArtifact', () => {
    it('true для имени из whitelist', () => {
        expect(isSpeakableArtifact({ name: 'response', parts: [] })).toBe(true);
        expect(isSpeakableArtifact({ name: 'operator_reply', parts: [] })).toBe(true);
        expect(isSpeakableArtifact({ name: 'reasoning', parts: [] })).toBe(false);
    });

    it('false для имени вне whitelist', () => {
        expect(isSpeakableArtifact({ name: 'thinking', parts: [] })).toBe(false);
        expect(isSpeakableArtifact({ name: 'search_plan', parts: [] })).toBe(false);
        expect(isSpeakableArtifact({ name: '', parts: [] })).toBe(false);
    });

    it('пустое имя и непустой TextPart — как response (стрим без name)', () => {
        expect(
            isSpeakableArtifact({
                parts: [{ root: { kind: 'text', text: 'Привет' } }],
            })
        ).toBe(true);
        expect(
            isSpeakableArtifact({
                parts: [{ root: { kind: 'data', data: {} } }],
            })
        ).toBe(false);
        expect(
            isSpeakableArtifact({
                parts: [{ root: { kind: 'text', text: 'x' } }],
                metadata: { speak: false },
            })
        ).toBe(false);
    });

    it('false когда metadata.speak === false', () => {
        expect(
            isSpeakableArtifact({
                name: 'response',
                parts: [],
                metadata: { speak: false },
            })
        ).toBe(false);
    });

    it('true когда metadata.speak === true (явное разрешение)', () => {
        expect(
            isSpeakableArtifact({
                name: 'response',
                parts: [],
                metadata: { speak: true },
            })
        ).toBe(true);
    });

    it('true при отсутствии metadata / пустой metadata', () => {
        expect(isSpeakableArtifact({ name: 'response', parts: [] })).toBe(true);
        expect(isSpeakableArtifact({ name: 'response', parts: [], metadata: {} })).toBe(true);
    });

    it('false для не-объектных аргументов', () => {
        expect(isSpeakableArtifact(null)).toBe(false);
        expect(isSpeakableArtifact(undefined)).toBe(false);
        expect(isSpeakableArtifact('response')).toBe(false);
        expect(isSpeakableArtifact(42)).toBe(false);
    });
});

describe('iterSpeakableTextParts', () => {
    it('возвращает только TextPart.text', () => {
        const parts = iterSpeakableTextParts({
            name: 'response',
            parts: [
                { root: { kind: 'text', text: 'Привет, ' } },
                { root: { kind: 'text', text: 'мир!' } },
                { root: { kind: 'data', data: { x: 1 } } },
                { root: { kind: 'file', file: { uri: 'f://1' } } },
            ],
        });
        expect(parts).toEqual(['Привет, ', 'мир!']);
    });

    it('поддерживает part без .root (flat form)', () => {
        const parts = iterSpeakableTextParts({
            name: 'response',
            parts: [{ kind: 'text', text: 'one' }, { kind: 'text', text: 'two' }],
        });
        expect(parts).toEqual(['one', 'two']);
    });

    it('возвращает [] если артефакт не speakable', () => {
        expect(
            iterSpeakableTextParts({
                name: 'thinking',
                parts: [{ root: { kind: 'text', text: 'x' } }],
            })
        ).toEqual([]);
    });

    it('игнорирует пустые text', () => {
        const parts = iterSpeakableTextParts({
            name: 'response',
            parts: [
                { root: { kind: 'text', text: '' } },
                { root: { kind: 'text', text: 'non-empty' } },
            ],
        });
        expect(parts).toEqual(['non-empty']);
    });

    it('игнорирует части с невалидной формой', () => {
        const parts = iterSpeakableTextParts({
            name: 'response',
            parts: [
                null,
                42,
                'строка',
                { root: null },
                { root: { kind: 'text', text: null } },
                { root: { kind: 'text', text: 'ok' } },
            ],
        });
        expect(parts).toEqual(['ok']);
    });
});

describe('extractSpeakableText', () => {
    it('склеивает все TextPart speakable артефакта', () => {
        const ev = {
            artifact: {
                name: 'response',
                parts: [
                    { root: { kind: 'text', text: 'Привет, ' } },
                    { root: { kind: 'text', text: 'друг.' } },
                ],
            },
        };
        expect(extractSpeakableText(ev)).toBe('Привет, друг.');
    });

    it('возвращает null для артефакта reasoning', () => {
        const ev = {
            artifact: {
                name: 'reasoning',
                parts: [{ root: { kind: 'text', text: 'Внутреннее размышление.' } }],
            },
        };
        expect(extractSpeakableText(ev)).toBeNull();
    });

    it('возвращает null если артефакт не speakable', () => {
        const ev = {
            artifact: {
                name: 'thinking',
                parts: [{ root: { kind: 'text', text: 'hidden' } }],
            },
        };
        expect(extractSpeakableText(ev)).toBeNull();
    });

    it('возвращает null если metadata.speak === false', () => {
        const ev = {
            artifact: {
                name: 'response',
                parts: [{ root: { kind: 'text', text: 'wont-speak' } }],
                metadata: { speak: false },
            },
        };
        expect(extractSpeakableText(ev)).toBeNull();
    });

    it('возвращает null при отсутствии artifact', () => {
        expect(extractSpeakableText({})).toBeNull();
        expect(extractSpeakableText(null)).toBeNull();
        expect(extractSpeakableText({ artifact: null })).toBeNull();
    });

    it('возвращает null если speakable артефакт без text частей', () => {
        const ev = {
            artifact: {
                name: 'response',
                parts: [{ root: { kind: 'data', data: {} } }],
            },
        };
        expect(extractSpeakableText(ev)).toBeNull();
    });

    it('склеивает TextPart при отсутствии name (стрим)', () => {
        const ev = {
            artifact: {
                parts: [
                    { root: { kind: 'text', text: 'Один' } },
                    { root: { kind: 'text', text: ' два' } },
                ],
            },
        };
        expect(extractSpeakableText(ev)).toBe('Один два');
    });
});
