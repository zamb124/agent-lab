# Receiving lot-tracked stock: lot number and expiry date

**Purpose:** food, pharma and cosmetics are managed in lots — each delivery has its own number and «best before» date. Without this you cannot tell what expired or ship oldest first.

**Problems solved:** the terminal asks for the lot number and expiry exactly when needed — after the bin scan, before quantity. With only a paper label, data is typed into two short fields.

**Result:** two lot-tracked products received into their own lots, expiry dates recorded, lots visible in the catalogue and on stock.

## Step 1. Scan a lot-tracked product

The lot-tracked product card looks like a regular one — photo and per-bin stock. «Receive» starts the session; the difference appears at the quantity step: the terminal asks for a lot.

![Scan a lot-tracked product](stock-tsd-receive-lots--01-tsd-lot-product-card.png)

## Step 2. Enter the lot number and expiry

Instead of the numpad — a compact lot panel: the number from the paper label and the «best before» date. If the box has a GS1 code — scan it and both fields fill themselves.

![Enter the lot number and expiry](stock-tsd-receive-lots--02-tsd-lot-entry.png)

## Step 3. Check the receiving line

The execution line shows the product and the entered lot next to the quantity — before committing you see exactly what lands on stock and under which lot number.

![Check the receiving line](stock-tsd-receive-lots--03-tsd-lot-line-review.png)

## Step 4. Scan the bin — stock received under the lot

**Result demonstration.** The bin shows the received quantity, and the lots catalogue («Lots» on the desktop) lists both new lots with «best before» dates — the system will pick what expires earlier first.

**Summary.** Receiving lot-tracked stock: scan product → bin → lot number and expiry → quantity → commit. Lots are created on the fly; an existing number reuses the lot.

![Scan the bin — stock received under the lot](stock-tsd-receive-lots--04-tsd-lot-bin-contents.png)
