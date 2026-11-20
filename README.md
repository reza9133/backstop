# Backstop

**Parametric cover for anything a public web page can prove, written as an intelligent contract for GenLayer.**

An insured writes a trigger in plain words ("level 1 if the status page reports an outage of more than one hour, level 2 if more than four, level 3 if more than twelve"), names one public page, pays a premium, and a group of backers commits the capital that stands behind the cover. When the cover period is over, an AI reads the page and names the payout level that the terms describe. The contract does the rest: tiered payouts, pro-rata sharing between backers, a bonded contest and an appeal, and refunds whenever nothing conclusive can be read.

The AI is never trusted with money. Its role is narrow and every answer it gives is checked by code:

| The AI is asked to | What the code does with the answer |
| --- | --- |
| **vet** the wording (clear? measurable with the page? event not yet happened?) | It can only *refuse*. A pass opens the policy to backers and moves no money. |
| **bind**: re-check, when the cover is fully backed, that the event has not already happened | A cover never starts on an event that is already on the page; otherwise everything goes back. |
| **read** the page after the cover ended and name a payout level 0-3 | A level above 0 counts **only with a quote that is verbatim on the page** (checked by the contract, again by every validator). The model's own doubt flags (`undated`, `outside_window`, `contradictory`) block a payout. |
| **appeal** a contested reading | Final, and it can only move the outcome in the direction the contesting party argued. |

If the page cannot be read, or the model cannot decide, three times in a row, the policy is **voided** and every wei goes back to where it came from. A reading that cannot be made never pays and never denies.

## Why this is not another escrow

Backstop has two-sided capital, tiers, syndication and an AI that reads the world after the fact. The interesting parts are in the code, not in the prompt:

* **Verbatim-quote rule.** No quote on the page, no payout. A model that hallucinates a catastrophe pays nothing.
* **Inception check.** Adverse selection (insuring something that has already happened) is blocked by a second reading when the cover starts.
* **Tiered payouts with a directional appeal.** The appeal can only help the party that contested; if it moves the other way the first reading stands and the bond is forfeited to the other side.
* **Exact money.** Pro-rata sharing uses one rounding rule (the dust goes to the largest backer) and the contract asserts that every settlement adds up to the wei before any transfer is made.
* **One decision, agreed exactly.** A validator approves a leader's result only when it carries the very decision the validator reached itself: the same verdict, the same payout level. "Stricter is fine" and "one level off is fine" do not exist, so whatever the network approves leads to the same state and the same payment, to the wei (details below).

## Life of a policy

```
create_policy ──► DRAFT ──vet──► OPEN ──back (fills the cover)──► FILLED ──bind──► ACTIVE
   (premium held)   │ refused        │ not filled in time              │ event already    │ cover_end
                    ▼                ▼                                 ▼ happened         ▼
                 REFUSED          LAPSED                             VOID            resolve ──► READ ──settle──► SETTLED
                                                                                         │ unreadable x3      │ contest (bond)
                                                                                         ▼                    ▼
                                                                                       VOID              CONTESTED ──appeal──► SETTLED
```

`CANCELLED` is the insured withdrawing a policy before it is fully backed. `REFUSED`, `LAPSED`, `VOID`, `CANCELLED` and `SETTLED` are final.

1. **Write.** `create_policy(title, terms, source_url, coverage, tier1, tier2, tier3, backing_secs, cover_secs, resolve_secs, contest_secs)` with the premium attached (2% to 90% of the cover). Tiers are payouts in basis points of the cover: `2500, 6000, 10000` (three levels) or `10000, 0, 0` (a single yes/no level). Unused levels are 0 and come last.
2. **Vet.** Anyone calls `vet`. Vague, subjective or already-met wordings are refused and the premium returns. A pass opens the policy for `backing_secs`.
3. **Back.** Backers call `back` with value (at least 0.001 GEN, up to 12 distinct backers). They can `unback` while the policy is open. When the cover is full it is `FILLED`.
4. **Bind.** Anyone calls `bind`; the inception check runs and the cover starts for `cover_secs`.
5. **Read.** After `cover_end`, anyone calls `resolve`. The reading is on record and can be contested for `contest_secs`.
6. **Contest (optional).** The insured (if the reading could be higher) or a backer (if it could be lower) posts a bond of 5% of the cover (at least 0.001 GEN) with a short claim. Anyone then calls `appeal`.
7. **Settle.** Anyone calls `settle` after the contest time (an appeal settles by itself).

## Money rules

* The insured receives `coverage x tier / 10000` of the final level.
* The backers receive the rest of the cover **plus the whole premium**, split in proportion to their commitments.
* A contest bond goes back to its owner when the appeal moved the outcome in the contesting party's direction (or when the appeal could not be read). Otherwise it goes to the other side: to the backers when the insured lost, to the insured when a backer lost.
* `VOID`, `LAPSED`, `REFUSED`, `CANCELLED`: the insured gets the premium back, every backer gets its commitment back.
* `solvency()` reports `deposited - paid == held`, recomputed from every open policy. The tests assert it after every step of hundreds of random walks.

## The consensus rule

Every AI step runs under `gl.vm.run_nondet_unsafe`: the leader assesses, each validator assesses again from the same policy and its own copy of the page, and `_accepts` compares the two. A result is accepted **only if both are well-formed and carry exactly the same decision**. The decision is the one part of a result the contract acts on:

| Step | The decision (must be equal) | What it controls |
| --- | --- | --- |
| **vet**, **bind** | the kind (`CHECK` or `UNREADABLE`) and, for a check, the verdict *pass / refuse* | `OPEN` or `REFUSED` (and a retry); `ACTIVE` or `VOID` (and a retry) |
| **read**, **appeal** | the kind (`READ`, `UNCLEAR` or `UNREADABLE`) and, for a reading, the payout **level** | a reading on record or a retry (and, after three, `VOID`); the exact payment and the direction of the bond |

There is no tolerance in either direction. A leader that refuses where the validator would pass, a leader that reports "no decision" where the validator decided, a leader that names a neighbouring level: each of them would send the policy to another state or pay another amount, so each is rejected and the network moves on to another leader. Because every approving validator holds the same decision as the leader, every approved output has the same lifecycle consequence and the same payout, whichever validators happen to be in the majority.

Around the decision there is proof and shape, never trust:

* **Proof.** A payout level needs a quote that is verbatim on the page of the validator that checks it (the leader's quote on the validator's copy, and the validator's own quote on its copy). A validator that cannot read the page reaches a different decision and rejects the leader's. A validator whose copy of the page tries to steer the reviewer reaches a refusal or "no decision", so it rejects any leader's pass or payout, and a leader's refusal must record the steering too.
* **Closed schema.** A result has exactly the keys of its kind, the right types, flags from the stage's own vocabulary, and nothing that contradicts its decision: a pass carries no refusing flag, a payout carries a quote and no blocking doubt flag, level 0 carries no quote. A forged result is rejected even when its decision matches.
* **Details are not decisions.** `reason`, the flags that are only information, and the page `hash` are stored for readers. They are shape-checked and they never choose a state or an amount, so two results with the same decision and different words have the same consequence (the tests show it to the wei).

The price of exactness is liveness, not safety: when the validators' own readings of a borderline page differ (level 1 against level 2, say), the leader's result is not approved, the transaction may take more rounds or not be accepted at all, and nothing changes. Ask again with `vet`, `bind`, `resolve` or `appeal`.

## Public interface

| Call | Who | Notes |
| --- | --- | --- |
| `create_policy(...)` payable | anyone | the attached value is the premium |
| `cancel_policy(id)` | insured | `DRAFT` or `OPEN` only |
| `vet(id)` | anyone | AI wording check |
| `back(id)` payable / `unback(id, amount)` | backers | the insured cannot back its own policy |
| `lapse(id)` | anyone | open policy past its deadline, or a full cover nobody bound in 2 days |
| `bind(id)` | anyone | AI inception check |
| `resolve(id)` | anyone | AI reading after the cover ended |
| `expire(id)` | anyone | no reading before `resolve_by`, or an appeal nobody ran in 2 days |
| `settle(id)` | anyone | after the contest time |
| `contest(id, claim)` payable | insured or a backer | exactly the bond (see `bond_due`) |
| `appeal(id)` | anyone | AI appeal reading, final |

Views: `get_policy`, `list_policies(offset, limit)`, `policies_of(address, offset, limit)`, `outlook(id)` (what each level pays), `bond_due(id)`, `premium_range(coverage)`, `stats()`, `solvency()`, `limits()`. Every view returns JSON text; amounts are decimal strings in wei.

States: `0 DRAFT, 1 OPEN, 2 FILLED, 3 ACTIVE, 4 READ, 5 CONTESTED, 6 SETTLED, 7 REFUSED, 8 LAPSED, 9 VOID, 10 CANCELLED`. Bond states: `0 none, 1 held, 2 refunded, 3 forfeited`.

## Limits worth knowing

* **The source is part of the risk.** The contract cannot know who controls a page. The vet result can carry a `weak_source` flag, but backers decide whether they trust the source. Choose pages that are not written by the insured.
* **Stable text.** The quote is checked against the text each validator fetches, so pages whose text changes every second (clocks, tickers) cannot support a payout. Use reports, status histories, bulletins.
* **A page that talks to the model** (prompt-injection phrases) is treated as unreliable: the reading is "no decision", and three of those void the policy. Anyone who can write on the page can therefore void a cover on it, but never trigger a payout.
* **The model reads the first 6000 characters** of the page's visible text.
* **A reading is final only when the validators reach it too.** A page that makes the model hesitate between two levels may need several rounds, or a new call, before a level is approved; it can never be approved at a level the validators do not share.
* **One contest per policy**, and a backer slot is never freed: at most 12 distinct addresses ever back one policy.
* No keeper fee: whoever calls `vet`, `bind`, `resolve`, `settle` does it because they are a party (or for free).
* This is a test-network project. It has not been audited.

## Project layout

```
contracts/backstop.py        the intelligent contract
tests/direct/                the local test suite (no network): unit, lifecycle, contest, consensus, adversarial, random walks
scripts/e2e.mjs              the live run on Studionet, writes reports/backstop-e2e-*.{html,md,json}
scripts/deploy.mjs           deploys the contract
scripts/keys.mjs             creates and funds three test accounts
scripts/run-all.sh           lint + local tests + live run, with a summary
rehearsal/run.sh             an offline rehearsal of the live run (real contract, scripted model)
.devcontainer/               GitHub Codespaces setup
```

## Run it

### Everything in a GitHub Codespace (recommended)

1. Push this folder to a GitHub repository and open it in a Codespace. The setup script installs Python and Node packages.
2. Create the test accounts (or add `INSURED_KEY`, `BACKER_KEY`, `BACKER2_KEY` as Codespaces secrets):
   ```bash
   npm run keys
   ```
3. Run the static check, the local tests and the live Studionet run (it deploys a fresh contract first):
   ```bash
   bash scripts/run-all.sh
   ```
   Open the newest `reports/backstop-e2e-*.html`. It refreshes itself while the run is going. The live run takes roughly 30 to 45 minutes because it waits for real cover periods.

Useful variations:

```bash
SKIP_LIVE=1  bash scripts/run-all.sh                   # local checks only
SKIP_LOCAL=1 bash scripts/run-all.sh --only vet        # live run only, one scenario
npm run e2e:plan                                       # print the plan, touch no network
bash rehearsal/run.sh                                  # offline rehearsal of the live script
READ_LEVEL=2 bash rehearsal/run.sh --only lifecycle    # ... with a scripted payout
```

### Only the local tests

```bash
pip install -r requirements.txt
genvm-lint check contracts/backstop.py
python3 -m pytest -q
```

### Deploy by hand on Studionet

* **GenLayer Studio:** open the Studio, create a new contract file, paste `contracts/backstop.py`, choose the Studionet network and deploy (no constructor arguments).
* **Script:** `DEPLOY_KEY=0x... npm run deploy` writes the address to `.backstop-address`; later runs use it, or set `BACKSTOP_ADDRESS`. `.backstop-address` belongs to one deployment: after any change of `contracts/backstop.py` delete it (or deploy again), otherwise the live run tests the old code.

Example call from `genlayer-js` (a cover of 0.02 GEN with a premium of 0.004 GEN):

```js
await client.writeContract({
  address, functionName: "create_policy", value: 4_000_000_000_000_000n,
  args: ["Example domains stay reserved", TERMS, "https://www.iana.org/help/example-domains",
         20_000_000_000_000_000n, 2500, 6000, 10000, 900, 120, 900, 60],
});
```

## What the live run checks

The AI is a real model, so the live run accepts any verdict it gives and checks what must hold for all of them: the books balance, every refused call changes nothing, the money that moved matches the state each policy ended in (to the wei), no payout above level 0 exists without a quote, and the contest bond ends in the right hands. Scenarios: `basics`, `adversarial`, `vet`, `lifecycle`, `contest`, `lapse`. If the model refuses the standard wording at the wording check, the run writes one more policy with a simpler wording so the later scenarios can still run (the refused policy's premium is returned and checked). Balances are read again for up to three minutes, because the node can report a balance a while after the transaction that moved it. The report has a table "What the AI said" with every verdict, flag, reason and quote.

## Troubleshooting

- **Local tests: many `ERROR at setup … HTTP Error 404` while downloading `genvm-universal.tar.xz`.** These are not test
  failures: `genlayer-test` could not fetch the GenVM release it wants. `scripts/run-all.sh` runs only those tests again; if
  it still fails, run `python3 -m pip install -U genlayer-test` or override the pinned release (default `v0.2.16`) with
  `BACKSTOP_SDK_VERSION=<version>`.
- **Live run: `Unexpected token '<', "<!DOCTYPE"`.** The Studionet gateway answered with an HTML error page. The script now
  retries such answers; if a scenario still fails, run it alone: `node scripts/e2e.mjs --only lapse`.
- **Live run: an AI step (`vet`, `bind`, `resolve`, `appeal`) is not accepted.** The validators must reach the leader's exact decision (see the consensus rule). When they do not, the transaction ends without a decision and changes nothing. The run sends such a call up to three times, `aiStep` also asks again after the two minute pause, and running the scenario alone usually settles it.
- **Live run: balance checks.** Refunds can show up on the node a few seconds late, so each scenario waits until the
  balances stop moving before it takes its "before" snapshot.

- **Live run: GEN attached to refused calls.** The adversarial steps send value with calls that the contract must refuse.
  On Studionet that value was not returned to the sender (it stayed in the contract's balance, outside its books): the
  contract's balance equalled the books plus the sum of those values to the wei. The run now counts it, prints the amount
  and checks the balances against it. Do not send real value with calls that can be refused.
