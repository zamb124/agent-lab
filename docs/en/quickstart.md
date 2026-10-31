---
title: "Quickstart"
description: "Send your first Platform A2A JSON-RPC request."
---

<p class="docs-page-kicker">Quickstart</p>
<p class="docs-lead">Check the Agent Card, send a message to an agent, and jump into the generated API reference.</p>

<div class="docs-api-strip">
  <div><span>Base URL</span><code>https://linnex.io/flows/api/v1/{flow_id}</code></div>
  <div><span>Auth</span><code>Authorization: Bearer {token}</code></div>
  <div><span>Protocol</span><code>JSON-RPC 2.0</code></div>
</div>

## 1. Prepare Values

The examples below need a flow identifier and an access token.

```bash
export PLATFORM_TOKEN="your_token"
export PLATFORM_FLOW_ID="my-agent"
export PLATFORM_BASE_URL="https://linnex.io/flows/api/v1/${PLATFORM_FLOW_ID}"
```

!!! tip

    Use an API token in the `Authorization: Bearer ...` header for server integrations. Embedded widgets can use a short-lived embed session token.

!!! note "Legacy domain"

    On `linnex.io` the API paths and JSON-RPC contract are the same. Use `https://linnex.io/flows/api/v1/{flow_id}` instead of `linnex.io` if your integration is tied to the legacy apex.

## 2. Fetch The Agent Card

The Agent Card describes the flow, supported capabilities, available branches, and public variables.

=== "curl"

    ```bash
    curl -H "Authorization: Bearer ${PLATFORM_TOKEN}" \
      "${PLATFORM_BASE_URL}"
    ```

=== "HTTP"

    ```http
    GET /flows/api/v1/{flow_id} HTTP/1.1
    Host: linnex.io
    Authorization: Bearer {token}
    ```

## 3. Send A Message

Interactive calls use `POST` against the agent URL with a JSON-RPC body.

=== "curl"

    ```bash
    curl -X POST "${PLATFORM_BASE_URL}" \
      -H "Authorization: Bearer ${PLATFORM_TOKEN}" \
      -H "A2A-Version: 1.0" \
      -H "Content-Type: application/json" \
      -d '{
        "jsonrpc": "2.0",
        "id": "1",
        "method": "SendMessage",
        "params": {
          "message": {
            "messageId": "msg-1",
            "role": "ROLE_USER",
            "parts": [
              {"text": "Help me prepare a short project status"}
            ]
          }
        }
      }'
    ```

=== "JSON-RPC"

    ```json
    {
      "jsonrpc": "2.0",
      "id": "1",
      "method": "SendMessage",
      "params": {
        "message": {
          "messageId": "msg-1",
          "role": "ROLE_USER",
          "parts": [
            { "text": "Help me prepare a short project status" }
          ]
        }
      }
    }
    ```

## 4. Stream Responses

For streaming responses, switch the method to `SendStreamingMessage`. The response is delivered as Server-Sent Events (`statusUpdate` / `artifactUpdate`).

```bash
curl -N -X POST "${PLATFORM_BASE_URL}" \
  -H "Authorization: Bearer ${PLATFORM_TOKEN}" \
  -H "A2A-Version: 1.0" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "stream-1",
    "method": "SendStreamingMessage",
    "params": {
      "message": {
        "messageId": "msg-stream-1",
        "role": "ROLE_USER",
        "parts": [
          {"text": "Tell me the next steps for launching the agent"}
        ]
      }
    }
  }'
```

## Next

<div class="docs-card-grid docs-card-grid-compact">
  <a class="docs-card" href="../api/flows/">
    <span class="docs-card-kicker">API</span>
    <h2>Flows Public API</h2>
    <p>Full A2A method, branch, variable, file, and task reference.</p>
  </a>
  <a class="docs-card" href="../scenarios/">
    <span class="docs-card-kicker">UI</span>
    <h2>Interface Instructions</h2>
    <p>Inspect how key product workflows appear in the UI.</p>
  </a>
</div>
