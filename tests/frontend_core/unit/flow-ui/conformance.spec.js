/**
 * Conformance Flow UI протокола: фикстуры ``tests/fixtures/flow_ui`` общие с pytest
 * (``tests/core/flow_ui/test_flow_ui_conformance.py``). Frontend читает те же данные,
 * что и backend: шаблоны, RFC 6902 патчи state, Part ``ui-action``, события артефакта
 * ``ui`` и sandbox блока ``html``.
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { buildUserMessage } from '../../../../core/frontend/static/lib/a2a/a2a-codec.js';
import { FLOW_UI_ACTION_MEDIA_TYPE } from '../../../../core/frontend/static/lib/a2a/constants.js';
import { applyJsonPatch, decodePart, decodeParts } from '../../../../core/frontend/static/lib/a2a/parts.js';
import {
    FLOW_UI_HTML_CSP,
    FLOW_UI_HTML_SANDBOX,
    buildHtmlSrcdoc,
    htmlBoundPaths,
} from '../../../../core/frontend/static/lib/flow-ui/runtime/html-sandbox.js';
import {
    designText,
    renderTemplate,
    templatePaths,
    unmatchedBraceMessage,
} from '../../../../core/frontend/static/lib/flow-ui/runtime/templating.js';

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), '../../../fixtures/flow_ui');

function fixture(name) {
    return JSON.parse(readFileSync(join(FIXTURES, name), 'utf8'));
}

describe('flow-ui conformance: templating', () => {
    it('extracts the same paths and renders the same text as the backend', () => {
        for (const testCase of fixture('templating.json').cases) {
            expect(templatePaths(testCase.template), testCase.name).toEqual(testCase.paths);
            const result = renderTemplate(testCase.template, testCase.state);
            if (testCase.rendered === false) {
                expect(result.rendered, testCase.name).toBe(false);
                continue;
            }
            if ('text' in testCase) expect(result.text, testCase.name).toBe(testCase.text);
        }
    });

    it('rejects unbalanced braces at render like the backend but keeps the canvas text as is', () => {
        for (const template of fixture('templating.json').unbalanced_templates) {
            expect(unmatchedBraceMessage(template), template).not.toBeNull();
            expect(() => renderTemplate(template, {}), template).toThrow(/unmatched/);
            expect(() => templatePaths(template), template).not.toThrow();
            expect(designText(template, { a: 'A' }), template).toBe(template);
        }
    });
});

describe('flow-ui conformance: state artifact', () => {
    it('applies backend patches to the same result', () => {
        for (const testCase of fixture('state_patch.json').cases) {
            expect(applyJsonPatch(testCase.before, testCase.operations), testCase.name).toEqual(testCase.after);
        }
    });

    it('rejects removing a missing path and unsupported ops', () => {
        expect(() => applyJsonPatch({}, [{ op: 'remove', path: '/x' }])).toThrow(/does not exist/);
        expect(() => applyJsonPatch({}, [{ op: 'move', path: '/x', from: '/y' }])).toThrow(/unsupported json patch op/);
    });
});

describe('flow-ui conformance: ui-action message', () => {
    it('builds exactly the Part the backend parses', () => {
        const { action, part } = fixture('ui_action_message.json');
        const message = buildUserMessage({ contextId: 'ctx-1', action });
        expect(message.parts).toEqual([part]);
        expect(part.mediaType).toBe(FLOW_UI_ACTION_MEDIA_TYPE);
        expect(decodePart(part)).toEqual({ kind: 'ui_action', action: part.data });
    });

    it('never combines an action with message text', () => {
        const { action } = fixture('ui_action_message.json');
        expect(() => buildUserMessage({ text: 'и текст', action })).toThrow(/cannot be combined/);
    });
});

describe('flow-ui conformance: ui artifact parts', () => {
    it('decodes parts by mediaType in the declared order', () => {
        const artifacts = fixture('ui_artifacts.json');
        expect(decodeParts(artifacts.parts).map((decoded) => decoded.kind)).toEqual(artifacts.decoded_kinds);
    });

    it('rejects events outside render/navigate', () => {
        for (const event of fixture('ui_artifacts.json').rejected_events) {
            if (event.kind !== 'render' && event.kind !== 'navigate') {
                expect(() => decodePart({ data: event, mediaType: 'application/vnd.platform.ui+json' })).toThrow(/render or navigate/);
            }
        }
        expect(() => decodePart({ data: {}, mediaType: 'application/x-unknown' })).toThrow(/unsupported Part mediaType/);
    });
});

describe('flow-ui conformance: html sandbox', () => {
    it('pins CSP and sandbox attribute to the fixture', () => {
        const sandbox = fixture('html_sandbox.json');
        expect(FLOW_UI_HTML_CSP).toBe(sandbox.csp);
        expect(FLOW_UI_HTML_SANDBOX).toBe(sandbox.sandbox);
        const srcdoc = buildHtmlSrcdoc({ source: '<p data-bind="email"></p>', tokens: { '--flow-ui-text': '#fff' } });
        expect(srcdoc).toContain(`<meta http-equiv="Content-Security-Policy" content="${sandbox.csp}">`);
        expect(srcdoc).toContain('<p data-bind="email"></p>');
        expect(srcdoc).not.toContain('allow-same-origin');
    });

    it('reads data-bind/data-show paths like the backend', () => {
        const sandbox = fixture('html_sandbox.json');
        for (const testCase of sandbox.bound_paths_cases) {
            expect(htmlBoundPaths(testCase.source), testCase.name).toEqual(testCase.paths);
        }
        for (const source of sandbox.invalid_sources) {
            expect(() => htmlBoundPaths(source)).toThrow(/invalid state path/);
        }
    });
});
