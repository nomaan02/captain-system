# Topstep Optimisation Functions — Complete Specification

**From:** Isaac
**Date:** 2026-03-12
**Scope:** All risk management functions for a $150,000 Topstep account with $4,500 fixed trailing MDD. Covers MDD% management, payout optimisation, trade sizing, daily exposure, and circuit breaker system.
**Recalculation Cycle:** All SOD-locked parameters recalculate at **19:00 EST** (Topstep MDD recalculation time). Trading day = 19:00 EST to 18:59 EST. Each day is treated as an independent time series.

---

# PART 1 — MDD% FUNCTIONS

## 1.1 Base MDD% Function

$$f(A) = \frac{4500}{A}, \quad A \geq 150{,}000$$

$$\lim_{A \to \infty} f(A) = 0$$

As account value A grows to infinity, MDD as a % of A reduces to 0. MDD% at start: f(150,000) = 3.00%.

## 1.2 Rate of Change of MDD% (Deterioration Gradient)

$$f'(A) = -\frac{4500}{A^2}$$

At A = 150,000: f' = -0.0000002. Every additional dollar reduces MDD% by 0.00002 percentage points.

## 1.3 Rate of Change of Deterioration Gradient

$$f''(A) = \frac{9000}{A^3}$$

Always positive → f(A) is **convex**. Deterioration slows as A grows. The first dollar of profit causes the most MDD% damage. Therefore: remove payout maximum as soon as possible.

## 1.4 Desmos

```
f(x) = 4500/x {x >= 150000}
```

```
d(x) = -4500/x^2 {x >= 150000}
```

```
q(x) = 9000/x^3 {x >= 150000}
```

---

# PART 2 — PAYOUT CONSTRAINT & OPTIMISATION

## 2.1 Maximum Payout Function

$$W(A) = \min\Big(5000, 0.5 \times (A - 150{,}000)\Big)$$

The 50% constraint binds until A = 160,000. Above that, the $5,000 cap binds.


| A       | Profit | W(A)  |
| ------- | ------ | ----- |
| 150,000 | 0      | 0     |
| 152,000 | 2,000  | 1,000 |
| 155,000 | 5,000  | 2,500 |
| 160,000 | 10,000 | 5,000 |
| 200,000 | 50,000 | 5,000 |


**Additional constraint:** Maximum 5 payouts total OR cumulative withdrawals ≤ $150,000 (whichever first). Since 5 × $5,000 = $25,000, the $150,000 sum limit is non-binding. The binding constraint is always the 5-payout count.

## 2.2 Post-Payout MDD% Function (Piecewise)

$$g(A) = \frac{4500}{A - W(A)}$$

Expanding:

- For 150,000 < A ≤ 160,000: $\quad g(A) = \frac{4500}{0.5A + 75{,}000}$
- For A > 160,000: $\quad g(A) = \frac{4500}{A - 5{,}000}$

## 2.3 MDD% Recovery Function

$$\Delta(A) = g(A) - f(A) = \frac{4500}{A - W(A)} - \frac{4500}{A}$$

For A > 160,000 (where $5,000 cap binds):

$$\Delta(A) = \frac{4500 \times 5000}{A(A - 5000)} = \frac{22{,}500{,}000}{A^2 - 5000A}$$

**Derivative of recovery:**

$$\Delta'(A) = -\frac{22{,}500{,}000 \times (2A - 5000)}{(A^2 - 5000A)^2}$$

Continuously negative for all A > 150,000. **Proof that optimal payout is the first and maximum payout.** Any time 5 winning days (π > 0) are achieved, the maximum payout should be taken. Idealistic payout = $5,000 exactly.

## 2.4 Steady-State MDD% Range

Let G = average daily profit. Payout per cycle of 5 winning days: W = 5G.

Break-even extraction rate: G = $1,000/day (5G = $5,000 = payout cap).

For G ≤ $1,000/day, account oscillates in steady state. MDD% range:

$$\text{MDD range} = \left[\frac{4500}{150{,}000 + 10G}, \frac{4500}{150{,}000 + 5G}\right]$$

At G = $1,000/day: MDD% range = [2.81%, 2.90%]. Account oscillates between $155,000 and $160,000.

**Optimal ceiling:** A = $160,714 (where f(A) = 2.80%).

For G > $1,000/day: every dollar above $1,000/day cannot be extracted within the optimised steady state. These funds are only effective for post-XFA "LIVE" reserves.

## 2.5 Optimal Payout Rules

1. The first payout, regardless of profit amount, should always be taken at the maximum available W(A).
2. The account should be managed so that expected payout is estimated and aimed to be available by the time the account grows to **$160,714** (+$10,714 from start). Any dollar past this point is an inefficient dollar to remove via payout within the optimised steady state.
3. On any given day, if profits would exceed $1,000: these are the capital units that build LIVE reserves + any inefficient funds remaining post-XFA closure. They cannot be optimised for MDD% recovery.

## 2.6 Key Threshold Table


| MDD% Target | A (no payout) | A (after one $5k payout) |
| ----------- | ------------- | ------------------------ |
| 3.00%       | 150,000       | 155,000                  |
| 2.80%       | 160,714       | 165,714                  |
| 2.50%       | 180,000       | 185,000                  |
| 2.00%       | 225,000       | 230,000                  |
| 1.50%       | 300,000       | 305,000                  |


## 2.7 Desmos

```
W(x) = min(5000, max(0, 0.5(x - 150000)))
```

```
g(x) = 4500/(x - W(x)) {x > 150000}
```

```
h(x) = g(x) - f(x) {x > 150000}
```

```
y = 0.03
y = 0.028
y = 0.025
y = 0.02
```

---

# PART 3 — NUMBER OF TRADES & DAILY EXPOSURE

## 3.1 Risk Per Trade (% of A)

Let p = fraction of MDD% risked per trade. Let φ = expected fee per trade in dollars (round-turn, from TSM fee_schedule — e.g., $2.80 for ES on Topstep Express, $4.18 for NQ on Topstep Live).

**Risk from SL (position risk):**

$$R_{\text{pos}}(A, p) = p \cdot f(A) = \frac{4500p}{A}, \quad A \geq 150{,}000$$

**Effective risk per trade (position risk + fee drag):**

$$R_{\text{eff}}(A, p, \varphi) = p \cdot f(A) + \frac{\varphi}{A} = \frac{4500p + \varphi}{A}$$

R_eff depends on A — as the account grows, both the position risk and fee drag shrink as a percentage. The fee is a fixed dollar cost, so its percentage impact decreases with account size.

In the ideal steady state: 150,000 ≤ A ≤ 160,714, so 0.028 ≤ f(A) ≤ 0.03.

**Example:** p = 0.005, φ = $2.80 (ES Express). At A = 150,000: R_pos = $22.50, R_eff = $22.50 + $2.80 = $25.30 per trade. Fee adds 12.4% to the effective risk.

**Note on p units:** p is expressed as a decimal fraction. p = 0.005 means "0.5% of MDD%." p = 0.01 means "1% of MDD%."

## 3.2 Maximum Trades Per Day

Let e = daily exposure fraction (maximum total risk as % of A per day).

$$N(A, p, e, \varphi) = \left\lfloor \frac{e \cdot A}{4500p + \varphi} \right\rfloor, \quad A \geq 150{,}000, \quad p > 0, \quad e > 0$$

The floor function ⌊⌋ returns the greatest integer ≤ the value. This ensures total exposure (including fees) never exceeds e × A.

**Verification:** At A = 150,000, p = 0.005, e = 0.01, φ = $2.80:

N = ⌊(0.01 × 150,000) / (4500 × 0.005 + 2.80)⌋ = ⌊1500 / 25.30⌋ = ⌊59.29⌋ = 59. ✓

Total daily exposure = 59 × $25.30 = $1,492.70 ≤ $1,500. ✓

**Without fees (φ = 0):** N = 66. **With fees (φ = 2.80):** N = 59. Fee drag removes 7 trade slots per day.

**Fee impact by account type:**


| Account Type    | Instrument | φ     | N (A = 150k) | Trade Slots Lost |
| --------------- | ---------- | ----- | ------------ | ---------------- |
| No fees         | —          | $0    | 66           | 0                |
| Topstep Express | ES         | $2.80 | 59           | 7                |
| Topstep Express | MES        | $0.74 | 64           | 2                |
| Topstep Live    | ES         | $2.80 | 59           | 7                |
| Topstep Live    | NQ         | $4.18 | 56           | 10               |
| IBKR            | ES         | $4.50 | 55           | 11               |


## 3.3 Daily Exposure Budget (Dollars)

$$E(A, e) = e \cdot A$$

At A = 150,000, e = 0.01: E = $1,500.

Total risk committed after n trades (including fees): n × (4500p + φ).

Remaining budget after n trades: E - n × (4500p + φ).

## 3.4 Fee Source: TSM fee_schedule

The fee φ is read from the account's TSM file at 19:00 EST alongside all other SOD-locked parameters. Each account has its own fee schedule:

```json
"fee_schedule": {
    "type": "TOPSTEP_EXPRESS",
    "fees_by_instrument": {
        "ES": {"round_turn": 2.80, "components": {"nfa_clearing": 2.80}},
        "MES": {"round_turn": 0.74, "components": {"nfa_clearing": 0.74}},
        "NQ": {"round_turn": 2.80, "components": {"nfa_clearing": 2.80}}
    },
    "slippage_model": {"type": "FIXED_TICKS", "ticks_per_side": 1}
}
```

φ = fee_schedule.fees_by_instrument[asset].round_turn × contracts. For single-contract trades: φ = round_turn directly.

If fee_schedule is absent, fall back to existing TSM `commission_per_contract` field × 2 (round-trip). If both absent, φ = 0 and a notification is sent to the user.

## 3.5 Desmos

```
p = 0.005
```

```
e = 0.01
```

```
phi = 2.80
```

```
R(x) = p * f(x) + phi/x {x >= 150000}
```

```
N(x) = floor((e * x) / (4500 * p + phi)) {x >= 150000}
```

```
E(x) = e * x {x >= 150000}
```

```
R_dollar = 4500 * p + phi
```

---

# PART 4 — CIRCUIT BREAKER SYSTEM

**Purpose:** Minimise losses effectively, without compromising edge or P&L negatively.

## 4.1 Intraday State Variables

All SOD-locked parameters (A, f(A), R, N, E) are fixed at 19:00 EST. The following evolve within the trading day:


| Symbol | Definition                                                         |
| ------ | ------------------------------------------------------------------ |
| t      | Time within 19:00–18:59 EST cycle                                  |
| n_t    | Trades completed by time t (n_t ≤ N)                               |
| r_j    | Realised dollar P&L of trade j                                     |
| L_t    | Cumulative P&L: L_t = Σ r_j for j = 1 to n_t                       |
| b      | Basket (= model m). Each trade is tagged with its generating model |
| L_b    | Cumulative P&L for basket b only: L_b = Σ r_j for j ∈ basket b     |
| n_b    | Trades completed from basket b                                     |


## 4.2 Layer 1 — Hard Halt (Account Survival)

$$H(L_t, \rho_j) = \begin{cases} 1 & \text{if } |L_t| + \rho_j < c \cdot e \cdot A  0 & \text{if } |L_t| + \rho_j \geq c \cdot e \cdot A \end{cases}$$

Where ρ_j = risk of the proposed trade j (contracts × (SL_distance × point_value + φ)). This is a **preemptive check**: the trade is blocked if taking it AND hitting SL would breach the halt threshold. This prevents the scenario where a trade is allowed at current L_t but its worst-case outcome pushes cumulative loss past the halt.

When H = 0, all trading stops. No exceptions, no conditional logic overrides this. c is the hard halt fraction (e.g., c = 0.5 means halt after 50% of daily exposure budget is lost).

**Dollar threshold at defaults:** c × e × A = 0.5 × 0.01 × 150,000 = $750.

**Preemptive example:** L_t = -$495, ρ_j = $495 (7 MES contracts × $70.74). Check: |-495| + 495 = $990 ≥ $750. **BLOCKED.** Without preemptive check, this trade would be allowed (|-495| < $750) and a second SL hit would push L_t to -$990, past the halt.

## 4.3 Layer 2 — Remaining Budget

$$B(n_t) = \begin{cases} 1 & \text{if } n_t < N  0 & \text{if } n_t \geq N \end{cases}$$

When B = 0, no further trades. This is the exposure cap. Remaining trade slots = N - n_t. Remaining dollar capacity = E - n_t × (4500p + φ).

## 4.4 Layer 3 — Conditional Expectancy Filter (Per-Basket)

### 4.4.1 Conditional Expectancy Function

For each basket b, the expected return of the next trade given basket b's cumulative P&L today:

$$\mu_b(L_b) = \bar{r}_b + \beta_b \cdot L_b$$

Where:

- r̄_b = unconditional mean trade return for basket b (from backtest, pre-estimated)
- β_b = sensitivity of next-trade return to cumulative basket loss (from backtest, pre-estimated)

**Interpretation of β_b:**

The regression r_{j+1} on L_b (signed cumulative P&L) produces β_b. Since L_b is NEGATIVE when losing:

- Positive β_b × negative L_b = negative adjustment → μ_b decreases → basket shuts down after enough loss.
- Negative β_b × negative L_b = positive adjustment → μ_b increases → basket stays open (recovery expected).


| β_b value                  | Meaning                                                                | Action                                                 |
| -------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------ |
| β_b ≈ 0 or not significant | Losses are noise                                                       | Basket stays open — only hard halt can stop it         |
| β_b > 0 (significant)      | Positive serial correlation — losses predict further losses            | Basket shuts down after L_b crosses L*_b = -r̄_b / β_b |
| β_b < 0 (significant)      | Negative serial correlation — losses predict recovery (mean reversion) | Basket stays open after losses — recovery expected     |


### 4.4.2 Per-Basket Filter

$$C_b(L_b) = \begin{cases} 1 & \text{if } \mu_b(L_b) > 0  0 & \text{otherwise} \end{cases}$$

### 4.4.3 Derived Halt Threshold (Per-Basket)

The crossover point where conditional expectancy turns negative (only exists when β_b < 0):

$$L^*_b = -\frac{\bar{r}_b}{\beta_b}$$

This is a **data-derived** circuit breaker threshold, not an arbitrary one. It comes directly from the regression. When cumulative basket loss exceeds L*_b, the filter shuts that basket down.

If β_b is not statistically significant (p > 0.05 in the regression) or sample size < 100 trade-day observations: set β_b = 0. The basket defaults to "always open" and only the hard halt can stop it. **Never act on a noisy β estimate.**

### 4.4.4 Time-Partitioned Budget (Optional Layer)

Split the day into windows indexed by w. Let α_w = fraction of daily exposure allocated to window w, where Σ α_w = 1:

$$E_w = \alpha_w \cdot e \cdot A$$

$$N_w = \left\lfloor \frac{\alpha_w \cdot e}{p \cdot f(A)} \right\rfloor$$

Each window tracks its own P&L independently:

$$L_w = \sum_{j \in w} r_j$$

Each window has its own halt:

$$H_w(L_w) = \begin{cases} 1 & \text{if } |L_w| < c \cdot E_w  0 & \text{otherwise} \end{cases}$$

Losses in window 1 do not consume window 2's budget. For AM/PM split: α_AM = α, α_PM = 1 - α.

## 4.5 Layer 4 — Correlation-Adjusted Conditional Sharpe

### 4.5.1 Marginal Portfolio Variance

The marginal variance contribution of adding trade j+1 given n_t existing trades, using average within-day correlation ρ̄:

$$\Delta\sigma^2_{j+1} = \sigma^2\big(1 + 2n_t\bar{\rho}\big)$$

Where σ² is per-trade return variance (pre-estimated from backtest) and ρ̄ is average pairwise same-day trade correlation (pre-estimated from backtest).

### 4.5.2 Conditional Sharpe Ratio

$$S_{j+1}(L_t, n_t) = \frac{\mu_b(L_b)}{\sigma\sqrt{1 + 2n_t\bar{\rho}}}$$

As more correlated trades accumulate (n_t rises, ρ̄ > 0), the denominator grows and S shrinks — progressively harder for additional trades to qualify.

### 4.5.3 Correlation-Adjusted Filter

$$Q(L_b, n_t) = \begin{cases} 1 & \text{if } S_{j+1} > \lambda  0 & \text{otherwise} \end{cases}$$

Where λ = minimum conditional Sharpe threshold (default λ = 0).

## 4.6 Composite Decision Function

Trade j+1 from basket b is taken if and only if ALL layers pass:

$$D_{j+1}(L_t, L_b, n_t, \rho_j) = H(L_t, \rho_j) \cdot B(n_t) \cdot C_b(L_b) \cdot Q(L_b, n_t)$$

Expanding — **take the trade iff:**

$$|L_t| + \rho_j < c \cdot e \cdot A \quad \text{AND} \quad n_t < N \quad \text{AND} \quad \bar{r}_b + \beta_b \cdot L_b > 0 \quad \text{AND} \quad \frac{\bar{r}_b + \beta_b \cdot L_b}{\sigma\sqrt{1 + 2n_t\bar{\rho}}} > \lambda$$

If time-partitioned budgets are active, replace H(L_t) with H_w(L_w) for the active window.

## 4.7 Parameter Register

### SOD-Locked (recalculate at 19:00 EST)


| Parameter  | Description               | Source                         |
| ---------- | ------------------------- | ------------------------------ |
| A          | Account value             | Topstep dashboard at 19:00 EST |
| f(A)       | MDD%                      | Computed: 4500/A               |
| R(A, p)    | Risk per trade (% of A)   | Computed: p × f(A)             |
| N(A, p, e) | Max trades per day        | Computed: ⌊e / (p × f(A))⌋     |
| E(A, e)    | Daily exposure budget ($) | Computed: e × A                |


### Strategy Parameters (fixed until P1 re-validates)


| Parameter | Description                          | Estimated From                        |
| --------- | ------------------------------------ | ------------------------------------- |
| p         | Fraction of MDD% risked per trade    | Grid search via model generator       |
| e         | Daily exposure fraction              | Grid search via model generator       |
| c         | Hard halt fraction                   | Grid search via model generator       |
| α         | AM/PM budget split ratio             | Grid search (if time partitions used) |
| λ         | Minimum conditional Sharpe threshold | Grid search (default 0)               |


### Per-Basket Parameters (pre-estimated from backtest)


| Parameter | Description                         | Estimated From                                                                        |
| --------- | ----------------------------------- | ------------------------------------------------------------------------------------- |
| r̄_b      | Unconditional mean return, basket b | Sample mean of all trades from model m in backtest                                    |
| β_b       | Loss-predictiveness, basket b       | OLS regression: r_{j+1} on L_b at time of trade j, across all historical days         |
| σ         | Per-trade return std dev            | Sample std of all trade returns in backtest                                           |
| ρ̄        | Average same-day trade correlation  | Pairwise correlation of returns within same day, averaged across all days in backtest |


### β_b Estimation Method

For each model m (basket b), across all historical trading days d:

1. Order trades within day d chronologically for basket b
2. For each trade j, record: L_{b,d}(j) = cumulative P&L of basket b on day d at the moment trade j is about to be taken
3. Record: r_{b,d}(j) = realised return of trade j
4. Pool all (L_{b,d}(j), r_{b,d}(j)) pairs across all days
5. Run OLS: r = r̄_b + β_b × L + ε
6. Require: p-value on β_b < 0.05 AND n > 100 observations. If either fails, set β_b = 0.

## 4.8 Desmos (Circuit Breaker)

```
c = 0.5
```

```
r_bar = 25
```

```
B = -0.001
```

```
s = 100
```

```
rho = 0.15
```

```
lam = 0
```

```
L_halt(x) = c * e * x {x >= 150000}
```

```
mu(L) = r_bar + B * L
```

```
S(L, n) = mu(L) / (s * sqrt(1 + 2 * n * rho))
```

```
L_star = -r_bar / B {B < 0}
```

---

# PART 5 — COMPLETE DESMOS REFERENCE

All equations below are copy-paste ready for Desmos. Paste each as a separate expression.

### Sliders (adjust these)

```
p = 0.005
e = 0.01
phi = 2.80
c = 0.5
r_bar = 25
B = -0.001
s = 100
rho = 0.15
lam = 0
```

### MDD% Functions (Part 1)

```
f(x) = 4500/x {x >= 150000}
d(x) = -4500/x^2 {x >= 150000}
q(x) = 9000/x^3 {x >= 150000}
```

### Payout Functions (Part 2)

```
W(x) = min(5000, max(0, 0.5(x - 150000)))
g(x) = 4500/(x - W(x)) {x > 150000}
h(x) = g(x) - f(x) {x > 150000}
```

### Threshold Lines (Part 2)

```
y = 0.03
y = 0.028
y = 0.025
y = 0.02
```

### Trade Sizing (Part 3)

```
R(x) = p * f(x) + phi/x {x >= 150000}
N(x) = floor((e * x) / (4500 * p + phi)) {x >= 150000}
E(x) = e * x {x >= 150000}
R_dollar = 4500 * p + phi
```

### Circuit Breaker (Part 4)

```
L_halt(x) = c * e * x {x >= 150000}
mu(L) = r_bar + B * L
S(L, n) = mu(L) / (s * sqrt(1 + 2 * n * rho))
L_star = -r_bar / B {B < 0}
```

---

# PART 6 — PLACEMENT IN P3 ARCHITECTURE

## 6.1 Function-to-Component Map

Every function from Parts 1–4 has a single home in the P3 architecture. No function spans multiple components.

### Command Block 8 — Daily Reconciliation (19:00 EST)

Runs once per day at 19:00 EST when Topstep recalculates MDD. Computes all SOD-locked parameters for each account.


| Function       | Formula                                           | What It Produces                              |
| -------------- | ------------------------------------------------- | --------------------------------------------- |
| f(A)           | 4500/A                                            | MDD% for this account                         |
| φ              | fee_schedule.fees_by_instrument[asset].round_turn | Expected fee per trade ($)                    |
| R_eff(A, p, φ) | p · f(A) + φ/A                                    | Effective risk per trade (% of A, incl. fees) |
| N(A, p, e, φ)  | ⌊(e · A) / (4500p + φ)⌋                           | Max trades for next day                       |
| E(A, e)        | e · A                                             | Daily exposure budget ($)                     |
| W(A)           | min(5000, 0.5(A − 150000))                        | Max payout available                          |
| g(A)           | 4500 / (A − W(A))                                 | Post-payout MDD%                              |
| L_halt         | c · e · A                                         | Hard halt threshold ($)                       |


**Per-account:** Each account ac has its own A (from API or manual reconciliation), its own TSM constraints, and its own set of SOD-locked values. These are stored in P3-D08[ac] alongside the existing TSM state.

**Data source for A:** API-connected accounts pull balance from `adapter.get_account_status().balance` (Command Block 3, 4 inbound fields). Manual accounts: user confirms via GUI prompt (Command Block 8 existing flow).

### Online Block 1 — Pre-Session Data Ingestion

No new computation. Online Block 1 READS the SOD-locked values from P3-D08[ac] that were computed at 19:00 EST by Command Block 8. These values feed into Block 4 (Kelly sizing) and the new Block 7 circuit breaker functions.

### Online Block 4 — Kelly Sizing (Extended)

The Topstep optimisation functions add an **additional constraint layer** to the existing Kelly pipeline. They do NOT replace Kelly. The existing flow:

```
kelly_contracts = account_kelly × account_capital / risk_per_contract
final_contracts = min(kelly_contracts, tsm_cap)
```

Becomes:

```
kelly_contracts = account_kelly × account_capital / risk_per_contract
topstep_cap = floor(E / (strategy_sl × point_value))    # from SOD-locked E
final_contracts = min(kelly_contracts, tsm_cap, topstep_cap)
```

The Topstep daily exposure budget E = e × A acts as a ceiling on total daily risk committed. `min()` — the most conservative answer always applies.

### Contract Scaling — Simultaneous Open Position Limit (XFA Only)

**Critical distinction:** The contract scaling plan limits the maximum contracts **held open simultaneously**, NOT total daily trading volume. When a position closes, those contract slots become available again.

**XFA $150k Scaling Tiers (evaluated end-of-day, applies next session):**


| Profit Level  | Max Minis Open | Max Micros Open |
| ------------- | -------------- | --------------- |
| < $1,500      | 3              | 30              |
| $1,500-$2,000 | 4              | 40              |
| $2,000-$3,000 | 5              | 50              |
| $3,000-$4,500 | 10             | 100             |
| > $4,500      | 15             | 150             |


**10:1 ratio:** 1 mini = 10 micros. Any combination that totals ≤ tier limit in mini-equivalents (e.g., at 5 lots: long 2 MES minis + short 30 MCL micros = 2 + 3 = 5 lots).

**Live accounts:** Scaling plan does NOT apply. Replaced by Dynamic Live Risk Expansion (position size adjusted by contacting support, not automatic).

**Integration with Kelly Block 4:**

```
kelly_contracts = account_kelly × account_capital / risk_per_contract
topstep_daily_cap = floor(E / (strategy_sl × point_value))
scaling_cap = current_scaling_tier_micros - current_open_positions_micros  # AVAILABLE slots
final_contracts = min(kelly_contracts, tsm_cap, topstep_daily_cap, scaling_cap)
```

The `scaling_cap` is DYNAMIC within the day — it depends on how many positions are currently open. As positions close, scaling_cap increases. This is fundamentally different from the static daily caps (E, N).

**Tracking:** P3 Online Block 7 already monitors open positions (existing functionality). The scaling cap check reads `current_open_positions_micros` from Block 7's position tracker.

### Online Block 7 — Intraday Position Monitoring (Extended)

This is the home of the circuit breaker system. Block 7 already monitors open positions intraday. The circuit breaker adds per-signal screening BEFORE a trade is taken.

**New function within Block 7:**

```
P3-PG-27B: "circuit_breaker_screen_A"

INPUT: incoming_signal (asset, direction, model m, contracts)
INPUT: account_id ac
INPUT: SOD-locked params from P3-D08[ac]: N, E, L_halt, f(A)
INPUT: intraday state from P3-D23[ac]: L_t, n_t, L_b per basket, n_b per basket
INPUT: pre-estimated params from P3-D25[ac]: r̄_b, β_b, σ, ρ̄

# Basket = model m from the signal
b = incoming_signal.model_m

# Compute worst-case risk for this trade
risk_per_contract = SL_distance × point_value + φ
rho_j = incoming_signal.contracts × risk_per_contract

# Layer 0: Simultaneous position limit (XFA only — Live has no scaling)
IF account.topstep_params.scaling_plan_active:
    current_open_micros = sum(open_positions.micro_equivalent for all open positions)
    proposed_micros = incoming_signal.contracts  # already in micros
    IF current_open_micros + proposed_micros > account.scaling_tier_micros:
        RETURN {take: False, reason: "SCALING_CAP_EXCEEDED",
                open: current_open_micros, proposed: proposed_micros,
                cap: account.scaling_tier_micros}

# Layer 1: Hard halt (PREEMPTIVE — checks projected worst-case, not just current L_t)
IF abs(L_t) + rho_j >= L_halt:
    RETURN {take: False, reason: "HARD_HALT_PREEMPTIVE", L_t: L_t, rho_j: rho_j, projected: abs(L_t) + rho_j, L_halt: L_halt}

# Layer 2: Budget
IF n_t >= N:
    RETURN {take: False, reason: "BUDGET_EXHAUSTED", n_t: n_t, N: N}

# Layer 3: Per-basket conditional expectancy
mu_b = r̄_b + β_b × L_b
IF mu_b <= 0:
    RETURN {take: False, reason: "BASKET_NEGATIVE_EXPECTANCY", basket: b, L_b: L_b, mu_b: mu_b}

# Layer 4: Correlation-adjusted conditional Sharpe
S = mu_b / (σ × sqrt(1 + 2 × n_t × ρ̄))
IF S <= λ:
    RETURN {take: False, reason: "SHARPE_BELOW_THRESHOLD", S: S, lambda: λ}

# All layers passed
RETURN {take: True, layers_passed: [1, 2, 3, 4]}
```

**Intraday state tracking (new dataset P3-D23):**

After each trade outcome is logged (TAKEN confirmation from Command Block 2):

```
P3-D23[ac].L_t += trade_pnl
P3-D23[ac].n_t += 1
P3-D23[ac].L_b[m] += trade_pnl
P3-D23[ac].n_b[m] += 1
```

Reset at 19:00 EST (same cycle as Command Block 8 reconciliation):

```
P3-D23[ac].L_t = 0
P3-D23[ac].n_t = 0
P3-D23[ac].L_b = {m: 0 for all m}
P3-D23[ac].n_b = {m: 0 for all m}
```

### Offline Block 8 — Kelly Parameter Updates (Extended)

β_b estimation runs here, alongside existing Kelly parameter updates. Uses P3-D03 (trade outcome log) which has full timestamps — not P1's D-22 which is daily resolution only.

**New function within Block 8:**

```
P3-PG-16C: "circuit_breaker_param_estimator_A"

INPUT: P3-D03 (trade outcome log — full intraday timestamps, per model m, per account ac)

FOR EACH account ac:
    FOR EACH model m (basket b) with ≥ 100 intraday trade observations:

        # Build regression dataset
        dataset = []
        FOR EACH trading day d in P3-D03:
            trades_b_d = P3-D03.filter(account=ac, model=m, day=d).sort_by(timestamp)
            cumulative = 0
            FOR EACH trade j in trades_b_d:
                dataset.append({L_b: cumulative, r: trade_j.pnl})
                cumulative += trade_j.pnl

        # OLS regression
        r̄_b, β_b, p_value, n_obs = ols_regression(dataset, y="r", x="L_b")

        # Significance gate
        IF p_value > 0.05 OR n_obs < 100:
            β_b = 0    # default: losses uninformative for this basket

        # Estimate per-trade volatility and same-day correlation
        σ = std(all trade returns for model m in account ac)
        ρ̄ = mean_pairwise_same_day_correlation(P3-D03, account=ac)

        # Store
        P3-D25[ac][m] = {r̄_b: r̄_b, β_b: β_b, σ: σ, ρ̄: ρ̄, n_obs: n_obs, last_updated: now()}

# Cold start: before 100 observations accumulated, β_b = 0 for all baskets.
# Hard halt (Layer 1) provides account protection from day 1.
# Conditional expectancy filter (Layers 3-4) activates only after sufficient data.
```

**Run frequency:** Same as existing Kelly updates — after each trade outcome batch, or daily at minimum.

---

# PART 7 — DATA SOURCES: PULL (A) vs GENERATE (B)

Every parameter falls into one of two categories:

## Category A — Pull and Reuse

Pre-computed values that are estimated once (or periodically) and then read at runtime. These are stored in persistent datasets and loaded at session open.


| Parameter | Source                                                      | Dataset                   | Update Frequency                                   |
| --------- | ----------------------------------------------------------- | ------------------------- | -------------------------------------------------- |
| p         | P1 model generator grid search → OO validation              | P3-D08[ac].topstep_params | Locked after P1 validation; changes only on re-run |
| e         | P1 model generator grid search → OO validation              | P3-D08[ac].topstep_params | Same as p                                          |
| c         | P1 model generator grid search OR pseudotrader optimisation | P3-D08[ac].topstep_params | Same                                               |
| α         | Pseudotrader optimisation (if time partitions used)         | P3-D08[ac].topstep_params | Same                                               |
| λ         | Pseudotrader optimisation                                   | P3-D08[ac].topstep_params | Same                                               |
| r̄_b      | Offline Block 8 regression                                  | P3-D25[ac][m]             | After each trade batch                             |
| β_b       | Offline Block 8 regression                                  | P3-D25[ac][m]             | After each trade batch                             |
| σ         | Offline Block 8 computation                                 | P3-D25[ac][m]             | After each trade batch                             |
| ρ̄        | Offline Block 8 computation                                 | P3-D25[ac][m]             | After each trade batch                             |


## Category B — Generate on Command

Computed fresh at a specific trigger point. Not stored long-term — overwritten each cycle.


| Parameter      | Trigger              | Source                                            | Stored In                                    |
| -------------- | -------------------- | ------------------------------------------------- | -------------------------------------------- |
| A              | 19:00 EST daily      | API adapter balance OR manual confirmation        | P3-D08[ac].current_balance                   |
| f(A)           | 19:00 EST daily      | Computed from A                                   | P3-D08[ac].topstep_state.mdd_pct             |
| φ              | 19:00 EST daily      | From TSM fee_schedule for active instrument       | P3-D08[ac].topstep_state.fee_per_trade       |
| scaling_tier   | 19:00 EST daily      | Profit tier lookup (XFA). Not applicable in Live. | P3-D08[ac].topstep_state.scaling_tier_micros |
| R_eff(A, p, φ) | 19:00 EST daily      | Computed from A, p, φ                             | P3-D08[ac].topstep_state.risk_per_trade_eff  |
| N(A, p, e, φ)  | 19:00 EST daily      | Computed from A, p, e, φ                          | P3-D08[ac].topstep_state.max_trades          |
| E(A, e)        | 19:00 EST daily      | Computed from A, e                                | P3-D08[ac].topstep_state.daily_exposure      |
| L_halt         | 19:00 EST daily      | Computed from c, e, A                             | P3-D08[ac].topstep_state.hard_halt_threshold |
| W(A)           | 19:00 EST daily      | Computed from A                                   | P3-D08[ac].topstep_state.max_payout          |
| g(A)           | 19:00 EST daily      | Computed from A, W(A)                             | P3-D08[ac].topstep_state.post_payout_mdd_pct |
| L_t            | Intraday (per trade) | Running sum                                       | P3-D23[ac].L_t                               |
| L_b            | Intraday (per trade) | Running sum per basket                            | P3-D23[ac].L_b[m]                            |
| n_t, n_b       | Intraday (per trade) | Running count                                     | P3-D23[ac].n_t, n_b[m]                       |


**Note on p, e, c:** These can be estimated via P1's model generator grid search (treating them as strategy parameters alongside TP/SL). However, p, e, c depend on intraday trade sequences, which P1 does not model — P1 operates at daily resolution. The pseudotrader (Part 8 below) provides the intraday-resolution validation that P1 cannot. Recommended path: set initial values from P1 grid search, then refine via pseudotrader once P3 has accumulated intraday data.

---

# PART 8 — PSEUDOTRADER EXTENSION FOR CIRCUIT BREAKER TESTING

## 8.1 Purpose

Extends Offline Block 3 (pseudotrader) to replay historical trade sequences at **intraday resolution, per-account**, applying the circuit breaker decision function at each trade. Compares P&L WITH circuit breaker vs WITHOUT to validate parameter choices.

The existing pseudotrader replays at signal level (one signal per session per asset). This extension replays at trade level (multiple trades per day within each account).

## 8.2 Scope by Version


| Version | Pseudotrader Runs Per               | Aggregation                                           |
| ------- | ----------------------------------- | ----------------------------------------------------- |
| V1      | Per account (single user)           | Per-account results                                   |
| V2      | Per account, per user               | Per-user aggregation across accounts                  |
| V3      | Per account, per user, per strategy | Per-user aggregation + capital arbitration simulation |


The per-account logic is identical across all versions. V2 adds a user-level aggregation loop. V3 adds strategy competition within each account. Spec below is V1-compatible and V2/V3-extensible.

## 8.3 Pseudocode

```
P3-PG-09B: "pseudotrader_circuit_breaker_A"

INPUT: account_id ac
INPUT: circuit_breaker_params {p, e, c, α, λ}  # proposed or current
INPUT: historical_window from P3-D03 (all trades for account ac, with intraday timestamps)
INPUT: basket_params from P3-D25[ac] {r̄_b, β_b, σ, ρ̄ per model m}

# ══════════════════════════════════════════
# PHASE 1: REPLAY WITHOUT CIRCUIT BREAKER
# ══════════════════════════════════════════

baseline_results = []
FOR EACH trading day d IN historical_window:

    trades_d = P3-D03.filter(account=ac, day=d).sort_by(timestamp)

    day_pnl = 0
    FOR EACH trade j IN trades_d:
        day_pnl += trade_j.pnl

    baseline_results.append({
        day: d,
        trades_taken: len(trades_d),
        trades_blocked: 0,
        day_pnl: day_pnl
    })

# ══════════════════════════════════════════
# PHASE 2: REPLAY WITH CIRCUIT BREAKER
# ══════════════════════════════════════════

cb_results = []
FOR EACH trading day d IN historical_window:

    # SOD-lock for this day (use actual account balance from that day)
    A_d = get_account_balance_at(ac, d, time="19:00_previous_day")
    f_d = 4500 / A_d
    N_d = floor(e / (p * f_d))
    E_d = e * A_d
    L_halt_d = c * E_d

    # Intraday state — reset per day
    L_t = 0
    n_t = 0
    L_b = {m: 0 for all m}
    n_b = {m: 0 for all m}

    trades_d = P3-D03.filter(account=ac, day=d).sort_by(timestamp)
    day_pnl = 0
    trades_taken = 0
    trades_blocked = 0
    block_log = []

    FOR EACH trade j IN trades_d:
        m = trade_j.model

        # Run composite decision function
        D = circuit_breaker_screen(L_t, L_b[m], n_t, n_b[m],
                                   L_halt_d, N_d,
                                   basket_params[m].r̄_b, basket_params[m].β_b,
                                   basket_params[m].σ, basket_params[m].ρ̄,
                                   λ)

        IF D.take:
            day_pnl += trade_j.pnl
            trades_taken += 1
            L_t += trade_j.pnl
            n_t += 1
            L_b[m] += trade_j.pnl
            n_b[m] += 1
        ELSE:
            trades_blocked += 1
            block_log.append({
                trade_idx: j,
                model: m,
                reason: D.reason,
                would_have_pnl: trade_j.pnl,
                L_t_at_decision: L_t,
                L_b_at_decision: L_b[m]
            })

    cb_results.append({
        day: d,
        trades_taken: trades_taken,
        trades_blocked: trades_blocked,
        day_pnl: day_pnl,
        block_log: block_log
    })

# ══════════════════════════════════════════
# PHASE 3: COMPARE
# ══════════════════════════════════════════

comparison = {
    account: ac,
    params_tested: {p, e, c, α, λ},
    total_days: len(historical_window),

    # Aggregate metrics
    baseline_total_pnl: sum(baseline.day_pnl),
    cb_total_pnl: sum(cb.day_pnl),
    pnl_delta: cb_total_pnl - baseline_total_pnl,

    baseline_sharpe: sharpe(baseline_results),
    cb_sharpe: sharpe(cb_results),
    sharpe_delta: cb_sharpe - baseline_sharpe,54r3

    baseline_max_dd: max_drawdown(baseline_results),
    cb_max_dd: max_drawdown(cb_results),
    dd_improvement: baseline_max_dd - cb_max_dd,

    total_trades_blocked: sum(cb.trades_blocked),
    block_rate: total_trades_blocked / sum(baseline.trades_taken),

    # Blocked trade analysis
    blocked_would_have_won: count(block_log WHERE would_have_pnl > 0),
    blocked_would_have_lost: count(block_log WHERE would_have_pnl <= 0),
    blocked_win_pnl_sacrificed: sum(would_have_pnl WHERE would_have_pnl > 0),
    blocked_loss_pnl_saved: abs(sum(would_have_pnl WHERE would_have_pnl <= 0)),

    # Per-layer breakdown
    blocks_by_reason: {
        "HARD_HALT": count,
        "BUDGET_EXHAUSTED": count,
        "BASKET_NEGATIVE_EXPECTANCY": count,
        "SHARPE_BELOW_THRESHOLD": count
    },

    # Per-basket β_b validation
    basket_analysis: {
        m: {
            β_b: basket_params[m].β_b,
            trades_blocked: count(blocks for model m),
            loss_saved: sum(|would_have_pnl| for losses blocked in model m),
            edge_sacrificed: sum(would_have_pnl for wins blocked in model m)
        } for each model m
    }
}

# ══════════════════════════════════════════
# PHASE 4: ANTI-OVERFITTING VALIDATION
# ══════════════════════════════════════════

pbo = compute_CSCV_PBO(cb_results, S=16)
dsr = compute_DSR(cb_sharpe, N_param_sets_tested, skew, kurtosis, T)

comparison.pbo = pbo
comparison.dsr = dsr
comparison.recommendation = "ADOPT" if (sharpe_delta > 0 AND dd_improvement > 0 AND pbo < 0.5) else "REVIEW"

# ══════════════════════════════════════════
# PHASE 5: STORE
# ══════════════════════════════════════════

P3-D11.append(comparison)
GENERATE RPT-09(comparison)

RETURN comparison
```

## 8.4 Grid Search Mode

To find optimal circuit breaker parameters, the pseudotrader runs Phase 1 once, then loops Phase 2 across a parameter grid:

```
P3-PG-09C: "circuit_breaker_grid_search_A"

INPUT: account_id ac
INPUT: parameter_grid {
    c_values: [0.3, 0.4, 0.5, 0.6, 0.7],
    lambda_values: [0, 0.1, 0.2, 0.5],
    # p and e come from P1 model generator — not grid-searched here
}

# Phase 1 runs once (no circuit breaker)
baseline = replay_without_cb(ac, historical_window)

# Phase 2 runs for each parameter combination
results = []
FOR EACH c IN c_values:
    FOR EACH λ IN lambda_values:
        cb_result = replay_with_cb(ac, historical_window, {c: c, λ: λ, ...})
        comparison = compare(baseline, cb_result)
        comparison.params = {c: c, λ: λ}
        results.append(comparison)

# Rank by Sharpe improvement, filtered by PBO < 0.5
valid_results = [r for r in results if r.pbo < 0.5]
valid_results.sort(by=sharpe_delta, descending=True)

# Best parameter set
best = valid_results[0]
P3-D25[ac].circuit_breaker_params = best.params
```

## 8.5 V2 Aggregation Extension (Future)

```
# V2: per-user aggregation
FOR EACH user u:
    user_accounts = P3-D16[u].accounts
    user_results = []
    FOR EACH ac IN user_accounts:
        result = pseudotrader_circuit_breaker(ac, params, historical_window)
        user_results.append(result)

    # Aggregate across user's accounts
    user_summary = {
        user: u,
        total_pnl_delta: sum(r.pnl_delta for r in user_results),
        total_dd_improvement: sum(r.dd_improvement for r in user_results),
        total_blocked: sum(r.total_trades_blocked for r in user_results),
        per_account: user_results
    }
```

## 8.6 New Datasets


| Dataset | Scope                  | Contents                                                                                           |
| ------- | ---------------------- | -------------------------------------------------------------------------------------------------- |
| P3-D23  | Per account, intraday  | Running circuit breaker state: L_t, n_t, L_b[m], n_b[m]. Reset at 19:00 EST.                       |
| P3-D25  | Per account, per model | Pre-estimated circuit breaker params: r̄_b, β_b, σ, ρ̄, plus locked strategy params p, e, c, α, λ. |


Both use QuestDB (same as all P3-D datasets). P3-D23 is hot state (Redis-cached for real-time access by Online Block 7). P3-D25 is warm state (loaded at session open).

## 8.7 Cold Start Protocol

Before P3-D03 has accumulated sufficient intraday trade data (< 100 observations per basket):


| Layer                            | Cold Start Behaviour                                                                                                          |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Layer 1 (Hard halt)              | **Active from day 1.** Uses c from P1 grid search or default c = 0.5. No data dependency.                                     |
| Layer 2 (Budget)                 | **Active from day 1.** N computed from SOD-locked params. No data dependency.                                                 |
| Layer 3 (Conditional expectancy) | **Disabled.** β_b = 0 for all baskets → μ_b = r̄_b > 0 always (assuming positive-expectancy strategy). Filter never triggers. |
| Layer 4 (Correlation Sharpe)     | **Disabled.** ρ̄ = 0 → denominator = σ → S = μ_b/σ ≈ unconditional Sharpe > 0 (if λ = 0). Filter never triggers.              |


Layers 3–4 activate automatically once Offline Block 8 accumulates ≥ 100 observations and produces statistically significant β_b estimates. No manual intervention required.