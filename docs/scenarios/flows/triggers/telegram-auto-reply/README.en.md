# Auto-reply in Telegram

**What for:** this guide connects incoming Telegram bot messages to the agent.

**Problems it solves:** customers message @zeleniy_sad_bot and the agent must reply automatically.

**Result:** a Telegram trigger with bot token via a secret variable is configured.

## Step 1. Open the triggers list

In the editor menu choose Triggers. Here you configure automatic agent runs — including incoming Telegram bot messages.

![Open the triggers list](telegram-auto-reply--01-telegram-triggers-modal-opened.png)

## Step 2. Create a Telegram trigger

In the triggers list click + and choose Telegram. Set id and name — the store bot will then accept customer messages.

![Create a Telegram trigger](telegram-auto-reply--02-telegram-trigger-editor.png)

## Step 3. Set the bot token via a secret

In the token field set @var:tg_bot_4a2e49ed — the value comes from protected company variables. Verify and re-register webhook buttons are nearby.

![Set the bot token via a secret](telegram-auto-reply--03-telegram-token-var-set.png)

## Step 4. Save the Telegram auto-reply

**Result demonstration.** The Telegram trigger is saved with a secret reference — the agent is ready to reply in @zeleniy_sad_bot.

**Summary.** You can configure a Telegram trigger and store the token as a secret.

![Save the Telegram auto-reply](telegram-auto-reply--04-telegram-trigger-published.png)
