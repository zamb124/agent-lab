# Time-travel the run history

**What for:** review dialog execution history, understand each step, and pick a moment to fork or switch the active head.

**Problems it solves:** after a failure it is unclear which step failed and you have to restart the whole dialog.

**Result:** execution history is open with a readable event journal and Fork / Make head / Retry actions.

## Step 1. Open the agent chat

Open the Green Garden Assistant chat. Execution history is available for dialogs that have run at least once.

![Open the agent chat](time-travel-history--01-history-chat-opened.png)

## Step 2. Run the dialog

Send a message and wait for the reply. After the run completes, the system stores the event chain in the durable ledger.

![Run the dialog](time-travel-history--02-history-run-done.png)

## Step 3. Open execution history

Click the execution history button in the chat or choose the menu item. The **Execution history** modal opens: branch lineage on top, event journal on the left, inspector on the right.

![Open execution history](time-travel-history--03-durable-history-opened.png)

## Step 4. Pick a step and an action

**Result demonstration.** The journal lists steps from the last run (input, nodes, terminal). The inspector shows a short summary, action consequences, and buttons:

- **Fork** — new branch; session active head stays unchanged.
- **Make head (Rewind)** — new branch becomes the active head; the run does not start by itself — continue with the next chat message.
- **Retry from failure** — only on `NodeFailed`.

After a command, an outcome card shows the new branch. Raw JSON stays under Advanced tabs.

**Summary.** You can now read execution history and deliberately choose fork or head switch.

![Review the event list](time-travel-history--04-durable-history-events.png)
