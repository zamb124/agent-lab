# platform-flow-ui: маршруты и покрытие E2E / browser / unit

Справочник для Playwright E2E (`tests/ui/e2e/test_flows_chat_page.py`, embed autoload, HITL) и WTR browser specs.

| Surface | Route / host | Component |
|---|---|---|
| `flow_chat` | `/flows/:flowId` | `chat-page` → `<platform-flow-ui display="page" profile="spa">` |
| Lara drawer | PlatformApp | `<flow-ui-drawer>` → `<platform-flow-ui display="drawer">` |
| Execution Run | flow editor Run | `<flows-execution-panel>` → `<platform-flow-ui>` |
| Embed | CDN autoload | `flow-ui-drawer` / `platform-flow-ui` |
| HITL page | `/worktracker/tasks/:id` | `<platform-flow-ui profile="operator_handoff">` |
| HITL panel | inbox `work-item-detail-panel` | тот же `operator_handoff` |
| HITL CRM | `/crm/tasks/:workItemId` | CTA `work_item.open_in_tasks`, без composer |

| Scenario | Helper / test |
|---|---|
| SPA send/stream | `test_flows_chat_page_send_and_stream_reply` |
| Task feed after reply | `test_flows_chat_page_task_feed_after_reply` |
| Cancel active task | `test_flows_chat_page_cancel_active_task` |
| New screen clears | `test_flows_chat_page_new_chat_clears_thread` |
| Helpers | `flows_chat_send_message`, `flows_open_chat_page` |
| Embed HITL wait / takeover | `test_hitl_user_surfaces.py` E1/E2 |
| Test Run HITL | `test_hitl_user_surfaces.py` R1/R2 |
| HITL SPA takeover write | `test_hitl_user_takeover_append` |
| HITL operator page/panel/CRM | `test_hitl_operator_matrix.py` |
| HITL host-composer / form Submit | `test_hitl_custom_ui.py` |

