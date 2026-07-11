# Connect an order tracking service

**What for:** this guide helps you fetch order status from an external HTTP service.

**Problems it solves:** the customer asks where the order is and the answer must come from a delivery API.

**Result:** an external API node is configured for order status requests.

## Step 1. Add an external API node

Drag an External API node onto the canvas. Through it the agent calls HTTP services such as an order tracker.

![Add an external API node](call-order-tracking-api--01-external-api-dropped.png)

## Step 2. Set the order service URL

Enter the tracking service URL. You can insert variables in curly braces, for example the order number from the chat.

![Set the order service URL](call-order-tracking-api--02-tracker-url-configured.png)

## Step 3. Publish the API connection

**Result demonstration.** The order tracker node is saved with the service URL — the agent can request order status over HTTP.

**Summary.** You can add an external API node and configure a delivery service call.

![Publish the API connection](call-order-tracking-api--03-order-api-published.png)
