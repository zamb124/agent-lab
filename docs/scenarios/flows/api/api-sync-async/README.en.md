# Sync and async calls through API Console

**What for:** this guide shows how to call an agent with one HTTP response or in the background.

**Problems it solves:** it is unclear when Sync is better than Streaming and how to wait for a long-running task result.

**Result:** you will verify both SendMessage modes in the same API Console modal.

## Step 1. Open the Run tab

Switch to the Run tab. Here you can change mode, message text, and variables, then send a real request to the current agent.

![Open the Run tab](api-sync-async--01-api-run-tab.png)

## Step 2. Test sync mode

![Test sync mode](api-sync-async--02-api-sync-result.png)

## Step 3. Switch to async mode

Choose Async mode. The API returns a task immediately and you fetch the final reply with a separate status poll.

![Switch to async mode](api-sync-async--03-api-async-mode-selected.png)

## Step 4. Test async mode

![Test async mode](api-sync-async--04-api-async-result.png)
