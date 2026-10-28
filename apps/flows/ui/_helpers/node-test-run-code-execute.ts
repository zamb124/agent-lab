/**
 * Default Play: POST /flows/api/v1/code/execute для всех нод кроме resource.
 */

import { formatExecuteViewModel } from './flows-execute-preview.js';
import { setTestRunRequestClientId } from './flows-test-run-gate.js';

export const codeExecuteTestRunHandler = {
    id: 'code_execute',
    opName: 'flows/code_execute',
    match: ({ nodeType }: any) => nodeType !== 'resource',
    busyOf: (op: any) => op.busy === true,
    formatViewModel: ({ op }: any) => formatExecuteViewModel({
        opError: op.error,
        lastResult: op.lastResult,
    }),
    run: async ({ host, op, requestClientId }: any) => {
        if (!host || typeof host._stateValue !== 'function') {
            throw new Error('codeExecuteTestRunHandler: host._stateValue required');
        }
        if (typeof host._nodeConfigForPayload !== 'function') {
            throw new Error('codeExecuteTestRunHandler: host._nodeConfigForPayload required');
        }
        let state;
        try {
            state = JSON.parse(host._stateValue());
        } catch (err) {
            if (!(err instanceof SyntaxError)) throw err;
            host.toast('flows:test_panel.toast_state_invalid', { type: 'error' });
            return;
        }
        if (state === null || typeof state !== 'object' || Array.isArray(state)) {
            host.toast('flows:test_panel.toast_state_invalid', { type: 'error' });
            return;
        }
        const nodeConfig = host._nodeConfigForPayload();
        if (host.nodeType === 'datasource' && nodeConfig.datasource_operation === 'execute') {
            const { platformConfirm } = await import('@platform/lib/components/platform-confirm-modal.js');
            const confirmed = await platformConfirm(
                host.t('datasource_node_editor.execute_confirm_body'),
                {
                    title: host.t('datasource_node_editor.execute_confirm_title'),
                    variant: 'danger',
                    confirmVariant: 'danger',
                },
            );
            if (!confirmed) {
                return;
            }
        }
        const skill = typeof host.branchId === 'string' && host.branchId.length > 0 ? host.branchId : 'base';
        setTestRunRequestClientId(requestClientId);
        const result = await op.run({
            node_type: host.nodeType,
            node_config: nodeConfig,
            state,
            flow_id: host.flowId,
            branch_id: skill,
        });
        if (result && typeof result === 'object' && result.success === true) {
            if (result.output_state && typeof result.output_state === 'object' && !Array.isArray(result.output_state)) {
                host._flowEditor.setPreviewExecutionState({ snapshot: result.output_state });
            }
            if (!Array.isArray(result.diff)) {
                throw new Error('codeExecuteTestRunHandler: result.diff array required');
            }
            host._flowEditor.recordDataflowObservation({
                nodeId: host.nodeId,
                observation: {
                    diff: result.diff,
                    output_state: result.output_state && typeof result.output_state === 'object'
                        ? result.output_state
                        : null,
                    duration_ms: typeof result.duration_ms === 'number' ? result.duration_ms : null,
                    observed_at: new Date().toISOString(),
                },
            });
        }
    },
};
