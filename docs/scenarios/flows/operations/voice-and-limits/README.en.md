# Configure voice and limits

**What for:** this guide helps you set a time limit and speech profile for the agent.

**Problems it solves:** it is unclear where to enable voice settings and cap long runs without editing the graph.

**Result:** the agent has a timeout and speech options set in the UI.

## Step 1. Open agent limits and speech

In the editor left column, open Limits and speech. Here you set the maximum runtime and STT/TTS/VAD profile.

![Open agent limits and speech](voice-and-limits--01-flow-limits-panel.png)

## Step 2. Review the speech settings block

Scroll the panel to the speech section. Here you choose TTS provider, voice, and language — profile setup only, without a real voice call.

![Review the speech settings block](voice-and-limits--02-speech-settings-visible.png)

## Step 3. Create a branch for separate settings

Add the Summer sale branch and switch to it. Different scenarios can have their own limits and speech profile on top of agent-wide settings.

![Create a branch for separate settings](voice-and-limits--03-branch-tab-created.png)

## Step 4. Override speech in the branch

**Result demonstration.** In the Summer sale branch you see a separate branch speech block — voice and limits can be tuned per branch.

**Summary.** You now know where to set the agent timeout and how to override the speech profile at branch level.

![Override speech in the branch](voice-and-limits--04-branch-speech-override.png)
