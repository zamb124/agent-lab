# Stock valuation: what the warehouse is worth

**Purpose:** «Valuation» shows stock in money terms: every receipt writes a layer with quantity and price, and issues consume layers in the product's valuation order.

**Problems solved:** you will learn where to find the value of on-hand stock, where the accounting price comes from and why two receipts at different prices are two separate layers.

**Result:** the valuation journal shows inbound layers with prices — the warehouse's value is transparent.

## Step 1. Open Valuation

Choose «Valuation» in the left menu. Every validated receipt wrote a cost layer: the same product has two rows — 10 units at 200 and 6 at 260, exactly as in the documents. The «inbound» type shows the layer came from a receipt.

![Open Valuation](valuation-report--01-valuation-layers.png)

## Step 2. How to read it

**Result demonstration.** The warehouse's value is the sum of live layers: 10×200 + 6×260 = 3560 for this product. When goods leave, layers are consumed in the valuation order (fifo takes the earliest receipt first), so the delivery's cost of goods always comes from real prices.

**Summary.** Valuation is the warehouse's cost ledger: it shows what each receipt cost and how much money is on the shelves right now.

![How to read it](valuation-report--02-valuation-read.png)
