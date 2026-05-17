/**
 * Единый UI-контракт языков isolated code runners.
 */

export const FLOW_CODE_LANGUAGES = Object.freeze([
    {
        value: 'python',
        label: 'Python',
        shortLabel: 'Py',
        icon: 'python',
        cmLanguage: 'python',
        entrypoint: 'run',
        starter: `async def run(args, state):
    return {}
`,
        edgeStarter: `async def check(args, state):
    return state.get("route") == "expected_value"
`,
    },
    {
        value: 'javascript',
        label: 'JavaScript',
        shortLabel: 'JS',
        icon: 'javascript',
        cmLanguage: 'javascript',
        entrypoint: 'run',
        starter: `async function run(args, state) {
  return {};
}
`,
        edgeStarter: `async function check(args, state) {
  return state.route === "expected_value";
}
`,
    },
    {
        value: 'typescript',
        label: 'TypeScript',
        shortLabel: 'TS',
        icon: 'typescript',
        cmLanguage: 'typescript',
        entrypoint: 'run',
        starter: `async function run(args: Record<string, unknown>, state: Record<string, unknown>) {
  return {};
}
`,
        edgeStarter: `async function check(args: Record<string, unknown>, state: Record<string, unknown>) {
  return state.route === "expected_value";
}
`,
    },
    {
        value: 'go',
        label: 'Go',
        shortLabel: 'Go',
        icon: 'go',
        cmLanguage: 'go',
        entrypoint: 'run',
        starter: `package main

func run(args map[string]any, state map[string]any) (any, error) {
    return map[string]any{}, nil
}
`,
        edgeStarter: `package main

func check(args map[string]any, state map[string]any) (any, error) {
    return state["route"] == "expected_value", nil
}
`,
    },
    {
        value: 'csharp',
        label: 'C#',
        shortLabel: 'C#',
        icon: 'csharp',
        cmLanguage: 'csharp',
        entrypoint: 'run',
        starter: `using System.Collections.Generic;
using System.Threading.Tasks;

async Task<object?> run(Dictionary<string, object?> args, Dictionary<string, object?> state)
{
    return new Dictionary<string, object?>();
}
`,
        edgeStarter: `using System.Collections.Generic;
using System.Threading.Tasks;

async Task<object?> check(Dictionary<string, object?> args, Dictionary<string, object?> state)
{
    return state.TryGetValue("route", out var route) && Equals(route, "expected_value");
}
`,
    },
]);

const LANGUAGE_BY_VALUE = new Map(FLOW_CODE_LANGUAGES.map((item) => [item.value, item]));

export function isFlowCodeLanguage(value) {
    return typeof value === 'string' && LANGUAGE_BY_VALUE.has(value);
}

export function normalizeFlowCodeLanguage(value) {
    if (isFlowCodeLanguage(value)) {
        return value;
    }
    return 'python';
}

export function flowCodeLanguageMeta(value) {
    const normalized = normalizeFlowCodeLanguage(value);
    return LANGUAGE_BY_VALUE.get(normalized);
}

export function flowCodeLanguageOptions() {
    return FLOW_CODE_LANGUAGES.map((item) => ({ value: item.value, label: item.label }));
}

export function flowCodeLanguageLabel(value) {
    return flowCodeLanguageMeta(value).label;
}

export function flowCodeLanguageShortLabel(value) {
    return flowCodeLanguageMeta(value).shortLabel;
}

export function flowCodeLanguageIconName(value) {
    return flowCodeLanguageMeta(value).icon;
}

export function flowCodeMirrorLanguage(value) {
    return flowCodeLanguageMeta(value).cmLanguage;
}

export function starterCodeForLanguage(value) {
    return flowCodeLanguageMeta(value).starter;
}

export function edgeConditionStarterCodeForLanguage(value) {
    return flowCodeLanguageMeta(value).edgeStarter;
}

export function isKnownStarterCode(code) {
    if (typeof code !== 'string') {
        return false;
    }
    const trimmed = code.trim();
    return FLOW_CODE_LANGUAGES.some((item) => item.starter.trim() === trimmed);
}

export function isKnownEdgeConditionStarterCode(code) {
    if (typeof code !== 'string') {
        return false;
    }
    const trimmed = code.trim();
    return FLOW_CODE_LANGUAGES.some((item) => item.edgeStarter.trim() === trimmed);
}
