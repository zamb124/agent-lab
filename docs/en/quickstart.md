---
title: "Quickstart"
description: "Send your first Humanitec A2A JSON-RPC request."
---

<p class="docs-page-kicker">Quickstart</p>
<p class="docs-lead">Check the Agent Card, send a message to an agent, and jump into the generated API reference.</p>

<div class="docs-api-strip">
  <div><span>Base URL</span><code>https://humanitec.ru/flows/a2a/{flow_id}</code></div>
  <div><span>Auth</span><code>Authorization: Bearer {token}</code></div>
  <div><span>Protocol</span><code>JSON-RPC 2.0</code></div>
</div>

## 1. Prepare Values

The examples below need a flow identifier and an access token.

```bash
export HUMANITEC_TOKEN="your_token"
export HUMANITEC_FLOW_ID="my-agent"
export HUMANITEC_BASE_URL="https://humanitec.ru/flows/a2a/${HUMANITEC_FLOW_ID}"
```

!!! tip

    Use a bearer token or API key for server integrations. Embedded widgets can use an embed session token.

## 2. Fetch The Agent Card

The Agent Card describes the agent, supported capabilities, and available skills.

=== "curl"

    ```bash
    curl -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
      "${HUMANITEC_BASE_URL}"
    ```

=== "HTTP"

    ```http
    GET /flows/a2a/{flow_id} HTTP/1.1
    Host: humanitec.ru
    Authorization: Bearer {token}
    ```

## 3. Send A Message

Interactive calls use `POST` against the agent URL with a JSON-RPC body.

=== "curl"

    ```bash
    curl -X POST "${HUMANITEC_BASE_URL}" \
      -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
      -H "Content-Type: application/json" \
      -d '{
        "jsonrpc": "2.0",
        "id": "1",
        "method": "message/send",
        "params": {
          "message": {
            "role": "user",
            "content": {
              "parts": [
                {"text": "Help me prepare a short project status"}
              ]
            }
          }
        }
      }'
    ```

=== "JSON-RPC"

    ```json
    {
      "jsonrpc": "2.0",
      "id": "1",
      "method": "message/send",
      "params": {
        "message": {
          "role": "user",
          "content": {
            "parts": [
              { "text": "Help me prepare a short project status" }
            ]
          }
        }
      }
    }
    ```

## 4. Stream Responses

For streaming responses, switch the method to `message/stream`. The response is delivered as Server-Sent Events.

```bash
curl -N -X POST "${HUMANITEC_BASE_URL}" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "stream-1",
    "method": "message/stream",
    "params": {
      "message": {
        "role": "user",
        "content": {
          "parts": [
            {"text": "Tell me the next steps for launching the agent"}
          ]
        }
      }
    }
  }'
```

## Next

<div class="docs-card-grid docs-card-grid-compact">
  <a class="docs-card" href="../api/flows/">
    <span class="docs-card-kicker">API</span>
    <h2>Flows Public API</h2>
    <p>Full A2A method, skill, and task reference.</p>
  </a>
  <a class="docs-card" href="../scenarios/">
    <span class="docs-card-kicker">UI</span>
    <h2>Interface Scenarios</h2>
    <p>Inspect how key product workflows appear in the UI.</p>
  </a>
</div>
