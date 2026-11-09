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
