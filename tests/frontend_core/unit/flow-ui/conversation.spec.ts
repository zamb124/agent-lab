/**
 * Проекция Tasks в ленту диалога и тосты хода: сообщение пользователя из history,
 * активность инструментов/скиллов/ошибок нод по настройкам, карточки агента, реплики HITL,
 * текст ответа с приоритетами, файлы сессии, тосты для страниц без ``conversation``.
 */

import { describe, expect, it } from 'vitest';

import {
    conversationTurn,
    conversationTurns,
    sessionFiles,
    taskActivity,
    taskCards,
    taskDialogue,
    taskErrorText,
    taskText,
    userMessageOfTask,
} from '@platform/lib/flow-ui/runtime/conversation.js';
import { FlowUIStore } from '@platform/lib/flow-ui/runtime/flow-ui-store.js';
import type { FlowUiTask } from '@platform/lib/flow-ui/runtime/conversation.js';
import { deriveTurnToasts } from '@platform/lib/flow-ui/runtime/turn-activity.js';

const UI_MEDIA_TYPE = 'application/vnd.platform.ui+json';
const ACTION_MEDIA_TYPE = 'application/vnd.platform.ui-action+json';
const DEFAULT_SETTINGS = { show_activity: true, tool_calls: 'compact', errors: 'generic', show_reasoning: false, show_skill_loads: true };

function textArtifact(name: string, text: string, { artifactId = `${name}-1`, metadata = undefined }: { artifactId?: string; metadata?: unknown } = {}) {
    const artifact: Record<string, unknown> = { artifactId, name, parts: [{ text }] };
    if (metadata !== undefined) artifact['metadata'] = metadata;
    return artifact;
}

function dataArtifact(name: string, payload: unknown, artifactId = name) {
    return { artifactId, name, parts: [{ data: payload }] };
}

function task(overrides: Record<string, unknown> = {}): FlowUiTask {
    return { id: 't1', contextId: 'c1', status: { state: 'TASK_STATE_COMPLETED' }, artifacts: [], history: [], ...overrides };
}

describe('userMessageOfTask', () => {
    it('takes the first ROLE_USER message of this task with text, files and action', () => {
        const history = [
            { role: 'ROLE_AGENT', parts: [{ text: 'agent' }] },
            { role: 'ROLE_USER', taskId: 'other', parts: [{ text: 'foreign task' }] },
            { role: 'ROLE_USER', taskId: 't1', parts: [
                { text: 'hello ' }, { text: 'world' },
                { url: 'https://f/api/v1/files/download/abc/report.pdf', mediaType: 'application/pdf', filename: 'report.pdf' },
                { url: 'https://f/x/photo.png' },
                { data: { action: 'submit', source: 'btn', fields: { a: 1 }, payload: {} }, mediaType: ACTION_MEDIA_TYPE },
            ] },
            { role: 'ROLE_USER', parts: [{ text: 'second' }] },
        ];
        expect(userMessageOfTask(task({ history }))).toEqual({
            text: 'hello world',
            files: [
                { file_id: null, url: 'https://f/api/v1/files/download/abc/report.pdf', original_name: 'report.pdf', content_type: 'application/pdf', file_size: null },
                { file_id: null, url: 'https://f/x/photo.png', original_name: 'photo.png', content_type: 'application/octet-stream', file_size: null },
            ],
            action: { action: 'submit', source: 'btn', fields: { a: 1 }, payload: {} },
        });
        expect(userMessageOfTask(task({ history: [{ role: 'ROLE_USER', parts: [{ text: 'no task id' }] }] }))).toMatchObject({ text: 'no task id', action: null, files: [] });
        expect(userMessageOfTask(task({ history: undefined }))).toBeNull();
        expect(userMessageOfTask(task({ history: [{ role: 'ROLE_AGENT', parts: [] }] }))).toBeNull();
    });
});

describe('taskActivity', () => {
    const toolCall = { tool: 'web_search', tool_call_id: 'call-1', args: { q: 'weather' } };
    const toolResult = { tool: 'web_search', tool_call_id: 'call-1', result: 'x'.repeat(200) };

    it('tracks a tool call from running to done and hides detail unless detailed', () => {
        const running = task({ status: { state: 'TASK_STATE_WORKING' }, artifacts: [dataArtifact('tool_call', toolCall)] });
        expect(taskActivity(running, DEFAULT_SETTINGS, 'en')).toEqual([{ id: 'call-1', kind: 'tool', label: 'web_search', detail: '', status: 'running' }]);
        const finished = task({ status: { state: 'TASK_STATE_WORKING' }, artifacts: [dataArtifact('tool_call', toolCall), dataArtifact('tool_result', toolResult, 'r')] });
        expect(taskActivity(finished, DEFAULT_SETTINGS, 'en')[0]?.status).toBe('done');
        const detailed = taskActivity(finished, { ...DEFAULT_SETTINGS, tool_calls: 'detailed' }, 'en')[0];
        expect(detailed?.detail).toBe('x'.repeat(160));
        const detailedRunning = taskActivity(running, { ...DEFAULT_SETTINGS, tool_calls: 'detailed' }, 'en')[0];
        expect(detailedRunning?.detail).toBe('{"q":"weather"}');
        // Task завершился без tool_result — незакрытый вызов считается выполненным
        expect(taskActivity(task({ artifacts: [dataArtifact('tool_call', toolCall)] }), DEFAULT_SETTINGS, 'en')[0]?.status).toBe('done');
    });

    it('labels skill loads by agent_skill_id and honours show_skill_loads / tool_calls / show_activity', () => {
        const skill = dataArtifact('tool_call', { tool: 'load_agent_skill', tool_call_id: 's1', args: { agent_skill_id: 'crm-entities' } });
        const artifacts = [skill, dataArtifact('tool_call', toolCall)];
        expect(taskActivity(task({ artifacts }), DEFAULT_SETTINGS, 'en').map((item) => [item.kind, item.label])).toEqual([['skill', 'crm-entities'], ['tool', 'web_search']]);
        expect(taskActivity(task({ artifacts }), { ...DEFAULT_SETTINGS, show_skill_loads: false }, 'en').map((item) => item.kind)).toEqual(['tool']);
        expect(taskActivity(task({ artifacts }), { ...DEFAULT_SETTINGS, tool_calls: 'hidden' }, 'en').map((item) => item.kind)).toEqual(['skill']);
        expect(taskActivity(task({ artifacts }), { ...DEFAULT_SETTINGS, show_activity: false }, 'en').map((item) => item.kind)).toEqual(['skill']);
        const unnamedSkill = dataArtifact('tool_call', { tool: 'load_agent_skill', tool_call_id: 's2', args: {} });
        expect(taskActivity(task({ artifacts: [unnamedSkill] }), DEFAULT_SETTINGS, 'en')[0]?.label).toBe('load_agent_skill');
    });

    it('turns node_error_* artifacts into error chips (detail only when errors=detailed) and skips foreign payloads', () => {
        const artifacts = [
            dataArtifact('node_error_llm', { error: 'Rate limited' }),
            dataArtifact('node_error_empty', { error: '' }, 'e2'),
            dataArtifact('node_start', { node_id: 'llm' }),
            { artifactId: 'text', name: 'response', parts: [{ text: 'not data' }] },
            dataArtifact('weird', 'string payload', 'w'),
        ];
        const generic = taskActivity(task({ artifacts }), DEFAULT_SETTINGS, 'en');
        expect(generic).toEqual([
            { id: 'node_error_llm', kind: 'error', status: 'error', label: 'The request could not be completed', detail: '' },
            { id: 'e2', kind: 'error', status: 'error', label: 'The request could not be completed', detail: '' },
        ]);
        const detailed = taskActivity(task({ artifacts }), { ...DEFAULT_SETTINGS, errors: 'detailed' }, 'ru');
        expect(detailed.map((item) => [item.label, item.detail])).toEqual([['Rate limited', 'Rate limited'], ['Не удалось выполнить запрос', '']]);
        // Ошибки видны даже при скрытой активности инструментов
        expect(taskActivity(task({ artifacts }), { ...DEFAULT_SETTINGS, show_activity: false }, 'en')).toHaveLength(2);
    });
});

describe('cards, text, dialogue and error text', () => {
    it('collects conversation cards, replacing re-rendered blocks in place', () => {
        const parts = [
            { data: { kind: 'render', slot_id: 'conversation', blocks: [{ block_id: 'a', type: 'text', text: 'A1' }, { block_id: 'b', type: 'text', text: 'B' }] }, mediaType: UI_MEDIA_TYPE },
            { data: { kind: 'render', slot_id: 'sidebar', blocks: [{ block_id: 'x', type: 'text', text: 'X' }] }, mediaType: UI_MEDIA_TYPE },
            { data: { kind: 'navigate', page_id: 'main' }, mediaType: UI_MEDIA_TYPE },
            { data: { kind: 'render', slot_id: 'conversation', blocks: [{ block_id: 'a', type: 'text', text: 'A2' }] }, mediaType: UI_MEDIA_TYPE },
        ];
        const withUi = task({ artifactsById: { ui: { artifactId: 'ui', parts } } });
        expect(taskCards(withUi).map((block) => [block.block_id, block.text])).toEqual([['a', 'A2'], ['b', 'B']]);
        expect(taskCards(task())).toEqual([]);
        expect(taskCards(task({ artifactsById: {} }))).toEqual([]);
    });

    it('joins text artifacts by name and orders HITL replies with operator authors', () => {
        const operator = { user_id: 'u1', name: 'Olga' };
        const artifacts = [
            textArtifact('response', 'Hel', { artifactId: 'r1' }),
            textArtifact('user_message', 'Need a human', { artifactId: 'um' }),
            textArtifact('operator_reply', 'On it', { artifactId: 'or', metadata: { author: operator } }),
            textArtifact('operator_reply', 'no author', { artifactId: 'or2', metadata: { author: 'bad' } }),
            textArtifact('response', 'lo', { artifactId: 'r2' }),
        ];
        expect(taskText(task({ artifacts }), 'response')).toBe('Hello');
        expect(taskText(task({ artifacts }), 'reasoning')).toBe('');
        expect(taskDialogue(task({ artifacts }))).toEqual([
            { id: 'um', role: 'user', text: 'Need a human', author: null },
            { id: 'or', role: 'operator', text: 'On it', author: operator },
            { id: 'or2', role: 'operator', text: 'no author', author: null },
        ]);
    });

    it('returns an error text only for failed tasks, detailed when configured and present', () => {
        const failed = task({ status: { state: 'TASK_STATE_FAILED', message: { role: 'ROLE_AGENT', parts: [{ text: 'Budget exceeded' }] } } });
        expect(taskErrorText(failed, DEFAULT_SETTINGS, 'en')).toBe('The request could not be completed');
        expect(taskErrorText(failed, { ...DEFAULT_SETTINGS, errors: 'detailed' }, 'en')).toBe('Budget exceeded');
        const silentFailure = task({ status: { state: 'TASK_STATE_FAILED' } });
        expect(taskErrorText(silentFailure, { ...DEFAULT_SETTINGS, errors: 'detailed' }, 'ru')).toBe('Не удалось выполнить запрос');
        expect(taskErrorText(task(), { ...DEFAULT_SETTINGS, errors: 'detailed' }, 'en')).toBe('');
        expect(taskErrorText(task({ status: undefined }), DEFAULT_SETTINGS, 'en')).toBe('');
    });
});

describe('conversationTurn', () => {
    it('prefers the response artifact, then the user_message interrupt question, then the completed status message', () => {
        const author = { user_id: 'agent', name: 'Flow' };
        const withResponse = task({ artifacts: [textArtifact('response', 'Answer', { metadata: { author } }), textArtifact('reasoning', 'thinking')] });
        const turn = conversationTurn(withResponse, DEFAULT_SETTINGS, 'en');
        expect(turn).toMatchObject({ taskId: 't1', state: 'TASK_STATE_COMPLETED', settled: true, text: 'Answer', author, reasoning: '', interrupt: null, error: '', user: null, cards: [], activity: [], dialogue: [] });
        expect(conversationTurn(withResponse, { ...DEFAULT_SETTINGS, show_reasoning: true }, 'en').reasoning).toBe('thinking');

        const asking = task({ status: { state: 'TASK_STATE_INPUT_REQUIRED', message: { role: 'ROLE_AGENT', parts: [{ text: 'Your email?' }] } } });
        const askingTurn = conversationTurn(asking, DEFAULT_SETTINGS, 'en');
        expect(askingTurn.text).toBe('Your email?');
        expect(askingTurn.interrupt).toMatchObject({ kind: 'user_message', question: 'Your email?', continues: false });
        expect(askingTurn.settled).toBe(true);

        const operatorWait = task({ status: { state: 'TASK_STATE_INPUT_REQUIRED', message: { role: 'ROLE_AGENT', parts: [{ text: 'Operator will answer' }], metadata: { platform_interrupt: { body: { kind: 'operator_task', handoff_mode: 'takeover' } } } } } });
        const operatorTurn = conversationTurn(operatorWait, DEFAULT_SETTINGS, 'en');
        // Ожидание оператора — не вопрос пользователю, текст ответа пустой
        expect(operatorTurn.text).toBe('');
        expect(operatorTurn.interrupt).toMatchObject({ kind: 'operator_task', continues: true, handoffMode: 'takeover' });

        const completedByStatus = task({ status: { state: 'TASK_STATE_COMPLETED', message: { role: 'ROLE_AGENT', parts: [{ text: 'Done via status' }] } } });
        expect(conversationTurn(completedByStatus, DEFAULT_SETTINGS, 'en').text).toBe('Done via status');
        const working = task({ status: { state: 'TASK_STATE_WORKING', message: { role: 'ROLE_AGENT', parts: [{ text: 'partial' }] } } });
        expect(conversationTurn(working, DEFAULT_SETTINGS, 'en')).toMatchObject({ text: '', settled: false });
        expect(conversationTurn(task({ status: undefined }), DEFAULT_SETTINGS, 'en')).toMatchObject({ state: 'TASK_STATE_SUBMITTED', settled: false });
    });

    it('drops an interrupt question that only echoes the response text, keeping kind and actions', () => {
        const handoffStatus = (question: string) => ({
            state: 'TASK_STATE_INPUT_REQUIRED',
            message: { role: 'ROLE_AGENT', parts: [{ text: question }], metadata: { platform_interrupt: { question, body: { kind: 'handoff', target_flow_id: 'crm' } } } },
        });
        const echoed = conversationTurn(task({ status: handoffStatus('Передаю управление агенту «CRM»'), artifacts: [textArtifact('response', 'Передаю управление агенту «CRM»\n')] }), DEFAULT_SETTINGS, 'ru');
        expect(echoed.text).toBe('Передаю управление агенту «CRM»\n');
        expect(echoed.interrupt).toMatchObject({ kind: 'handoff', question: '', continues: true });

        const distinct = conversationTurn(task({ status: handoffStatus('Подключаю CRM'), artifacts: [textArtifact('response', 'Секунду')] }), DEFAULT_SETTINGS, 'ru');
        expect(distinct.interrupt).toMatchObject({ kind: 'handoff', question: 'Подключаю CRM' });

        const oauth = { state: 'TASK_STATE_INPUT_REQUIRED', message: { role: 'ROLE_AGENT', parts: [{ text: 'Authorize Google' }], metadata: { platform_interrupt: { question: 'Authorize Google', body: { kind: 'oauth_required', auth_url: 'https://auth' } } } } };
        const oauthTurn = conversationTurn(task({ status: oauth, artifacts: [textArtifact('response', 'Authorize Google')] }), DEFAULT_SETTINGS, 'en');
        expect(oauthTurn.interrupt).toMatchObject({ kind: 'oauth_required', question: '', authUrl: 'https://auth' });
    });

    it('keeps the user message of a streaming turn: SUBMITTED snapshot first, then status/artifact frames', () => {
        const store = new FlowUIStore();
        store.resetContext('c1');
        store.setPending({ text: 'hello', files: [], action: null, messageId: 'm1' });
        store.applyFrame({ result: { task: task({
            status: { state: 'TASK_STATE_SUBMITTED' },
            history: [{ messageId: 'm1', role: 'ROLE_USER', taskId: 't1', parts: [{ text: 'hello' }] }],
        }) } });
        expect(store.pending).toBeNull();
        store.applyFrame({ result: { statusUpdate: { taskId: 't1', contextId: 'c1', status: { state: 'TASK_STATE_WORKING' } } } });
        store.applyFrame({ result: { artifactUpdate: { taskId: 't1', contextId: 'c1', append: true, lastChunk: false, artifact: textArtifact('response', 'Hi') } } });
        expect(conversationTurns(store, DEFAULT_SETTINGS, 'en')[0]).toMatchObject({ user: { text: 'hello' }, text: 'Hi', settled: false });
        store.applyFrame({ result: { statusUpdate: { taskId: 't1', contextId: 'c1', status: { state: 'TASK_STATE_COMPLETED' } } } });
        expect(conversationTurns(store, DEFAULT_SETTINGS, 'en')[0]).toMatchObject({ user: { text: 'hello' }, text: 'Hi', settled: true });
    });

    it('maps every ordered task of the store and dedupes session files by file_id or url', () => {
        const store = new FlowUIStore();
        store.resetContext('c1');
        const upload = { url: 'https://f/api/v1/files/download/f1/a.pdf', filename: 'a.pdf', mediaType: 'application/pdf' };
        store.applyFrame({ result: { task: task({ id: 't1', history: [{ role: 'ROLE_USER', parts: [{ text: 'first' }, upload] }] }) } });
        store.applyFrame({ result: { task: task({ id: 't2', history: [{ role: 'ROLE_USER', parts: [{ text: 'second' }, upload] }],
            artifacts: [{ artifactId: 'state', name: 'state', parts: [{ data: { files: [
                { file_id: 'f1', url: 'https://f/api/v1/files/download/f1/a.pdf', original_name: 'a.pdf', content_type: 'application/pdf', file_size: 10 },
                { file_id: 'f2', url: 'https://f/api/v1/files/download/f2/b.png', original_name: 'b.png', content_type: 'image/png', file_size: 20 },
                { file_id: 'f2', file_size: 25 },
                'garbage', { url: '' },
            ] }, mediaType: 'application/json' }] }] }) } });
        const turns = conversationTurns(store, DEFAULT_SETTINGS, 'en');
        expect(turns.map((turn) => [turn.taskId, turn.user?.text])).toEqual([['t1', 'first'], ['t2', 'second']]);
        const files = sessionFiles(store);
        expect(files).toHaveLength(3);
        expect(files.map((file) => file.file_id)).toEqual([null, 'f1', 'f2']);
        expect(files[0]).toMatchObject({ url: 'https://f/api/v1/files/download/f1/a.pdf', original_name: 'a.pdf', content_type: 'application/pdf' });
        expect(files[2]).toEqual({ file_id: 'f2', url: 'https://f/api/v1/files/download/f2/b.png', original_name: 'b.png', content_type: 'image/png', file_size: 25 });
    });
});

describe('deriveTurnToasts', () => {
    function storeWith(activeTask: FlowUiTask | null) {
        const store = new FlowUIStore();
        store.resetContext('c1');
        if (activeTask) {
            store.applyFrame({ result: { task: activeTask } });
            store.activeTaskId = typeof activeTask.id === 'string' ? activeTask.id : null;
        }
        return store;
    }

    it('shows a working toast with the last three non-error activity labels while the task runs', () => {
        const artifacts = ['a', 'b', 'c', 'd'].map((name) => dataArtifact('tool_call', { tool: `tool_${name}`, tool_call_id: name }));
        artifacts.push(dataArtifact('node_error_x', { error: 'boom' }));
        const store = storeWith(task({ status: { state: 'TASK_STATE_WORKING' }, artifacts }));
        const toasts = deriveTurnToasts(store, DEFAULT_SETTINGS, 'en', { allowCancel: true });
        expect(Object.isFrozen(toasts)).toBe(true);
        expect(toasts).toEqual([{ id: 'working:t1', kind: 'working', title: 'Agent is working…', body: 'tool_b · tool_c · tool_d', streaming: true, canCancel: true, dismissible: false }]);
        expect(deriveTurnToasts(store, DEFAULT_SETTINGS, 'ru')[0]).toMatchObject({ title: 'Агент работает…', canCancel: false });
    });

    it('shows error or truncated response toasts once settled, and nothing without an active task or text', () => {
        expect(deriveTurnToasts(storeWith(null), DEFAULT_SETTINGS, 'en')).toEqual([]);
        const failed = storeWith(task({ status: { state: 'TASK_STATE_FAILED', message: { role: 'ROLE_AGENT', parts: [{ text: 'Quota' }] } } }));
        expect(deriveTurnToasts(failed, { ...DEFAULT_SETTINGS, errors: 'detailed' }, 'en')).toEqual([{ id: 'error:t1', kind: 'error', title: 'Error', body: 'Quota', streaming: false, canCancel: false, dismissible: true }]);
        const long = 'y'.repeat(300);
        const answered = storeWith(task({ artifacts: [textArtifact('response', long)] }));
        const [toast] = deriveTurnToasts(answered, DEFAULT_SETTINGS, 'en');
        expect(toast).toMatchObject({ id: 'response:t1', kind: 'response', title: 'Response', dismissible: true });
        expect(toast?.body).toBe(`${'y'.repeat(280)}…`);
        const short = storeWith(task({ artifacts: [textArtifact('response', 'ok')] }));
        expect(deriveTurnToasts(short, DEFAULT_SETTINGS, 'en')[0]?.body).toBe('ok');
        expect(deriveTurnToasts(storeWith(task()), DEFAULT_SETTINGS, 'en')).toEqual([]);
    });
});
