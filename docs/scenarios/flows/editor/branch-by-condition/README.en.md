# Branch the dialog with edge conditions

**What for:** this guide helps route Green Garden customers down different branches, such as order handling versus returns.

**Problems it solves:** the agent treats every request the same even though order and return scenarios need different answers.

**Result:** a return request follows the Returns Agent branch, visible during a test run.

## Step 1. Open the agent with a branch

In the Green Garden Assistant editor there is already a router and two branches: a regular order path and the Returns Agent. This shows where different request types can go.

![Open the agent with a branch](branch-by-condition--01-branch-graph-opened.png)

## Step 2. Set the condition on the returns link

Click the label on the link to the Returns Agent block and set a condition: variable intent equals returns. The branch runs only for return requests.

![Set the condition on the returns link](branch-by-condition--02-returns-edge-condition.png)
