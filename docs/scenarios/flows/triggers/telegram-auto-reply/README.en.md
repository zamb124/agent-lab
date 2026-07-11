# Auto-reply in Telegram

**What for:** this guide connects incoming Telegram bot messages to the agent.

**Problems it solves:** customers message @zeleniy_sad_bot and the agent must reply automatically.

**Result:** a Telegram trigger with bot token via a secret variable is configured.

## Step 1. Create a Telegram trigger

In the triggers list click + and choose Telegram. Set id and name — the store bot will then accept customer messages.

![Create a Telegram trigger](telegram-auto-reply--01-telegram-trigger-editor.png)

## Step 2. Set the bot token via a secret

In the token field set @var:tg_bot_8b0d986a — the value comes from protected company variables. Verify and re-register webhook buttons are nearby.

![Set the bot token via a secret](telegram-auto-reply--02-telegram-token-var-set.png)
