# FEFO lot picking: what expires sooner goes first

**Purpose:** the warehouse holds several lots of one product with different expirations — you must ship what spoils sooner, otherwise fresh stock leaves and the old lot rots on the shelf.

**Problems solved:** a FEFO warehouse reserves the lot with the nearest «best before» itself — the terminal walks the operator to exactly that one, not whatever is handy on the top shelf.

**Result:** of two lots the system reserved and picked the earlier one — its stock decreased, the later lot is untouched.

## Step 1. The hint points to the earliest-expiry lot

The document line already reserved the earlier lot — the hint points to its bin. The operator does not compare label dates: the warehouse strategy made the choice.

![The hint points to the earliest-expiry lot](stock-tsd-fefo-pick--01-tsd-fefo-expected.png)

## Step 2. Scan the bin — the earlier lot was taken

**Result demonstration.** Bin stock is «8»: of 10 units, 2 were taken exactly from the «best before +10 days» lot — checkable in «Lots» on the desktop where each lot shows its date.

**Summary.** On a FEFO warehouse the nearest-expiry lots leave first automatically — the operator just scans where the terminal leads.

![Scan the bin — the earlier lot was taken](stock-tsd-fefo-pick--02-tsd-fefo-bin-contents.png)
