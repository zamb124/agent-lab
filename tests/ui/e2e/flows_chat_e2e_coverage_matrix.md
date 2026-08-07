# platform-flow-ui: маршруты и покрытие E2E / browser / unit

Справочник для Playwright E2E (`tests/ui/e2e/test_flows_chat_page.py`, embed autoload) и WTR browser specs.

| Surface | Route / host | Component |
|---|---|---|
| `flow_chat` | `/flows/:flowId` | `chat-page` → `<platform-flow-ui display="page" profile="spa">` |
| Lara drawer | PlatformApp | `<flow-ui-drawer>` → `<platform-flow-ui display="drawer">` |
| Execution Run | flow editor Run | `<flows-execution-panel>` → `<platform-flow-ui>` |
| Embed | CDN autoload | `flow-ui-drawer` / `platform-flow-ui` |
| HITL | worktracker card | `<platform-flow-ui profile="operator_handoff">` |

| Scenario | Helper / test |
|---|---|
| SPA send/stream | `test_flows_chat_page_send_and_stream_reply` |
| Task feed after reply | `test_flows_chat_page_task_feed_after_reply` |
| Cancel active task | `test_flows_chat_page_cancel_active_task` |
| New screen clears | `test_flows_chat_page_new_chat_clears_thread` |
| Helpers | `flows_chat_send_message`, `flows_open_chat_page` |
