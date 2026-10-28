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
        starter: `import json

# HTTP: await http.get(url=...). Files: files.*. No requests/open().
# args — входы ноды; в playground передай ExecuteRequest.args, иначе {}.
async def run(args, state):
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
        starter: `// JSON, Date, Map, ArrayBuffer, Intl are available. HTTP: await http.get({url}). import lodash from 'lodash'
// args come from node inputs; playground POST /code/execute args, otherwise {}.
async function run(args, state) {
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
        starter: `// JSON, Date, Map, ArrayBuffer, Intl are available. HTTP: await http.get({url}). import lodash from 'lodash'
// Types are stripped at runtime. args come from node inputs or playground ExecuteRequest.args.
async function run(args: Record<string, unknown>, state: Record<string, unknown>) {
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

// encoding/json and encoding/csv are allowed. net/http is not — use http.Get.
// args come from node inputs or playground ExecuteRequest.args.
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
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading.Tasks;

// args come from node inputs or playground ExecuteRequest.args.
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

export function isFlowCodeLanguage(value: unknown): value is string {
    return typeof value === 'string' && LANGUAGE_BY_VALUE.has(value);
}

export function normalizeFlowCodeLanguage(value: unknown) {
    if (isFlowCodeLanguage(value)) {
        return value;
    }
    return 'python';
}

export function flowCodeLanguageMeta(value: unknown) {
    const normalized = normalizeFlowCodeLanguage(value);
    return LANGUAGE_BY_VALUE.get(normalized);
}

export function flowCodeLanguageOptions() {
    return FLOW_CODE_LANGUAGES.map((item) => ({ value: item.value, label: item.label }));
}

/**
 * Items для platform-segmented-control: brand-логотипы через iconSrc (img), не platform-icon.
 * @param {{ iconOnly?: boolean }} [options]
 */
export function flowCodeLanguageSegmentItems(options = {}) {
    const iconOnly = (options as Record<string, any>).iconOnly === true;
    return FLOW_CODE_LANGUAGES.map((item) => ({
        value: item.value,
        iconSrc: `/static/core/assets/icons/${item.icon}.svg`,
        iconFallback: item.shortLabel,
        title: item.label,
        ...(iconOnly ? {} : { label: item.label }),
    }));
}

function requireFlowCodeLanguageMeta(value: unknown) {
    const meta = flowCodeLanguageMeta(value);
    if (meta === undefined) {
        throw new Error('flow code language meta missing');
    }
    return meta;
}

export function flowCodeLanguageLabel(value: unknown) {
    return requireFlowCodeLanguageMeta(value).label;
}

export function flowCodeLanguageShortLabel(value: unknown) {
    return requireFlowCodeLanguageMeta(value).shortLabel;
}

export function flowCodeLanguageIconName(value: unknown) {
    return requireFlowCodeLanguageMeta(value).icon;
}

export function flowCodeMirrorLanguage(value: unknown) {
    return requireFlowCodeLanguageMeta(value).cmLanguage;
}

export function starterCodeForLanguage(value: unknown) {
    return requireFlowCodeLanguageMeta(value).starter;
}

export function edgeConditionStarterCodeForLanguage(value: unknown) {
    return requireFlowCodeLanguageMeta(value).edgeStarter;
}

export function isKnownStarterCode(code: string) {
    if (typeof code !== 'string') {
        return false;
    }
    const trimmed = code.trim();
    return FLOW_CODE_LANGUAGES.some((item) => item.starter.trim() === trimmed);
}

export function isKnownEdgeConditionStarterCode(code: string) {
    if (typeof code !== 'string') {
        return false;
    }
    const trimmed = code.trim();
    return FLOW_CODE_LANGUAGES.some((item) => item.edgeStarter.trim() === trimmed);
}
