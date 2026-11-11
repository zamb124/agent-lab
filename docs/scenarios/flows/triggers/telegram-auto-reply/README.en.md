# Connect a Telegram bot to the agent

**What for:** inbound Telegram bot messages will start the agent and get a reply.

**Problems it solves:** customers message the store bot, and the assistant must answer — without copying chats by hand.

**Result:** a Telegram trigger with a secret token and a user_id filter is saved.

## Step 1. Open triggers in the editor

Open Triggers on the Green Garden Assistant. Here you connect the bot @zeleniy_sad_bot so customer messages reach the agent.

![Open triggers in the editor](telegram-auto-reply--01-telegram-triggers-modal-opened.png)

## Step 2. Choose Telegram and name the trigger

The Telegram card is for inbound Bot API Updates. Set a short id and a clear name such as Telegram auto-reply. Leave the trigger enabled.

![Choose Telegram and name the trigger](telegram-auto-reply--02-telegram-type-and-name.png)

## Step 3. Set the bot token and allowed users

In Bot token set a reference like @var:telegram_bot_token — the value comes from company secrets; do not paste the raw token into the UI. Allowed user ids are numeric Telegram ids, comma-separated; empty means everyone. Nearby are verify and webhook re-register actions.

![Set the bot token and allowed users](telegram-auto-reply--03-telegram-token-and-users.png)

## Step 4. Map message text to the agent reply

On the Mapping tab click a path example — usually message text goes to content, and chat_id is needed so the reply returns to the same chat. Sample JSON shows the Telegram data shape.

![Map message text to the agent reply](telegram-auto-reply--04-telegram-mapping.png)

## Step 5. Save the auto-reply and check the list

**Result demonstration.** The Telegram auto-reply trigger is in the list — the agent is ready to reply in @zeleniy_sad_bot.

**Summary.** You can connect a bot: token via secret, user_id filter, and mapping.

![Save the auto-reply and check the list](telegram-auto-reply--05-telegram-trigger-published.png)
