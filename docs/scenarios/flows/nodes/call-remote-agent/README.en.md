# Call a remote agent

**What for:** this guide connects a partner agent over the A2A protocol.

**Problems it solves:** some scenarios live with another provider and you need to call their remote agent from your graph.

**Result:** a remote agent node with URL and branch.

## Step 1. Add a remote agent node

Drag a Remote agent node and open its settings. It calls another company's agent by URL or identifier.

![Add a remote agent node](call-remote-agent--01-remote-flow-node-opened.png)

## Step 2. Set the partner agent address

In URL mode enter the partner agent address and branch if needed. Your agent then knows where to forward the customer request.

![Set the partner agent address](call-remote-agent--02-remote-agent-url-set.png)

## Step 3. Review the address before publishing

Reopen the node and confirm the partner URL is in the draft — the graph is ready to delegate requests to an external agent.

![Review the address before publishing](call-remote-agent--03-remote-agent-url-reviewed.png)

## Step 4. Publish the remote agent call

**Result demonstration.** The remote agent node is saved with the URL — the graph is ready to delegate requests to a partner.

**Summary.** You can add a remote_flow node and configure an external agent call over A2A.

![Publish the remote agent call](call-remote-agent--04-remote-agent-published.png)
