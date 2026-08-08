# Landed

A dropshipping product viability calculator. Tells you whether a product makes money
**before** you buy stock or spend anything on ads.

Built to be sold as a paid tool on Whop.

## What it answers

- **Expected profit per order**, adjusted for your real refund rate — not the optimistic number
- **Break-even ROAS**, the figure you actually need when buying traffic
- **Maximum ad cost per sale** before the product stops making money
- **Suggested price** from a configurable pricing rule
- **Orders per month** required to hit a profit target
- A plain verdict: *worth selling*, *too tight*, or *loses money*

Plus supplier A/B comparison and a saved portfolio for shortlisting products.

## The model

All figures are computed in USD. Costs quoted in CNY/EUR/GBP convert at an editable rate.

```
landed        = (unit cost + freight) × fx
revenue       = retail + shipping charged
fees          = revenue × fee% + fixed fee
max ad cost   = revenue − landed − fees
break-even ROAS = revenue ÷ (revenue − landed − fees)
suggested price = (landed + ad cost) × rule multiplier
```

Expected profit is refund-adjusted. On a refunded order the goods, fees and ad spend are
all still gone, so those costs apply to every order while only the kept orders bring revenue:

```
expected profit = (1 − refund rate) × revenue − landed − fees − ad cost
```

**Verdict logic**

| Verdict | Condition |
|---|---|
| Loses money | expected profit ≤ 0 |
| Too tight | profitable, but price is below the pricing rule's suggested price |
| Worth selling | profitable and at or above the suggested price |

## Running it

No build step and no dependencies — it is a single self-contained `index.html`.

```bash
npm run dev     # serves on http://localhost:5173
```

Or just open `index.html` in a browser.

## Architecture

Deliberately a single static file: no build pipeline, no npm supply chain, no backend.
It deploys anywhere, loads instantly, and keeps working untouched. All state lives in
`localStorage`, so a buyer's product costs never leave their machine — which is also the
honest answer to "do you store my supplier pricing?"

## Licence

See `LICENSE`.
