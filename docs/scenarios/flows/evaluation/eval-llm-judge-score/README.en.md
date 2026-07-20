# Score an answer with an LLM judge

**What for:** this guide helps you create a rubric, a judge node, and run a case with LLM judge scoring.

**Problems it solves:** it is unclear where criteria live and how to see the score after a run.

**Result:** an LLM judge case is saved (ids only) and the run shows a score.

## Step 1. Create a case and select LLM judge

Create a blank case, set a name and text input. In check type choose LLM judge — rubric and judge node fields appear.

![Create a case and select LLM judge](eval-llm-judge-score--01-eval-judge-check-selected.png)

## Step 2. Create a rubric and judge node in the flow

Click New rubric, fill name, threshold and criteria prompt, then Create rubric. Next click Create judge node — the node is stored in the agent FlowConfig.

![Create a rubric and judge node in the flow](eval-llm-judge-score--02-eval-judge-rubric-and-node.png)

## Step 3. Save the case and confirm only ids are stored

Click Create. The case appears in the list: the check stores judge_node_id and rubric_version_id, while the judge body lives in the flow.

![Save the case and confirm only ids are stored](eval-llm-judge-score--03-eval-judge-case-saved-ids.png)

## Step 4. Run the case and inspect the score

**Result demonstration.** After Run the results matrix shows a score and the transcript shows judge feedback.

**Summary.** You can create a rubric with a judge node and run an LLM judge until the score is visible.

![Run the case and inspect the score](eval-llm-judge-score--04-eval-judge-score-visible.png)
