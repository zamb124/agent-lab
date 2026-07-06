/**
 * Re-export канонического run trace из core/lib/chat.
 */
import { ChatRunTrace } from '@platform/lib/chat/chat-run-trace.js';

export class FlowsChatRunTrace extends ChatRunTrace {}

if (!customElements.get('flows-chat-run-trace')) {
    customElements.define('flows-chat-run-trace', FlowsChatRunTrace);
}
