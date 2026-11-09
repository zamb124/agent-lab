# Agent step plan via Skill

**What for:** this guide shows how to attach the planning Skill so chat shows a visible checklist of the agent's steps.

**Problems it solves:** long agent tasks are opaque — you cannot see the current step or enable a checklist without wiring tools by hand.

**Result:** the Green Garden Assistant chat shows a step plan; completed steps are struck through and the current one is highlighted.

## Step 1. Create an agent from a template

On the Flows home start creating an agent, pick the plain template, and name it Green Garden Assistant. You get an answer node ready for a step checklist setup.

![Create an agent from a template](agent-plan-via-skill--01-agent-plan-create-wizard.png)

## Step 2. Open Studio in Tools mode

In Studio open Skills and tools and choose Tools. Here you add library tools without a Skill.

![Open Studio in Tools mode](agent-plan-via-skill--02-agent-plan-studio-tools.png)

## Step 3. Add the planning Skill

Click Add skill, find agent-planning, and confirm. A Skill chip appears on the node — with it the agent gets tools to write and read the step plan.

![Add the planning Skill](agent-plan-via-skill--03-agent-plan-skill-attached.png)

## Step 4. Publish the agent and open chat

Publish the settings and open the assistant chat. Next the same multi-step customer request — the plan appears without a Skill.

![Publish the agent and open chat](agent-plan-via-skill--04-agent-plan-chat-opened.png)
