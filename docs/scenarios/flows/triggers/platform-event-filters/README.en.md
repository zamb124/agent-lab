# Run the agent on a platform event with a filter

**What for:** the agent reacts only to matching events from other services (CRM, tasks, comments).

**Problems it solves:** without a filter the flow would fire on every event of that type — a field condition narrows the subscription to useful cases.

**Result:** a platform event trigger with a comment-role condition is saved.

## Step 1. Open the triggers list

In the editor menu choose Triggers. A platform event connects the agent to actions in other services without a separate webhook.

![Open the triggers list](platform-event-filters--01-platform-event-triggers-modal.png)

## Step 2. Choose Platform event and set the name

This type listens to the event catalog (CRM, tasks, mail, and more). Set an id and a name such as Operator comment. Next pick the exact event type.

![Choose Platform event and set the name](platform-event-filters--02-platform-event-type-selected.png)

## Step 3. Pick the event type and a filter condition

Event type comes from the catalog (autocomplete list). A filter row is field / operator / value: the field comes from the event catalog, the operator is equals / not equals / contains, and the value might be the operator role. With no conditions the agent fires on every event of that type.

![Pick the event type and a filter condition](platform-event-filters--03-platform-event-filters-filled.png)

## Step 4. Check the sample payload on Mapping

The sample shows the event envelope: type, company, and useful payload fields. Path examples help pass the right data into the agent content.

![Check the sample payload on Mapping](platform-event-filters--04-platform-event-mapping-sample.png)

## Step 5. Save the trigger and find it in the list

**Result demonstration.** Operator comment is in the list — the agent reacts only when a work item gets a comment with role operator.

**Summary.** You can subscribe to a platform event and narrow it with a filter.

![Save the trigger and find it in the list](platform-event-filters--05-platform-event-saved-in-list.png)
