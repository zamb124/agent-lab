# Run the agent on a schedule

**What for:** this guide configures a daily agent run without manual starts.

**Problems it solves:** an order summary is needed every morning — a cron trigger automates it.

**Result:** a schedule trigger with a cron expression is saved on the agent.

## Step 1. Open the triggers list

In the editor menu choose Triggers. Here you see all automatic agent runs — on a schedule, from Telegram, or via webhook.

![Open the triggers list](schedule-daily-run--01-triggers-modal-opened.png)

## Step 2. Create a cron trigger

Click +, pick Cron, and set the schedule to 0 9 * * * — the agent runs every day at 9:00.

![Create a cron trigger](schedule-daily-run--02-cron-trigger-configured.png)
