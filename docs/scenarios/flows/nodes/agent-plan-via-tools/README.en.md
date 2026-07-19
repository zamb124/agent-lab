# Agent step plan via tools

**What for:** this guide shows how to attach plan tools by hand when a Skill is not needed or not available.

**Problems it solves:** you only need a chat checklist without a Skill procedure — write and read plan tools are enough.

**Result:** the Green Garden Assistant chat shows the same checklist with completed steps struck through.

## Step 1. Create an agent from a template

On the Flows home start creating an agent, pick the plain template, and name it Green Garden Assistant. You get an answer node ready for a step checklist setup.

![Create an agent from a template](agent-plan-via-tools--01-agent-plan-create-wizard.png)

## Step 2. Open Studio in Tools mode

In Studio open Skills and tools and choose Tools. Here you add library tools without a Skill.

![Open Studio in Tools mode](agent-plan-via-tools--02-agent-plan-tools-studio.png)

## Step 3. Add plan tools from the library

Click From library and add agent_plan_write and agent_plan_get. The first writes the full step checklist; the second reads the current plan. Both appear as chips on the node.

![Add plan tools from the library](agent-plan-via-tools--03-agent-plan-tools-attached.png)

## Step 4. Publish the agent and open chat

Publish the settings and open the assistant chat. Next the same multi-step customer request — the plan appears without a Skill.

![Publish the agent and open chat](agent-plan-via-tools--04-agent-plan-tools-chat.png)

## Step 5. Send a multi-step request and see the checklist

Send a request with several actions. The agent calls the plan tools, and a step checklist appears in the feed.

![Send a multi-step request and see the checklist](agent-plan-via-tools--05-agent-plan-tools-checklist.png)

## Step 6. Check plan progress and the reply

**Result demonstration.** Find the customer order is struck through, Check delivery status is current; the agent reply is next to it.

**Summary.** You can enable a step plan via library tools and follow progress in chat.

![Check plan progress and the reply](agent-plan-via-tools--06-agent-plan-tools-progress-demo.png)
