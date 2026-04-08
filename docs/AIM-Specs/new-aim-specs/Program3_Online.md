# Program 3 — Captain (Online) Specification

**Version:** 1.0
**Created:** 2026-03-01
**Purpose:** Complete specification of the Captain (Online) continuous 24/7 signal engine — the component that evaluates at each session open, generates trading decisions, and monitors open positions intraday.
**Architecture reference:** `Program3_Architecture.md`
**Companion specs:** `Program3_Offline.md`, `Program3_Command.md`

---

# OVERVIEW

Captain (Online) is the continuous signal engine. It runs 24/7, evaluating at each major trading session open (NY, London, APAC) and monitoring open positions throughout the trading day. It reads outputs from Captain (Offline) but never writes to Offline datasets directly — trade outcomes are logged to P3-D03 which Offline processes asynchronously.

**Key design principles:**
- **Strategy-agnostic:** Processes ANY strategy type from Program 1 (ORB, swing, multi-day)
- **Multi-session:** Evaluates at NY (09:30 America/New_York), London (08:00 Europe/London), APAC sessions. All internal timestamps stored in America/New_York (see `Program3_Architecture.md` Section 7)
- **Continuous monitoring:** Tracks open positions intraday with real-time alerts
- **Read-only from Offline:** Uses P3-D01, D02, D05, D08, D12 but never modifies them
- **Per-user capital siloing:** Blocks 1-3 compute shared market intelligence once per session. Blocks 4-6 run independently for each active user using that user's capital silo (P3-D16), accounts, and risk allocation. See `UserManagementSetup.md` Section 10.

**9 Blocks:**
1. Pre-Session Data Ingestion
2. Regime Probability Computation
3. AIM Aggregation (MoE/DMA)
4. Kelly Sizing Under Constraints
5. Universe-Level Trade Selection
5B. Signal Quality Gate
6. Signal Output
7. Intraday Position Monitoring
8. Network Concentration Monitor
9. Capacity Evaluation (Session-End)

---

# BLOCK 1 — PRE-SESSION DATA INGESTION

## 1.1 Purpose

Loads all required data and computes pre-session features for the upcoming evaluation. Session-aware: different assets are evaluated at different session opens.

**Infrastructure note:** Market data is ingested and cached in Redis for real-time access by subsequent blocks. Feature computations stored in Redis pub/sub channels for immediate availability to Blocks 2–6. See `Program3_Architecture.md` Section 16.2.

## 1.2 Pseudocode

```
P3-PG-21: "data_ingestion_A"

INPUT: session_id (NY=1, LON=2, APAC=3)

# Step 1: Determine which assets to evaluate this session
active_assets = []
FOR EACH asset u IN P3-D00:
    IF P3-D00[u].captain_status == "ACTIVE" AND session_match(u, session_id):
        active_assets.append(u)

IF len(active_assets) == 0:
    LOG "No active assets for session {session_id}"
    RETURN empty

# Step 1b: DATA MODERATOR — pre-ingestion sanity checks
# Data sources for each asset are configured in P3-D00[u].data_sources
# (see P3_Dataset_Schemas.md and Architecture Section 15.1)
# Each source is validated here; failures → DATA_HOLD for this asset
FOR EACH asset u IN P3-D00 WHERE P3-D00[u].captain_status == "ACTIVE":
    
    # Price bounds check
    current_price = get_latest_price(u)
    prior_close = close_price(u, yesterday)
    IF prior_close > 0:
        price_deviation = abs(current_price - prior_close) / prior_close
        IF price_deviation > 0.05:  # >5% from prior close
            P3-D00[u].data_quality_flag = "PRICE_SUSPECT"
            create_incident("DATA_QUALITY", "P2_HIGH", "DATA_FEED",
                           "Price for {u} deviates {price_deviation*100:.1f}% from prior close. Halting signals.",
                           affected_users=get_all_active_user_ids())
            P3-D00[u].captain_status = "DATA_HOLD"  # exclude until ADMIN confirms
            CONTINUE
    
    # Volume sanity check
    current_volume = get_current_session_volume(u)
    avg_volume = avg_session_volume_20d(u)
    IF avg_volume > 0 AND current_volume == 0:
        P3-D00[u].data_quality_flag = "ZERO_VOLUME"
        LOG "Volume = 0 for {u} — data feed may be stale"
    ELIF avg_volume > 0 AND current_volume > avg_volume * 10:
        P3-D00[u].data_quality_flag = "VOLUME_EXTREME"
        LOG "Volume for {u} is {current_volume/avg_volume:.0f}x normal — flagged"
    ELSE:
        P3-D00[u].data_quality_flag = "CLEAN"
    
    # Missing data check — validates raw data SOURCE availability BEFORE feature computation
    # (features[u] is populated later in Step 1d; this checks whether the underlying
    # data feeds are producing data, not whether computed features exist yet)
    FOR EACH required_feature IN get_required_features(u):
        source_available = check_data_source_for_feature(u, required_feature)
        IF NOT source_available:
            LOG "Data source unavailable for feature {required_feature} for {u} — will use last known value in Step 1d"
            P3-D00[u].data_quality_flag = "STALE_FEATURE"
    
    # Timestamp validation
    IF NOT has_timezone_offset(get_latest_timestamp(u)):
        create_incident("DATA_QUALITY", "P2_HIGH", "DATA_FEED",
                       "Data for {u} missing timezone offset. Rejecting.",
                       affected_users=get_all_active_user_ids())
        CONTINUE

# Log data quality summary to P3-D17 for System Overview
P3-D17.data_quality_log.append({
    session: session_id, timestamp: now(),
    assets_checked: len(active_assets),
    clean: count(flag == "CLEAN"),
    flagged: count(flag != "CLEAN"),
    held: count(status == "DATA_HOLD")
})

# Step 1c: Contract roll calendar check
FOR EACH asset u IN P3-D00:
    roll_info = P3-D00[u].roll_calendar
    IF roll_info:
        days_to_roll = (roll_info.next_roll_date - today()).days
        
        IF days_to_roll <= 0 AND NOT roll_info.roll_confirmed:
            # Roll date reached — pause signals until roll is confirmed
            NOTIFY(user_id="ALL_ADMINS",
                   message="CONTRACT ROLL: {u} roll date is today ({roll_info.next_roll_date}). Signals paused until roll confirmed.",
                   priority="CRITICAL", action_required=True)
            P3-D00[u].captain_status = "ROLL_PENDING"
        
        ELIF days_to_roll <= 3:
            # Approaching roll — warn users
            NOTIFY(user_id="ALL_ADMINS",
                   message="CONTRACT ROLL: {u} rolls in {days_to_roll} days ({roll_info.next_roll_date}). Front month: {roll_info.current_contract} → {roll_info.next_contract}.",
                   priority="HIGH")
        
        IF P3-D00[u].captain_status == "ROLL_PENDING":
            # Exclude from active_assets until roll confirmed via GUI
            CONTINUE

# Step 1c: Validate system timezone
# All internal operations use America/New_York (see Program3_Architecture.md Section 7)
system_tz = "America/New_York"
ASSERT system_clock_timezone() == system_tz, "System clock not set to America/New_York"

# Step 2: Load Offline outputs (read-only)
# DATA LOADING CONVENTION: All READ/LOAD commands below query QuestDB. P1/P2 output files
# are loaded into QuestDB during initial setup (Implementation_Checklist Task 1.9) and on
# asset onboarding (asset_bootstrap → Command Block 10 validates paths → Offline loads files
# into QuestDB tables). P3-D datasets are written directly to QuestDB by Captain processes.
aim_states      = READ P3-D01  # AIM model states
aim_weights     = READ P3-D02  # DMA meta-weights
ewma_states     = READ P3-D05  # Regime-conditional return estimates
tsm_configs     = READ P3-D08  # Active TSM configurations
kelly_params    = READ P3-D12  # Kelly fractions, shrinkage factors
sizing_overrides = READ P3-D12.sizing_override  # Level 2 reductions

# Step 3: Load Program 2 outputs (read-only)
# Source files: P3-D00[asset].p1_data_path (e.g. /captain/data/p1_outputs/ES/)
#               P3-D00[asset].p2_data_path (e.g. /captain/data/p2_outputs/ES/)
# These are pre-loaded into QuestDB; READ here queries QuestDB, not files.
locked_strategies = READ P2-D06  # Locked (model, feature, threshold) per asset
regime_models     = READ P2-D07  # Trained regime classifiers per asset

# Step 4: Compute pre-session features for each asset
FOR EACH asset u IN active_assets:
    
    # Overnight return (close-to-open)
    features[u].overnight_return = (open_price(u, today) / close_price(u, yesterday)) - 1
    
    # VRP — AIM-01 (if active)
    IF aim_states["AIM-01"].status == ACTIVE:
        features[u].vrp = compute_vrp(u)  # E[RV] - IV
        features[u].vrp_overnight = compute_overnight_vrp(u)
    
    # IVTS — AIM-04 (CRITICAL regime filter)
    features[u].ivts = vix_close_yesterday / vxv_close_yesterday
    
    # Opening volume — AIM-15
    # or_minutes: OR formation window from model params (D-09[locked_strategies[u].m].strategy_params.OR_window)
    or_minutes = get_or_window_minutes(locked_strategies[u].m)
    features[u].opening_volume_ratio = volume_first_N_min(u, or_minutes) / avg_volume_first_N_min(u, or_minutes)
    
    # Economic calendar — AIM-06
    features[u].events_today = check_economic_calendar(today, asset=u)
    features[u].event_proximity = min_distance_to_event(features[u].events_today, session_open_time)
    
    # COT positioning — AIM-07 (weekly update)
    features[u].cot_smi = latest_smi_polarity(u)
    features[u].cot_speculator_z = speculator_z_score(u)
    
    # Cross-asset correlation — AIM-08
    features[u].correlation_es_cl = rolling_20d_correlation("ES", "CL")
    features[u].correlation_z = z_score(features[u].correlation_es_cl, trailing_252d)
    
    # Cross-asset momentum — AIM-09
    features[u].cross_momentum = compute_cross_asset_momentum(u, lookback=21)
    
    # GEX — AIM-03
    features[u].gex = compute_dealer_net_gamma(u)
    
    # Skew — AIM-02
    features[u].pcr = compute_put_call_ratio(u)
    features[u].put_skew = compute_dotm_otm_put_spread(u)
    
    # Calendar — AIM-10
    features[u].is_opex_window = is_within_opex_window(today)
    features[u].day_of_week = today.weekday()
    
    # Regime warning — AIM-11
    features[u].vix_z = z_score(vix_close_yesterday, trailing_252d)
    trailing_60d_vix_changes = get_trailing_vix_daily_changes(lookback=60)
    features[u].vix_daily_change_z = z_score(abs(vix_change_today), trailing_60d_vix_changes)
    IF u == "CL":
        features[u].cl_basis = (cl_spot - cl_front_futures) / cl_spot
    
    # Cost estimation — AIM-12
    features[u].current_spread = get_live_spread(u)
    features[u].spread_z = z_score(features[u].current_spread, trailing_60d_open_spreads)

RETURN active_assets, features, aim_states, aim_weights, ewma_states, kelly_params, locked_strategies, regime_models, tsm_configs, sizing_overrides
```

---

# BLOCK 1 APPENDIX — FEATURE COMPUTATION FUNCTIONS

All functions below are called by Block 1 (P3-PG-21) during pre-session data ingestion. Each function specifies: what it computes, what data it needs, and how to handle missing data. Research grounding in `AIM_Research_Notes.md`.

```
# ═══════════════════════════════════════════════════
# AIM-01 FEATURES (Volatility Risk Premium)
# ═══════════════════════════════════════════════════

FUNCTION compute_vrp(asset):
    # Volatility Risk Premium = Expected Realised Vol - Implied Vol
    # Positive VRP = IV is cheap (markets underpricing vol)
    # Negative VRP = IV is expensive (markets overpricing vol)
    # Data: ATM implied vol from options chain, RV from P2-D01
    # Research: Papers 34, 35 (AIM_Research_Notes.md AIM-01)
    
    iv = get_atm_implied_vol(asset, maturity="30d")  # 30-day ATM IV, prior close
    rv = P2-D01[asset].latest.sigma_t                # realised vol from P2 EWMA
    
    IF iv is None OR rv is None:
        RETURN None
    
    RETURN rv - iv  # positive = RV > IV (IV cheap)

FUNCTION compute_overnight_vrp(asset):
    # Overnight VRP: gap-implied vol vs realised overnight range
    # Data: overnight high/low/close from Globex session
    
    overnight_range = (overnight_high(asset) - overnight_low(asset)) / overnight_close(asset)
    iv_overnight = get_atm_implied_vol(asset, maturity="1d")  # next-day IV
    
    IF iv_overnight is None:
        RETURN None
    
    RETURN overnight_range - iv_overnight

# ═══════════════════════════════════════════════════
# AIM-02 FEATURES (Options Skew)
# ═══════════════════════════════════════════════════

FUNCTION compute_put_call_ratio(asset):
    # Put-Call Ratio: total put volume / total call volume (prior session)
    # Ideal: buyer-initiated open-position volume (Paper 47)
    # Fallback: aggregate volume ratio (noisier but available)
    # Data: CBOE options volume or broker options data
    
    put_vol = get_options_volume(asset, type="PUT", session="PRIOR_DAY")
    call_vol = get_options_volume(asset, type="CALL", session="PRIOR_DAY")
    
    IF call_vol is None OR call_vol == 0:
        RETURN None
    
    RETURN put_vol / call_vol

FUNCTION compute_dotm_otm_put_spread(asset):
    # DOTM-OTM Put IV Spread: deep OTM put IV minus slightly OTM put IV
    # Measures tail risk pricing (Paper 49)
    # Data: options IV surface, 10-30 day maturity
    
    dotm_put_iv = get_put_iv(asset, delta=0.10, maturity="30d")  # 10-delta put
    otm_put_iv = get_put_iv(asset, delta=0.25, maturity="30d")   # 25-delta put
    
    IF dotm_put_iv is None OR otm_put_iv is None:
        RETURN None
    
    RETURN dotm_put_iv - otm_put_iv  # positive = steep skew (crash risk elevated)

# ═══════════════════════════════════════════════════
# AIM-03 FEATURES (Gamma Exposure)
# ═══════════════════════════════════════════════════

FUNCTION compute_dealer_net_gamma(asset):
    # Dealer Net Gamma Exposure estimation from open interest
    # GEX = SUM(dealer_net_OI * gamma * multiplier * spot^2) across strikes
    # Dealers typically net short → negative gamma is default
    # Data: options open interest by strike/maturity, IV surface for greek computation
    # Research: Papers 52, 57 (AIM_Research_Notes.md AIM-03)
    
    spot = get_latest_price(asset)
    option_chain = get_option_chain(asset, max_maturity_days=30)
    
    IF option_chain is None OR len(option_chain) == 0:
        RETURN None
    
    gex = 0
    FOR EACH option IN option_chain:
        gamma = compute_bsm_gamma(spot, option.strike, option.maturity, option.iv, risk_free_rate)
        # Assume dealers are net short options (standard market-making model)
        dealer_net_oi = -option.open_interest  # negative = dealer short
        IF option.type == "PUT":
            dealer_net_oi = -dealer_net_oi     # put-call parity adjustment
        gex += dealer_net_oi * gamma * contract_multiplier(asset) * spot * spot
    
    RETURN gex  # positive = positive gamma (dampening); negative = negative gamma (amplification)

# ═══════════════════════════════════════════════════
# AIM-06 FEATURES (Economic Calendar)
# ═══════════════════════════════════════════════════

FUNCTION check_economic_calendar(date, asset):
    # Returns list of economic events on the given date relevant to the asset
    # Data: economic calendar file/API (see LocalFileRequirements.md item 75)
    # Each event has: name, time, tier (1=highest impact), asset_relevance
    
    all_events = LOAD economic_calendar WHERE event_date == date
    
    # Filter to relevant events
    relevant = []
    FOR EACH event IN all_events:
        IF asset IN event.affected_assets OR event.scope == "ALL":
            relevant.append({
                name: event.name,
                time: event.time,
                tier: event.tier,   # 1=NFP/FOMC, 2=CPI/GDP, 3=EIA/ISM, 4=Housing/PPI
                expected: event.consensus
            })
    
    RETURN relevant  # empty list if no events

FUNCTION min_distance_to_event(events, reference_time):
    # Returns minutes between reference_time and nearest event
    # Negative = event is before reference_time; positive = event is after
    
    IF events is None OR len(events) == 0:
        RETURN None
    
    distances = [(event.time - reference_time).total_minutes() for event in events]
    closest_idx = argmin([abs(d) for d in distances])
    
    RETURN distances[closest_idx]

# ═══════════════════════════════════════════════════
# AIM-07 FEATURES (COT Positioning)
# ═══════════════════════════════════════════════════

FUNCTION latest_smi_polarity(asset):
    # Smart Money Index polarity from COT data
    # SMI = institutional positioning vs individual positioning (relative)
    # Data: CFTC COT report (weekly, 3-day lag)
    # Research: Paper 98 (AIM_Research_Notes.md AIM-07)
    
    cot = LOAD latest_cot_report(asset)
    
    IF cot is None:
        RETURN None
    
    # TFF format for ES/NQ: dealer + asset_manager = institutional
    # Disaggregated for CL: managed_money = speculative
    institutional = cot.dealer_long - cot.dealer_short + cot.asset_mgr_long - cot.asset_mgr_short
    retail = cot.nonreportable_long - cot.nonreportable_short
    
    IF institutional > retail:
        RETURN 1     # institutional net long relative to retail = bullish
    ELIF institutional < retail:
        RETURN -1    # institutional net short relative to retail = bearish
    ELSE:
        RETURN 0

FUNCTION speculator_z_score(asset):
    # Large speculator net positioning as z-score vs 52-week history
    # Data: CFTC COT report, 52 weeks of history
    
    cot = LOAD latest_cot_report(asset)
    cot_history = LOAD cot_history(asset, weeks=52)
    
    IF cot is None OR len(cot_history) < 26:
        RETURN None
    
    spec_net = cot.noncommercial_long - cot.noncommercial_short
    spec_history = [c.noncommercial_long - c.noncommercial_short for c in cot_history]
    
    RETURN (spec_net - mean(spec_history)) / std(spec_history)

# ═══════════════════════════════════════════════════
# AIM-08 FEATURES (Cross-Asset Correlation)
# ═══════════════════════════════════════════════════

FUNCTION rolling_20d_correlation(asset1, asset2):
    # 20-trading-day rolling Pearson correlation of daily returns
    # Data: daily close prices for both assets (last 20 trading days)
    
    returns1 = daily_returns(asset1, lookback=20)
    returns2 = daily_returns(asset2, lookback=20)
    
    IF len(returns1) < 20 OR len(returns2) < 20:
        RETURN None
    
    RETURN pearson_correlation(returns1, returns2)

# ═══════════════════════════════════════════════════
# AIM-09 FEATURES (Cross-Asset Momentum)
# ═══════════════════════════════════════════════════

FUNCTION compute_cross_asset_momentum(asset, lookback=21):
    # Aggregate momentum signal from all traded assets using MACD
    # Positive = majority of assets trending up; negative = trending down
    # Research: Paper 19 (SLP with cross-asset MACD), Paper 116 (network momentum)
    
    all_assets = get_all_universe_assets()  # ES, NQ, CL, etc.
    signals = []
    
    FOR EACH a IN all_assets:
        close = daily_closes(a, lookback=max(26, lookback) + 9)  # need 26+9 for MACD
        IF len(close) < 35:
            CONTINUE
        macd_line = ema(close, 12) - ema(close, 26)
        signal_line = ema(macd_line, 9)
        signals.append(1 IF macd_line[-1] > signal_line[-1] ELSE -1)
    
    IF len(signals) == 0:
        RETURN None
    
    # Aggregate: net direction (-1 to +1)
    RETURN sum(signals) / len(signals)

# ═══════════════════════════════════════════════════
# AIM-10 FEATURES (Calendar Effects)
# ═══════════════════════════════════════════════════

FUNCTION is_within_opex_window(date):
    # Returns True if date is within ±2 trading days of monthly options expiration
    # Monthly OPEX = 3rd Friday of each month
    
    third_friday = get_third_friday(date.year, date.month)
    distance = trading_days_between(date, third_friday)
    
    RETURN abs(distance) <= 2

# ═══════════════════════════════════════════════════
# AIM-12 FEATURES (Dynamic Costs)
# ═══════════════════════════════════════════════════

FUNCTION get_live_spread(asset):
    # Current bid-ask spread for the asset
    # Data: live market data feed (see LocalFileRequirements.md item 78)
    # Returns spread in price units (e.g., 0.25 for 1-tick ES spread)
    
    bid = get_best_bid(asset)
    ask = get_best_ask(asset)
    
    IF bid is None OR ask is None OR bid <= 0:
        RETURN None
    
    RETURN ask - bid

# ═══════════════════════════════════════════════════
# AIM-15: OPENING VOLUME
# ═══════════════════════════════════════════════════

FUNCTION volume_first_N_min(asset, minutes):
    # Total volume during the first N minutes of the current session's OR formation
    # Data: live intraday volume bars from market data feed
    # minutes: typically matches the OR formation period (from strategy parameters)
    
    session_open = get_session_open_time(asset)
    cutoff = session_open + timedelta(minutes=minutes)
    bars = get_intraday_bars(asset, start=session_open, end=cutoff)
    
    IF bars is None OR len(bars) == 0:
        RETURN None
    
    RETURN SUM(bar.volume for bar in bars)

FUNCTION avg_volume_first_N_min(asset, minutes, lookback=20):
    # Average volume during the first N minutes across the last `lookback` sessions
    # Used as the denominator for opening volume ratio (AIM-15)
    
    historical = []
    FOR EACH of the last `lookback` trading sessions:
        vol = get_historical_volume_first_N_min(asset, minutes, session_date)
        IF vol is not None:
            historical.append(vol)
    
    IF len(historical) < 5:
        RETURN None
    
    RETURN mean(historical)

# ═══════════════════════════════════════════════════
# GENERAL UTILITY
# ═══════════════════════════════════════════════════

FUNCTION z_score(value, trailing_series):
    # Standard z-score: (value - mean) / std
    # Returns None if insufficient data
    
    IF trailing_series is None OR len(trailing_series) < 10:
        RETURN None
    
    mu = mean(trailing_series)
    sigma = std(trailing_series)
    
    IF sigma == 0:
        RETURN 0.0
    
    RETURN (value - mu) / sigma

FUNCTION ema(series, span):
    # Exponential moving average with given span
    alpha = 2 / (span + 1)
    result = [series[0]]
    FOR i IN range(1, len(series)):
        result.append(alpha * series[i] + (1 - alpha) * result[-1])
    RETURN result
```

## BLOCK 1 APPENDIX B — DATA ACCESS UTILITY FUNCTIONS

```
FUNCTION session_match(asset, session_id):
    # Returns True if this asset trades in the given session
    session_key = {1: "NY", 2: "LON", 3: "APAC"}[session_id]
    RETURN P3-D00[asset].session_hours.get(session_key) is not None

FUNCTION close_price(asset, date):
    # Yesterday's closing price from price_feed adapter
    RETURN price_feed_adapter.get_close(asset, date)

FUNCTION get_current_session_volume(asset):
    # Current session's cumulative volume from price_feed
    RETURN price_feed_adapter.get_session_volume(asset, today())

FUNCTION avg_session_volume_20d(asset):
    # 20-day average session volume from price_feed history
    volumes = [price_feed_adapter.get_session_volume(asset, d) for d in last_20_sessions]
    RETURN mean(volumes) IF len(volumes) > 0 ELSE None

FUNCTION get_required_features(asset):
    # Returns list of feature keys based on which AIMs are ACTIVE/BOOTSTRAPPED for this asset
    required = []
    FOR EACH aim_id IN [1..15]:
        IF P3-D01[aim_id].status IN ["ACTIVE", "BOOTSTRAPPED", "ELIGIBLE"]:
            required.extend(AIM_FEATURE_MAP[aim_id])
    RETURN required

FUNCTION feature_value(asset, feature_name):
    # Current value of a computed feature from the features dict
    RETURN features[asset].get(feature_name)

FUNCTION get_last_known_value(asset, feature_name):
    # Fallback: last successfully computed value from P3-D17 session history
    FOR entry IN reversed(P3-D17.session_log):
        IF entry.features.get(asset, {}).get(feature_name) is not None:
            RETURN entry.features[asset][feature_name]
    RETURN None

FUNCTION extract_classifier_features(asset, features):
    # Maps the features dict to the feature vector expected by P2-D07 classifier
    # Uses P2-D07[asset].feature_list to determine which features in which order
    classifier = P2-D07[asset]
    feature_vector = []
    FOR fname IN classifier.feature_list:
        feature_vector.append(features[asset].get(fname, None))
    RETURN feature_vector

FUNCTION get_return_bounds(ewma_states):
    # Distributional robust Kelly: compute return bounds from EWMA statistics
    # Paper 218: uncertainty set based on mean ± k*sigma
    # Returns (lower_bound, upper_bound) for expected return
    mu = ewma_states.avg_win * ewma_states.win_rate - ewma_states.avg_loss * (1 - ewma_states.win_rate)
    sigma = sqrt(ewma_states.avg_win**2 * ewma_states.win_rate + ewma_states.avg_loss**2 * (1 - ewma_states.win_rate) - mu**2)
    RETURN (mu - 1.5 * sigma, mu + 1.5 * sigma)

FUNCTION compute_robust_kelly(return_bounds, uncertainty_set):
    # Distributional robust Kelly: minimize worst-case growth over uncertainty set
    # Paper 218: uses min-max approach — Kelly fraction that maximises minimum growth
    lower, upper = return_bounds
    IF lower <= 0:
        RETURN 0.3 * standard_kelly  # conservative fallback
    robust_f = lower / (upper * lower)  # simplified robust solution
    RETURN max(0, min(robust_f, 0.5))  # cap at half-Kelly
FUNCTION get_or_window_minutes(model_id):
    # Returns the OR formation window in minutes for the given model
    # Source: D-09 model_indexed_dataset, which stores strategy_params per model
    model_def = D-09[model_id]
    RETURN model_def.strategy_params.get("OR_window_minutes", 15)  # default 15 min
```

**Session-open variable definitions:**

The following variables used in Block 1 feature computation are read from external data feeds at session open and are available to all feature functions:

- `vix_close_yesterday`: VIX closing price at 16:00 ET on prior trading day (from P3-D00.data_sources.vix_feed)
- `vxv_close_yesterday`: VXV (3-month VIX) closing price (from P3-D00.data_sources.vix_feed)
- `trailing_252d`: Array of last 252 VIX daily closes (for z-score computation)
- `trailing_60d_open_spreads`: Array of last 60 session-open bid-ask spreads (for AIM-12)
- `vix_change_today`: abs(VIX_now - VIX_yesterday) (from vix_feed intraday if available, else 0)
- `cl_spot`, `cl_front_futures`: CL spot and front-month futures prices (CL-specific, from cross_asset_prices)

---

# BLOCK 2 — REGIME PROBABILITY COMPUTATION

## 2.1 Pseudocode

```
P3-PG-22: "regime_probability_A"

INPUT: features (from Block 1), regime_models (P2-D07)

FOR EACH asset u IN active_assets:
    # Run trained classifier from Program 2
    classifier = regime_models[u]
    feature_vector = extract_classifier_features(u, features)
    
    # Check complexity tier (C4 = BINARY_ONLY, no trained classifier)
    IF classifier.model_type == "BINARY_ONLY":
        # C4 asset: use Pettersson binary rule directly from live data
        # sigma_t from P2-D01 RV computation; phi from P2 Block 1 EWMA threshold
        sigma_today = compute_realised_vol(features[u])
        phi = classifier.pettersson_threshold  # stored in P2-D07
        IF sigma_today > phi:
            regime_probs[u] = {HIGH_VOL: 1.0, LOW_VOL: 0.0}
        ELSE:
            regime_probs[u] = {HIGH_VOL: 0.0, LOW_VOL: 1.0}
    ELSE:
        # C1/C2/C3: use trained classifier
        # IMPORTANT: use P2-D07's stored feature_list to ensure feature alignment
        feature_list = classifier.feature_list  # from P2-D07
        feature_vector = extract_classifier_features(u, features)
        regime_probs[u] = classifier.predict_proba(feature_vector)
        # regime_probs[u] = {LOW_VOL: p_low, HIGH_VOL: p_high}
    
    # Uncertainty flag
    max_prob = max(regime_probs[u].values())
    regime_uncertain[u] = (max_prob < 0.6)
    
    IF regime_uncertain[u]:
        LOG "Regime uncertainty for {u}: max_prob = {max_prob} — robust Kelly will be used"

RETURN regime_probs, regime_uncertain
```

---

# BLOCK 3 — AIM AGGREGATION (MoE/DMA)

## 3.1 Pseudocode

```
P3-PG-23: "aim_aggregation_A"

INPUT: features (from Block 1), aim_states (P3-D01), aim_weights (P3-D02)

FOR EACH asset u IN active_assets:
    aim_outputs = {}
    
    # Collect outputs from all ACTIVE AIMs
    FOR EACH aim a IN [AIM-01..AIM-15]:
        IF aim_states[a].status != ACTIVE:
            CONTINUE
        IF NOT aim_weights[a].inclusion_flag:
            CONTINUE  # DMA gating excluded this AIM
        
        # Compute AIM modifier using its specific logic (see AIMRegistry.md Part J)
        aim_result = compute_aim_modifier(a, features, u)
        modifier = aim_result.modifier
        confidence = aim_result.confidence
        reason = aim_result.reason_tag
        
        aim_outputs[a] = {
            modifier: clamp(modifier, FLOOR=0.5, CEILING=1.5),
            confidence: confidence,
            reason_tag: reason,
            dma_weight: aim_weights[a].inclusion_probability
        }
    
    # Weighted aggregation using DMA probabilities
    IF len(aim_outputs) > 0:
        total_weight = SUM(aim_outputs[a].dma_weight for a in aim_outputs)
        combined_modifier[u] = SUM(
            aim_outputs[a].modifier * (aim_outputs[a].dma_weight / total_weight)
            for a in aim_outputs
        )
        combined_modifier[u] = clamp(combined_modifier[u], FLOOR=0.5, CEILING=1.5)
    ELSE:
        combined_modifier[u] = 1.0  # No active AIMs → neutral
    
    aim_breakdown[u] = aim_outputs

RETURN combined_modifier, aim_breakdown
```

---

# BLOCK 4 — KELLY SIZING UNDER CONSTRAINTS

## 4.1 Purpose

Computes optimal contract sizing per asset per account for the **current user**. This block runs once per user per session evaluation (see orchestrator). Market intelligence inputs (regime, AIM modifier, Kelly fractions) are shared; capital and account constraints are user-specific.

## 4.2 Pseudocode

```
P3-PG-24: "kelly_sizing_A"

INPUT: regime_probs, regime_uncertain (Block 2 — shared)
INPUT: combined_modifier (Block 3 — shared)
INPUT: kelly_params (P3-D12 — shared), ewma_states (P3-D05 — shared)
INPUT: tsm_configs (P3-D08), sizing_overrides
INPUT: user_silo (P3-D16[current_user]) — THIS user's capital silo

# ──── SILO-LEVEL DRAWDOWN CHECK (Architecture Section 19.6) ────
silo_drawdown_pct = 1 - (user_silo.total_capital / user_silo.starting_capital)
IF silo_drawdown_pct > P3-D17.system_params.max_silo_drawdown_pct:  # default 0.30
    FOR EACH asset u IN active_assets:
        FOR EACH ac_id IN user_silo.accounts:
            account_recommendation[u][ac_id] = "BLOCKED"
            account_skip_reason[u][ac_id] = "SILO_DRAWDOWN_LIMIT"
    NOTIFY(user_id=user_silo.user_id,
           message="CRITICAL: Silo drawdown at {silo_drawdown_pct:.1%}. All trading halted.",
           priority="CRITICAL")
    RETURN  # skip entire Kelly computation for this user

FOR EACH asset u IN active_assets:
    
    # Step 1: Blended Kelly across regimes (Paper 219)
    blended_kelly = 0
    FOR EACH regime r IN [LOW_VOL, HIGH_VOL]:
        regime_kelly = kelly_params[u][r].kelly_full
        regime_weight = regime_probs[u][r]
        blended_kelly += regime_weight * regime_kelly
    
    # Step 2: Parameter uncertainty shrinkage (Paper 217)
    shrinkage = kelly_params[u].shrinkage_factor  # from Offline Block 8
    adjusted_kelly = blended_kelly * shrinkage
    
    # Step 3: Robust Kelly fallback during high uncertainty (Paper 218)
    IF regime_uncertain[u]:
        robust_kelly = compute_robust_kelly(
            return_bounds=get_return_bounds(ewma_states[u]),
            uncertainty_set="moment_constraints"
        )
        final_kelly = min(adjusted_kelly, robust_kelly)
    ELSE:
        final_kelly = adjusted_kelly
    
    # Step 4: Apply AIM modifier
    kelly_with_aim = final_kelly * combined_modifier[u]
    
    # Step 5: Apply user-level Kelly ceiling
    kelly_with_aim = min(kelly_with_aim, user_silo.risk_allocation.user_kelly_ceiling)
    
    # Step 6: Per-account sizing — account classification drives risk optimisation mode
    # strategy_sl: SL distance in points from P2-D06[u].threshold (the locked strategy's threshold)
    # point_value: dollar value per point from instrument config in P3-D00 (e.g., $50/pt for ES)
    # account_eligible_for_asset: checks tsm.instrument_permissions includes asset u
    strategy_sl = locked_strategies[u].threshold
    point_value = P3-D00[u].point_value
    FOR EACH account_id ac_id IN user_silo.accounts:
        tsm = tsm_configs.get(ac_id)
        IF tsm is None OR NOT tsm.instrument_permissions.contains(u):
            final_contracts[u][ac_id] = 0
            account_recommendation[u][ac_id] = "SKIP"
            account_skip_reason[u][ac_id] = "Not eligible for this asset"
            CONTINUE
        
        risk_goal = tsm.classification.risk_goal
        
        # Step 6a: Account-type-specific Kelly adjustment
        IF risk_goal == "PASS_EVAL":
            # Conservative: protect MDD/MLL headroom, prioritise pass probability
            # Reduce Kelly by pass-probability-preserving factor
            pass_prob = tsm.pass_probability  # from Offline Block 7 simulation
            IF pass_prob is not None AND pass_prob < 0.5:
                # Critically low pass probability — further reduce sizing
                account_kelly = kelly_with_aim * 0.5
            ELIF pass_prob is not None AND pass_prob < 0.7:
                account_kelly = kelly_with_aim * 0.7
            ELSE:
                account_kelly = kelly_with_aim * 0.85  # always slightly conservative for eval
        
        ELIF risk_goal == "PRESERVE_CAPITAL":
            account_kelly = kelly_with_aim * 0.5  # hard cap at half-Kelly
        
        ELIF risk_goal == "GROW_CAPITAL":
            account_kelly = kelly_with_aim  # full computed Kelly (standard)
        
        # Step 6b: TSM hard constraints (applies regardless of risk_goal)
        category = tsm.classification.category
        
        IF category IN ["PROP_EVAL", "PROP_FUNDED", "PROP_SCALING"]:
            remaining_mdd = tsm.max_drawdown_limit - tsm.current_drawdown
            # daily_budget_divisor: number of days to spread remaining MDD over.
            # For timed evaluations: actual remaining days.
            # For no-deadline evaluations (days=0): use configurable divisor (default 20).
            # CALIBRATION NOTE: divisor of 20 may be too conservative for large-SL
            # instruments (e.g., ES with 4-pt SL = $200/contract). If this produces
            # 0 contracts at typical SL sizes, decrease divisor (smaller divisor = larger daily budget) or reduce SL.
            # Stored in P3-D17.system_params.tsm_budget_divisor_default (default: 20).
            budget_divisor = P3-D17.system_params.get("tsm_budget_divisor_default", 20)
            daily_budget = remaining_mdd / max(tsm.evaluation_end_date - today(), 1) \
                           IF tsm.evaluation_end_date ELSE remaining_mdd / budget_divisor
            
            max_contracts_by_mdd = floor(daily_budget / (strategy_sl * point_value))
            max_contracts_by_mll = floor(
                (tsm.max_daily_loss - tsm.daily_loss_used) / (strategy_sl * point_value)
            ) IF tsm.max_daily_loss ELSE 999
            tsm_cap = min(max_contracts_by_mdd, max_contracts_by_mll, tsm.max_contracts or 999)
            
            # Scaling plan: adjust max_contracts based on current balance
            IF tsm.scaling_plan:
                FOR tier IN reversed(tsm.scaling_plan):
                    IF tsm.current_balance >= tier.balance_threshold:
                        tsm_cap = min(tsm_cap, tier.max_contracts)
                        BREAK
        
        ELIF category IN ["BROKER_RETAIL", "BROKER_INSTITUTIONAL"]:
            margin_per_contract = tsm.margin_per_contract or get_default_margin(u)
            buffer = tsm.margin_buffer_pct or 1.5
            tsm_cap = floor(tsm.current_balance / (margin_per_contract * buffer))
            IF tsm.max_contracts:
                tsm_cap = min(tsm_cap, tsm.max_contracts)
        
        # Step 6c: Compute final contracts for this account
        # account_kelly is a dimensionless fraction (Kelly criterion)
        # avg_loss_per_contract from P3-D05 gives the risk per contract in dollars
        # contracts = kelly × capital / risk_per_contract
        account_capital = tsm.current_balance
        risk_per_contract = ewma_states[u][argmax(regime_probs[u])].avg_loss  # per-contract $ risk
        IF risk_per_contract <= 0:
            risk_per_contract = strategy_sl * point_value  # fallback to SL-based risk
        kelly_contracts = account_kelly * account_capital / risk_per_contract
        final_contracts[u][ac_id] = min(floor(kelly_contracts), tsm_cap)
        final_contracts[u][ac_id] = max(final_contracts[u][ac_id], 0)
        
        # Step 6d: Per-account trade recommendation and reasoning
        # remaining_mdd is only set for PROP accounts; for BROKER accounts use None
        IF category NOT IN ["PROP_EVAL", "PROP_FUNDED", "PROP_SCALING"]:
            remaining_mdd = None
        IF final_contracts[u][ac_id] == 0:
            IF tsm.max_daily_loss AND tsm.daily_loss_used >= tsm.max_daily_loss:
                account_recommendation[u][ac_id] = "BLOCKED"
                account_skip_reason[u][ac_id] = "Daily loss limit reached"
            ELIF remaining_mdd is not None AND remaining_mdd < strategy_sl * point_value:
                account_recommendation[u][ac_id] = "BLOCKED"
                account_skip_reason[u][ac_id] = "Insufficient MDD headroom"
            ELSE:
                account_recommendation[u][ac_id] = "SKIP"
                account_skip_reason[u][ac_id] = "Position size rounded to 0"
        ELSE:
            account_recommendation[u][ac_id] = "TRADE"
            account_skip_reason[u][ac_id] = None
    
    # Step 7: User-level portfolio risk cap
    total_risk_this_asset = SUM(
        final_contracts[u][ac_id] * strategy_sl * point_value
        for ac_id in user_silo.accounts
    )
    max_risk = user_silo.risk_allocation.max_portfolio_risk_pct * user_silo.total_capital
    IF total_risk_this_asset > max_risk AND total_risk_this_asset > 0:
        scale_factor = max_risk / total_risk_this_asset
        FOR EACH ac_id IN user_silo.accounts:
            final_contracts[u][ac_id] = floor(final_contracts[u][ac_id] * scale_factor)
    
    # Step 7: User-level portfolio risk cap (unchanged — applied across all accounts)
    # [see above — Steps 7 and 8 unchanged]

    # Step 8: Apply Level 2 sizing override
    IF sizing_overrides.get(u):
        FOR EACH ac_id IN user_silo.accounts:
            final_contracts[u][ac_id] = floor(final_contracts[u][ac_id] * sizing_overrides[u])
            IF final_contracts[u][ac_id] == 0 AND account_recommendation[u][ac_id] == "TRADE":
                account_recommendation[u][ac_id] = "REDUCED_TO_ZERO"
                account_skip_reason[u][ac_id] = "Level 2 sizing override"

RETURN final_contracts, account_recommendation, account_skip_reason
```

---

# BLOCK 5 — UNIVERSE-LEVEL TRADE SELECTION

## 5.1 Purpose

Selects which assets the **current user** should trade this session, considering expected edge, contract sizing from Block 4 (user-specific), cross-asset correlation (to avoid concentrated risk), and the user's maximum simultaneous position limit. Expected edge is computed from shared intelligence; selection decisions are user-specific because different users have different contract sizes after Block 4.

## 5.2 Pseudocode

```
P3-PG-25: "trade_selection_A"

INPUT: final_contracts, account_recommendation, account_skip_reason (Block 4 — THIS user's)
INPUT: ewma_states (P3-D05 — shared), regime_probs (Block 2 — shared)
INPUT: correlation_matrix from P3-D07 (AIM-08 — shared)
INPUT: user_silo (P3-D16[current_user]) — THIS user's capital silo

# Compute expected edge per asset (shared intelligence — same for all users)
# expected_edge is in per-contract dollar terms (sizing-independent, cross-asset comparable)
FOR EACH asset u IN active_assets:
    regime = argmax(regime_probs[u])
    expected_edge[u] = ewma_states[u][regime].win_rate * ewma_states[u][regime].avg_win \
                     - (1 - ewma_states[u][regime].win_rate) * ewma_states[u][regime].avg_loss
    # Units: dollars per contract (e.g., $180/contract for ES in LOW_VOL)
    
    # Risk-adjusted score — uses THIS user's contract sizes
    max_contracts_this_user = max(
        final_contracts[u].get(ac_id, 0) for ac_id in user_silo.accounts
    )
    score[u] = expected_edge[u] * max_contracts_this_user

# Multi-asset covariance adjustment — scoped to THIS user's portfolio
corr_threshold = user_silo.risk_allocation.correlation_threshold  # default 0.7

IF len(active_assets) > 1:
    corr_matrix = get_correlation_matrix(active_assets, P3-D07)
    
    FOR EACH pair (u1, u2) IN active_assets:
        IF corr_matrix[u1][u2] > corr_threshold:
            IF score[u1] > score[u2]:
                FOR EACH ac_id IN user_silo.accounts:
                    final_contracts[u2][ac_id] = floor(final_contracts[u2].get(ac_id, 0) * 0.5)
            ELSE:
                FOR EACH ac_id IN user_silo.accounts:
                    final_contracts[u1][ac_id] = floor(final_contracts[u1].get(ac_id, 0) * 0.5)

# Max simultaneous positions — user-specific constraint
ranked_assets = sorted(active_assets, key=lambda u: score[u], reverse=True)

max_pos = user_silo.risk_allocation.max_simultaneous_positions
IF max_pos is not None AND len(ranked_assets) > max_pos:
    FOR EACH u IN ranked_assets[max_pos:]:
        FOR EACH ac_id IN user_silo.accounts:
            final_contracts[u][ac_id] = 0

# Reconcile account_recommendation after Block 5 modifications
# Block 5 may have reduced contracts to 0 via correlation or position limit constraints
FOR EACH asset u IN active_assets:
    FOR EACH ac_id IN user_silo.accounts:
        IF final_contracts[u].get(ac_id, 0) == 0 AND account_recommendation[u].get(ac_id) == "TRADE":
            account_recommendation[u][ac_id] = "SKIP"
            account_skip_reason[u][ac_id] = "Removed by portfolio-level constraint (correlation or position limit)"

# Select trades — this user's selection
selected_trades = []
FOR EACH asset u IN ranked_assets:
    max_contracts_this_user = max(
        final_contracts[u].get(ac_id, 0) for ac_id in user_silo.accounts
    )
    IF max_contracts_this_user > 0 AND expected_edge[u] > 0:
        selected_trades.append(u)

RETURN selected_trades, score, expected_edge, final_contracts, account_recommendation, account_skip_reason
```

---

# BLOCK 5B — SIGNAL QUALITY GATE

## 5B.1 Purpose

Filters selected trades by a minimum quality threshold before signal generation. Signals below the quality bar are logged as `AVAILABLE_NOT_RECOMMENDED` — they have positive expected edge but do not meet the quality standard for active trading. This naturally reduces network concentration (fewer marginal signals pass) and ensures traders only receive signals the system has high conviction in.

The quality gate does NOT modify or degrade passing signals — it is a filter, not a modifier.

## 5B.2 Pseudocode

```
P3-PG-25B: "signal_quality_gate_A"

INPUT: selected_trades, expected_edge, combined_modifier, score (from Block 5)
INPUT: regime_probs (Block 2 — shared), ewma_states (P3-D05 — shared)
INPUT: minimum_quality_threshold (from P3-D17.system_params — OPEN PARAMETER)

quality_results = {}

FOR EACH asset u IN selected_trades:
    regime = argmax(regime_probs[u])
    
    # Quality score: combines edge magnitude, AIM conviction, and data sufficiency
    trade_count = P3-D03.filter(asset=u).count()
    data_maturity = min(1.0, trade_count / 50)  # ramps from 0→1 over first 50 trades
    
    # UNIT NOTE: expected_edge is in $/contract (e.g., $180 for ES in LOW_VOL).
    # quality_score inherits these units. The hard_floor and quality_ceiling defaults
    # below (0.003, 0.010) are PLACEHOLDERS — they MUST be calibrated from P1/P2
    # historical quality_scores during first deployment (see Section 5B.3).
    # After calibration, thresholds will be in the same $/contract range as expected_edge.
    quality_score = expected_edge[u] * combined_modifier[u] * data_maturity
    
    # SPEC-A7: Confidence-graduated sizing (replaces binary gate)
    # Signals below hard_floor are excluded; between hard_floor and quality_ceiling
    # receive graduated sizing via quality_multiplier
    hard_floor = P3-D17.system_params.quality_hard_floor       # CALIBRATE from P1/P2 data
    quality_ceiling = P3-D17.system_params.quality_ceiling      # CALIBRATE from P1/P2 data
    
    IF quality_score < hard_floor:
        quality_multiplier = 0.0
        passes_gate = False
    ELSE:
        quality_multiplier = min(1.0, quality_score / quality_ceiling)
        passes_gate = True
    
    quality_results[u] = {
        quality_score:  quality_score,
        quality_multiplier: quality_multiplier,
        passes_gate:    passes_gate,
        edge:           expected_edge[u],
        modifier:       combined_modifier[u],
        data_maturity:  data_maturity,
        trade_count:    trade_count
    }
    
    IF NOT quality_results[u].passes_gate:
        LOG "Asset {u}: quality_score {quality_score} below threshold {minimum_quality_threshold} — AVAILABLE_NOT_RECOMMENDED"

# Split: passing signals → Block 6, below-threshold → logged only
recommended_trades = [u for u in selected_trades if quality_results[u].passes_gate]
available_not_recommended = [u for u in selected_trades if not quality_results[u].passes_gate]

# Log below-threshold signals for capacity reporting (P3-D17)
P3-D17.session_log.append({
    session: session_id,
    user_id: user_silo.user_id,
    timestamp: now(),
    total_selected: len(selected_trades),
    total_recommended: len(recommended_trades),
    total_below_threshold: len(available_not_recommended),
    quality_scores: quality_results
})

RETURN recommended_trades, available_not_recommended, quality_results
```

## 5B.3 Minimum Quality Threshold

```
minimum_quality_threshold:
    Type:       OPEN PARAMETER
    Default:    0.005  (calibrate during initial P1/P2 validation runs)
    Range:      [0.001, 0.05]
    Stored in:  P3-D17.system_params
    Changed by: ADMIN only (via System Overview GUI)
    
    Relationship to internal parameters:
        quality_hard_floor — signals below this are blocked entirely (default 0.003)
        quality_ceiling — signals at/above this receive full Kelly (default 0.010)
        minimum_quality_threshold — user-facing alias for quality_hard_floor
        When ADMIN changes minimum_quality_threshold, quality_hard_floor is updated.
    
    Calibration method:
        During P1/P2 validation, compute quality_score for all historical trades.
        Set threshold at the 20th percentile of quality_scores among profitable trades.
        This ensures ~80% of historically profitable signals pass the gate.
    
    The threshold is FIXED after calibration — it does NOT adapt dynamically
    to current conditions (prevents overfitting and look-ahead bias).
```

---

# BLOCK 6 — SIGNAL OUTPUT

## 6.1 Purpose

Generates fully specified trading signals for the **current user** from the quality-gated recommended trades. Signals include strategy execution details (direction, TP, SL), the user's specific per-account contract sizes, quality score, and diagnostic context for GUI display. Signals are tagged with `user_id` so Captain (Command) routes them to the correct GUI session and notifications. Below-threshold signals are included in the payload as `available_not_recommended` for transparency.

## 6.2 Pseudocode

```
P3-PG-26: "signal_output_A"

INPUT: recommended_trades, available_not_recommended, quality_results (Block 5B output)
INPUT: final_contracts, account_recommendation, account_skip_reason (Block 5 output)
INPUT: features (Block 1 — shared), ewma_states (P3-D05 — shared)
INPUT: aim_breakdown, combined_modifier, regime_probs, expected_edge (shared)
INPUT: locked_strategies (P2-D06), tsm_configs (P3-D08)
INPUT: user_silo (P3-D16[current_user]) — THIS user's capital silo
minimum_quality_threshold = P3-D17.system_params.quality_hard_floor

FOR EACH asset u IN recommended_trades:
    strategy = locked_strategies[u]  # P2-D06 locked strategy for this asset
    
    regime = argmax(regime_probs[u])
    
    signal = {
        # User identification
        user_id:            user_silo.user_id,
        
        # Core signal
        asset:              u,
        session:            session_id,
        timestamp:          now(),
        direction:          strategy.determine_direction(features[u]),
        tp_level:           strategy.compute_tp(features[u]),
        sl_level:           strategy.compute_sl(features[u]),
        sl_method:          strategy.sl_method,
        entry_conditions:   strategy.entry_conditions(features[u]),
        
        # Per-account trade breakdown — the core per-account recommendation
        per_account: {ac_id: {
            contracts:        final_contracts[u].get(ac_id, 0),
            recommendation:   account_recommendation[u].get(ac_id, "SKIP"),
            skip_reason:      account_skip_reason[u].get(ac_id, None),
            account_name:     get_account(ac_id).name,
            category:         tsm_configs[ac_id].classification.category IF tsm_configs.get(ac_id) ELSE None,
            risk_goal:        tsm_configs[ac_id].classification.risk_goal IF tsm_configs.get(ac_id) ELSE None,
            remaining_mdd:    tsm_configs[ac_id].max_drawdown_limit - tsm_configs[ac_id].current_drawdown IF tsm_configs.get(ac_id) AND tsm_configs[ac_id].max_drawdown_limit ELSE None,
            remaining_mll:    tsm_configs[ac_id].max_daily_loss - tsm_configs[ac_id].daily_loss_used IF tsm_configs.get(ac_id) AND tsm_configs[ac_id].max_daily_loss ELSE None,
            pass_probability: tsm_configs[ac_id].pass_probability IF tsm_configs.get(ac_id) ELSE None,
            risk_budget_pct:  (tsm_configs[ac_id].daily_loss_used / tsm_configs[ac_id].max_daily_loss) * 100 IF tsm_configs.get(ac_id) AND tsm_configs[ac_id].max_daily_loss ELSE None,
            api_validated:    get_account(ac_id).api_validated
        } for ac_id in user_silo.accounts},
        
        # Context for GUI display (shared intelligence)
        aim_breakdown:      aim_breakdown[u],
        combined_modifier:  combined_modifier[u],
        regime_state:       regime,
        regime_probs:       regime_probs[u],
        expected_edge:      expected_edge[u],
        win_rate:           ewma_states[u][regime].win_rate,
        payoff_ratio:       ewma_states[u][regime].avg_win / ewma_states[u][regime].avg_loss,
        
        # User capital context
        user_total_capital: user_silo.total_capital,
        user_daily_pnl:     daily_pnl_sum(user_silo.user_id, today()),
        
        # Signal quality
        quality_score:      quality_results[u].quality_score,
        data_maturity:      quality_results[u].data_maturity
    }

# Attach below-threshold signals for transparency (shown differently in GUI)
# This list is built ONCE per session for this user, attached to the signal batch
session_below_threshold = [{
    asset: u,
    quality_score: quality_results[u].quality_score,
    expected_edge: expected_edge[u],
    reason: "Below minimum quality threshold ({minimum_quality_threshold})"
} for u in available_not_recommended]
    
    # Confidence classification
    # high_threshold = quality_ceiling from P3-D17.system_params (CALIBRATE from P1/P2 data)
    # low_threshold  = quality_hard_floor from P3-D17.system_params (CALIBRATE from P1/P2 data)
    high_threshold = P3-D17.system_params.quality_ceiling
    low_threshold  = P3-D17.system_params.quality_hard_floor
    # NOTE: confidence_tier is an approximate GUI classification for display purposes.
    # The formal quality gate is Block 5B's quality_score (= edge * modifier * maturity).
    # Here we use expected_edge as a proxy for quick classification.
    IF expected_edge[u] > high_threshold AND combined_modifier[u] > 1.0:
        signal.confidence_tier = "HIGH"
    ELIF expected_edge[u] > low_threshold:
        signal.confidence_tier = "MEDIUM"
    ELSE:
        signal.confidence_tier = "LOW"
    
    # Push to signal queue — tagged with user_id for Command routing
    signal_queue.push(signal)
    
    LOG signal to P3-D03.signals_generated

NOTIFY_COMMAND("New signals available for user {user_silo.user_id}, session {session_id}")
```

---

# BLOCK 7 — INTRADAY POSITION MONITORING

## 7.1 Purpose

Monitors all open positions continuously, tracking P&L, TP/SL proximity, and market conditions. Positions are inherently per-user (each position belongs to a user's account). All notifications are routed to the user who owns the position. Trade outcomes update both the shared intelligence layer and the user's capital silo.

## 7.2 Pseudocode

```
P3-PG-27: "intraday_monitor_A"

# Runs continuously while any position is open across any user

WHILE any_position_open():
    SLEEP(10 seconds)  # Poll frequency
    
    FOR EACH open_position pos:
        current_price = get_live_price(pos.asset)
        point_value = P3-D00[pos.asset].point_value
        
        # P&L tracking
        pos.current_pnl = (current_price - pos.entry_price) * pos.direction * pos.contracts * point_value
        pos.pnl_pct = pos.current_pnl / pos.risk_amount
        
        # TP/SL proximity
        tp_distance = abs(pos.tp_level - current_price) / abs(pos.tp_level - pos.entry_price)
        sl_distance = abs(pos.sl_level - current_price) / abs(pos.sl_level - pos.entry_price)
        
        # Alert: approaching TP — routed to position owner
        IF tp_distance < 0.10:
            NOTIFY(user_id=pos.user_id,
                   message="TP approaching for {pos.asset}: {current_price} vs TP {pos.tp_level}", 
                   priority="HIGH")
        
        # Alert: approaching SL — routed to position owner
        IF sl_distance < 0.10:
            NOTIFY(user_id=pos.user_id,
                   message="SL approaching for {pos.asset}: {current_price} vs SL {pos.sl_level}", 
                   priority="CRITICAL")
        
        # Alert: VIX spike
        current_vix = get_live_vix()
        trailing_60d_vix = get_trailing_vix(lookback=60)
        IF z_score(current_vix, trailing_60d_vix) > 2.0:
            NOTIFY(user_id=pos.user_id,
                   message="VIX spike detected while position open in {pos.asset}", 
                   priority="HIGH")
        
        # Alert: regime shift mid-trade
        IF regime_shift_detected(pos.asset):
            NOTIFY(user_id=pos.user_id,
                   message="Regime shift detected for {pos.asset} — review position", 
                   priority="CRITICAL")
        
        # Position resolved — TP/SL
        IF current_price >= pos.tp_level (long) OR current_price <= pos.tp_level (short):
            resolve_position(pos, outcome="TP_HIT", exit_price=current_price)
        
        IF current_price <= pos.sl_level (long) OR current_price >= pos.sl_level (short):
            resolve_position(pos, outcome="SL_HIT", exit_price=current_price)
        
        # TIME EXIT — forced close for accounts that prohibit overnight positions
        tsm = tsm_configs[pos.account]
        IF tsm AND NOT tsm.overnight_allowed:
            close_time = parse_trading_hours_end(tsm.trading_hours)  # e.g., 15:55 (5 min buffer)
            IF now() >= close_time - timedelta(minutes=5):
                NOTIFY(user_id=pos.user_id,
                       message="TIME EXIT: {pos.asset} position closing — {pos.account} does not allow overnight. Close by {close_time}.",
                       priority="CRITICAL")
                resolve_position(pos, outcome="TIME_EXIT", exit_price=current_price)
    
    # Update GUI with live positions — each user sees only their own positions
    FOR EACH active_user:
        user_positions = [pos for pos in open_positions if pos.user_id == active_user.user_id]
        UPDATE_GUI_POSITIONS(active_user.user_id, user_positions)

FUNCTION resolve_position(pos, outcome, exit_price):
    point_value = P3-D00[pos.asset].point_value
    gross_pnl = (exit_price - pos.entry_price) * pos.direction * pos.contracts * point_value
    
    # COMMISSION DEDUCTION — data sourcing chain: API → TSM config → user notification
    commission = resolve_commission(pos.account, pos.contracts)
    net_pnl = gross_pnl - commission
    
    # ACTUAL ENTRY PRICE — sourcing chain: API fill → manual GUI input → notification
    actual_entry = resolve_actual_entry_price(pos)
    slippage = (actual_entry - pos.signal_entry_price) * pos.direction * pos.contracts * point_value \
               IF actual_entry ELSE None
    
    # Log to trade outcome log — tagged with user_id for silo isolation
    # PnL stored as NET (after commissions) — this feeds the learning loop
    P3-D03.append({
        user_id: pos.user_id,
        asset: pos.asset,
        direction: pos.direction,
        entry_price: actual_entry or pos.entry_price,
        signal_entry_price: pos.signal_entry_price,
        exit_price: exit_price,
        contracts: pos.contracts,
        gross_pnl: gross_pnl,
        commission: commission,
        pnl: net_pnl,           # NET PnL — used by EWMA, BOCPD, DMA
        slippage: slippage,     # feeds AIM-12 learning
        outcome: outcome,       # TP_HIT, SL_HIT, MANUAL_CLOSE, TIME_EXIT
        entry_time: pos.entry_time,
        exit_time: now(),
        regime_at_entry: pos.regime_state,
        aim_modifier_at_entry: pos.combined_modifier,
        aim_breakdown_at_entry: pos.aim_breakdown,
        session: pos.session,
        account: pos.account,
        tsm_used: pos.tsm_id
    })
    
    NOTIFY(user_id=pos.user_id,
           message="Position closed: {pos.asset} {outcome} Net PnL={net_pnl} (commission={commission})", 
           priority="CRITICAL")
    
    # Update user's capital silo (siloed) — uses NET PnL
    update_capital_silo(pos.user_id, pos.account, net_pnl)
    
    # Trigger Offline updates via Redis channel captain:trade_outcomes (asynchronous)
    PUBLISH "captain:trade_outcomes" trade_outcome_event(P3-D03.latest)

FUNCTION resolve_commission(account_id, contracts):
    # Chain: API reported commission → TSM config → user notification
    
    # Source 1: API fill data (if API-connected account)
    adapter = get_api_adapter(account_id)
    IF adapter AND adapter.type != "Manual":
        api_commission = adapter.get_last_fill_commission()
        IF api_commission is not None:
            RETURN api_commission  # actual commission from broker
    
    # Source 2: TSM config file
    tsm = tsm_configs[account_id]
    IF tsm AND tsm.commission_per_contract:
        RETURN tsm.commission_per_contract * contracts * 2  # round trip (entry + exit)
    
    # Source 3: Fallback — notify user to input
    NOTIFY(user_id=get_account(account_id).user_id,
           message="Commission data missing for account {account_id}. Please input via GUI.",
           priority="HIGH", action_required=True)
    RETURN 0  # temporary — corrected when user provides data

FUNCTION resolve_actual_entry_price(pos):
    # Chain: API fill → manual GUI input → notification
    
    # Source 1: API fill data (automatic for API-connected accounts)
    adapter = get_api_adapter(pos.account)
    IF adapter AND adapter.type != "Manual":
        fill = adapter.get_fill(pos.order_id)
        IF fill AND fill.fill_price:
            RETURN fill.fill_price
    
    # Source 2: User already input via GUI (TAKEN confirmation with price)
    IF pos.actual_entry_price:
        RETURN pos.actual_entry_price
    
    # Source 3: Prompt user — for Manual accounts, entry price is REQUIRED
    NOTIFY(user_id=pos.user_id,
           message="Entry price required for {pos.asset} trade on account {pos.account}. Please input via GUI.",
           priority="HIGH", action_required=True)
    RETURN None  # updated when user provides data; learning loop uses signal price as interim
```

---

# ORCHESTRATOR — CAPTAIN (ONLINE) SESSION LOOP

```
P3-PG-20: "session_evaluator_A"

# Main loop — runs 24/7

WHILE Captain is active:
    
    # Check for session opens
    FOR EACH session ss IN [NY, LON, APAC]:
        IF session_opening_now(ss):
            LOG "Session {ss} opening — beginning evaluation"
            
            # ──── CIRCUIT BREAKER CHECK (Architecture Section 19.6) ────
            IF NOT circuit_breaker_check():
                LOG "Session {ss} HALTED by circuit breaker"
                CONTINUE  # skip this session entirely
            
            # ──── SHARED INTELLIGENCE (computed ONCE per session) ────
            # Latency budget: <5s + <2s + <2s = <9s shared (see Architecture Section 13)
            data = P3-PG-21(session_id=ss)           # Block 1: Ingestion (<5s target)
            regime = P3-PG-22(data.features, data.regime_models)  # Block 2: Regime (<2s target)
            aim = P3-PG-23(data.features, data.aim_states, data.aim_weights)  # Block 3: AIM (<2s target)
            
            # ──── PER-USER DEPLOYMENT (computed for EACH active user) ────
            # Blocks 4-6 are INDEPENDENT across users — no cross-user data dependencies.
            # V1: sequential loop (single user).
            # V2+: PARALLEL execution via ThreadPoolExecutor or asyncio.
            #   Parallelised: 9s shared + max(5s) per-user = ~14s total at 20 users.
            #   Sequential:   9s shared + 5s × 20 = 109s (exceeds 30s SLA).
            #   Block 8 (concentration) runs AFTER all user loops complete (requires aggregation).
            #
            # SCOPE NOTE: All blocks in this loop have implicit access to:
            #   - session_id (= ss from outer loop)
            #   - data.* (all shared intelligence outputs from Blocks 1-3:
            #     active_assets, features, aim_states, aim_weights, ewma_states,
            #     kelly_params, locked_strategies, regime_models, tsm_configs, sizing_overrides)
            #   - regime.* (regime_probs, regime_uncertain from Block 2)
            #   - aim.* (combined_modifier, aim_breakdown from Block 3)
            #   Block INPUT lists show only ADDITIONAL inputs specific to that block.
            #   Market data variables in Block 1 (vix_close_yesterday, trailing_252d, etc.)
            #   are read from live/historical data feeds — they ARE the data being ingested.
            active_users = get_active_users()  # v1: single user; v2: all users with ACTIVE status
            
            FOR EACH user IN active_users:  # V2: replace with parallel_map(process_user, active_users)
                user_silo = READ P3-D16[user.user_id]
                
                # Block 4: Kelly sizing with this user's capital and accounts
                sizing = P3-PG-24(
                    regime, aim, data.kelly_params, data.ewma_states,
                    data.tsm_configs, data.sizing_overrides, user_silo
                )
                
                # Block 5: Trade selection with this user's portfolio constraints
                trades = P3-PG-25(sizing, data.ewma_states, regime, user_silo)
                
                # Block 5B: Signal quality gate
                quality = P3-PG-25B(trades, aim, regime, user_silo)
                
                # Block 6: Signal output for quality-gated signals
                P3-PG-26(quality, trades, sizing, aim, regime, user_silo,
                         data.features, data.ewma_states,
                         data.locked_strategies, data.tsm_configs)
                
                LOG "Session {ss} — user {user.user_id}: {len(quality.recommended_trades)} recommended, {len(quality.available_not_recommended)} below threshold"
            
            LOG "Session {ss} evaluation complete for {len(active_users)} user(s)"
            
            # ──── POST-LOOP: NETWORK + CAPACITY (runs ONCE after all user loops) ────
            IF len(active_users) > 1:
                RUN P3-PG-28(session_id=ss, active_users=active_users)  # Block 8: Concentration
            RUN P3-PG-29(session_id=ss, active_users=active_users, active_assets=data.active_assets)  # Block 9: Capacity
    
    # Continuous: intraday monitoring (Block 7) — covers all users' positions
    IF any_position_open():
        P3-PG-27()
    
    # Heartbeat
    SLEEP(1 second)
    UPDATE system_health_status()
```

---

# BLOCK 8 — NETWORK CONCENTRATION MONITOR

## 8.1 Purpose

Runs once per session AFTER all per-user deployment loops complete. Aggregates exposure across all users to detect network-level concentration. Does NOT modify any signals — it is a monitoring and alerting layer only. Alerts are sent to ADMIN users. Concentration history feeds the capacity evaluation system to proactively recommend universe expansion.

## 8.2 Pseudocode

```
P3-PG-28: "network_concentration_monitor_A"

INPUT: session_id, active_users
INPUT: all signals generated this session (from signal_queue)
INPUT: concentration_threshold (from P3-D17.system_params — OPEN PARAMETER, default 0.8)

# Step 1: Aggregate exposure across all users
network_exposure = {}
FOR EACH signal IN signal_queue.filter(session=session_id):
    asset = signal.asset
    direction = signal.direction
    total_contracts = SUM(signal.per_account[ac].contracts for ac in signal.per_account)
    
    key = (asset, direction)
    IF key NOT IN network_exposure:
        network_exposure[key] = {users: [], total_contracts: 0, account_count: 0}
    
    network_exposure[key].users.append(signal.user_id)
    network_exposure[key].total_contracts += total_contracts
    network_exposure[key].account_count += len([ac for ac in signal.per_account 
                                                  if signal.per_account[ac].recommendation == "TRADE"])

# Step 2: Check concentration thresholds
FOR EACH (asset, direction), exposure IN network_exposure:
    user_concentration = len(exposure.users) / len(active_users)
    
    IF user_concentration >= concentration_threshold:
        # CRITICAL: high network concentration
        FOR EACH admin_user IN get_users_by_role("ADMIN"):
            NOTIFY(user_id=admin_user.user_id,
                   message="Network concentration: {asset} {direction} across {len(exposure.users)}/{len(active_users)} users, {exposure.total_contracts} total contracts, {exposure.account_count} accounts. Acknowledge or Pause.",
                   priority="CRITICAL",
                   action_required=True)
        
        # Log concentration event
        P3-D17.concentration_history.append({
            session: session_id,
            timestamp: now(),
            asset: asset,
            direction: direction,
            user_count: len(exposure.users),
            total_users: len(active_users),
            concentration_pct: user_concentration,
            total_contracts: exposure.total_contracts,
            account_count: exposure.account_count,
            admin_response: PENDING  # updated when ADMIN responds
        })

# Step 3: Proactive concentration reduction tracking
# If concentration alerts fire frequently, recommend universe expansion
recent_alerts = P3-D17.concentration_history.filter(last_30_days=True)
IF len(recent_alerts) > 10:
    # Frequent concentration — universe likely too narrow
    correlated_pairs = identify_highly_correlated_assets(P3-D07)
    
    P3-D17.capacity_recommendations.append({
        timestamp: now(),
        type: "CONCENTRATION_FREQUENCY",
        message: "Concentration alerts fired {len(recent_alerts)} times in 30 days. Universe may be too narrow.",
        detail: "Correlated pairs: {correlated_pairs}. Consider: add uncorrelated assets via Programs 1/2, test additional asset classes.",
        severity: "HIGH"
    })

SAVE P3-D17
```

## 8.3 ADMIN Response Flow

```
ON admin_concentration_response(admin_user_id, event_id, response):
    P3-D17.concentration_history[event_id].admin_response = response
    P3-D17.concentration_history[event_id].responding_admin = admin_user_id
    P3-D17.concentration_history[event_id].response_time = now()
    
    LOG to AdminDecisionLog(
        admin_user_id=admin_user_id,
        decision_type="CONCENTRATION_RESPONSE",
        decision_value=response,
        context=P3-D17.concentration_history[event_id]
    )
    
    IF response == "PAUSE":
        # ADMIN specifies which asset to pause and for which user(s)
        # Signals already delivered — pause affects NEXT session only
        # OR: retract unconfirmed signals from GUI for specified users
        handle_concentration_pause(event_id)
    
    ELIF response == "PROCEED":
        # Acknowledged — no action, signals remain as-is
        LOG "Concentration acknowledged by {admin_user_id} — proceeding"
```

---

# BLOCK 9 — CAPACITY EVALUATION (SESSION-END)

## 9.1 Purpose

Runs at the end of each session evaluation to update capacity metrics. Tracks signal generation vs. trader demand, identifies constraints, and generates actionable recommendations for the System Overview GUI. This data drives the "where are we constrained?" analysis that ADMIN uses to plan universe expansion.

## 9.2 Pseudocode

```
P3-PG-29: "capacity_evaluator_A"

INPUT: all quality_results from this session (from P3-D17.session_log)
INPUT: active_users, active_assets, P3-D00 (asset universe), session_id
minimum_quality_threshold = P3-D17.system_params.quality_hard_floor
INPUT: session_id (from orchestrator)
minimum_quality_threshold = P3-D17.system_params.quality_hard_floor

# Signal supply vs. demand
total_recommended = SUM(entry.total_recommended for entry in P3-D17.session_log.filter(session=session_id))
total_below_threshold = SUM(entry.total_below_threshold for entry in P3-D17.session_log.filter(session=session_id))
total_users_needing_signals = len(active_users)

# Utilization metrics
signal_supply_ratio = total_recommended / max(total_users_needing_signals, 1)
quality_pass_rate = total_recommended / max(total_recommended + total_below_threshold, 1)

# Asset diversity
active_asset_count = len(active_assets)
assets_producing_quality_signals = len([u for u in active_assets 
                                         if any(e.quality_scores.get(u, {}).get("passes_gate") 
                                               for e in P3-D17.session_log.filter(session=session_id))])
effective_diversity = assets_producing_quality_signals / max(active_asset_count, 1)

# Correlation-adjusted diversity (accounts for highly correlated assets)
corr_matrix = get_correlation_matrix(active_assets, P3-D07)
high_corr_pairs = [(u1, u2) for u1, u2 in pairs(active_assets) if corr_matrix[u1][u2] > 0.7]
effective_independent_assets = active_asset_count - len(high_corr_pairs)

# Update capacity state
P3-D17.capacity_state = {
    timestamp:                     now(),
    session:                       session_id,
    
    # Current utilization
    active_users:                  len(active_users),
    active_accounts:               SUM(len(P3-D16[u.user_id].accounts) for u in active_users),
    active_assets:                 active_asset_count,
    assets_producing_signals:      assets_producing_quality_signals,
    effective_independent_assets:  effective_independent_assets,
    
    # Signal supply
    signal_supply_ratio:           signal_supply_ratio,
    quality_pass_rate:             quality_pass_rate,
    total_recommended:             total_recommended,
    total_below_threshold:         total_below_threshold,
    
    # Max capacities (configurable by ADMIN_DEV)
    max_users:                     P3-D17.system_params.max_users,          # default: 20
    max_accounts_per_user:         P3-D17.system_params.max_accounts_per_user,  # default: 10
    max_assets:                    P3-D17.system_params.max_assets,          # default: 50
    max_simultaneous_sessions:     3,  # NY, LON, APAC (fixed)
    max_aims:                      15, # AIMRegistry (extensible but fixed for now)
    
    # Constraint flags
    constraints: []
}

# Identify constraints
IF signal_supply_ratio < 1.0:
    P3-D17.capacity_state.constraints.append({
        type: "SIGNAL_SHORTAGE",
        severity: "HIGH",
        message: "Not enough quality signals for all users ({signal_supply_ratio:.1f} signals per user)",
        recommendation: "Test additional assets via Programs 1/2, or lower quality threshold (current: {minimum_quality_threshold})"
    })

IF effective_independent_assets < len(active_users):
    P3-D17.capacity_state.constraints.append({
        type: "ASSET_CONCENTRATION",
        severity: "HIGH",
        message: "Only {effective_independent_assets} independent assets for {len(active_users)} users",
        recommendation: "Add uncorrelated assets. Current high-correlation pairs: {high_corr_pairs}"
    })

IF quality_pass_rate < 0.3:
    P3-D17.capacity_state.constraints.append({
        type: "LOW_QUALITY_RATE",
        severity: "MEDIUM",
        message: "Only {quality_pass_rate*100:.0f}% of signals pass quality gate",
        recommendation: "Review strategy quality via Programs 1/2 re-run, or review quality threshold calibration"
    })

IF len(active_users) > P3-D17.system_params.max_users * 0.8:
    P3-D17.capacity_state.constraints.append({
        type: "USER_CAPACITY",
        severity: "HIGH",
        message: "At {len(active_users)}/{P3-D17.system_params.max_users} user capacity",
        recommendation: "Consider infrastructure scaling or staggering session evaluation"
    })

# Strategy type constraints
strategy_models = set([(P2-D06[u].m, P2-D06[u].k) for u in active_assets])
IF len(strategy_models) == 1:
    P3-D17.capacity_state.constraints.append({
        type: "STRATEGY_HOMOGENEITY",
        severity: "MEDIUM",
        message: "All assets use the same (model, feature) pair — no strategy diversification",
        recommendation: "Develop alternative strategy types (swing, multi-day) via Programs 1/2"
    })

# Asset class constraints
asset_classes = count_by_class(active_assets)
IF len(asset_classes) == 1:
    P3-D17.capacity_state.constraints.append({
        type: "ASSET_CLASS_HOMOGENEITY",
        severity: "MEDIUM",
        message: "All assets in one class ({asset_classes[0]}) — no asset class diversification",
        recommendation: "Expand to additional asset classes (FX, commodities, bonds)"
    })

SAVE P3-D17
```

---

# BLOCK-TO-BLOCK DATA FLOW

```
┌─ SHARED INTELLIGENCE (computed once per session) ──────────────────────┐
│                                                                        │
│  Block 1 (Ingestion) ──► features{} ──► Block 2 (Regime)              │
│                      ──► aim_states ──► Block 3 (AIM)                  │
│                      ──► kelly_params, ewma_states, tsm_configs        │
│                                                                        │
│  Block 2 (Regime) ──► regime_probs, regime_uncertain                   │
│                                                                        │
│  Block 3 (AIM) ──► combined_modifier, aim_breakdown                    │
│                                                                        │
└────────────────────────────── shared outputs ──────────────────────────┘
                                    │
                     (passed to each user's deployment loop)
                                    │
┌─ PER-USER DEPLOYMENT (computed for each active user) ─────────────────┐
│                                                                        │
│  P3-D16[user] ──► user_silo (capital, accounts, risk allocation)       │
│                                                                        │
│  Block 4 (Kelly) ──► final_contracts, account_recommendation,          │
│                      account_skip_reason (per-account sizing + reco)   │
│       ▲ inputs: regime_probs, combined_modifier, kelly_params,         │
│                  ewma_states, tsm_configs (with classification),       │
│                  sizing_overrides, user_silo                           │
│       ▲ risk_goal drives account-type-specific Kelly adjustment        │
│                                                                        │
│  Block 5 (Selection) ──► selected_trades, final_contracts (modified),  │
│                          account_recommendation (reconciled)            │
│       ▲ inputs: final_contracts, account_recommendation,               │
│                  account_skip_reason, ewma_states, regime_probs,       │
│                  correlation_matrix (P3-D07), user_silo               │
│       ▲ reconciles recommendation when portfolio constraints zero out  │
│                                                                        │
│  Block 5B (Quality Gate) ──► recommended_trades, available_not_recommended │
│       ▲ inputs: selected_trades, expected_edge, combined_modifier,     │
│                  regime_probs, P3-D17.system_params                    │
│       ▲ filters by minimum_quality_threshold — logs below-threshold    │
│                                                                        │
│  Block 6 (Signal Output) ──► signal_queue (tagged with user_id)        │
│       ▲ inputs: recommended_trades, final_contracts,                   │
│                  account_recommendation, account_skip_reason,           │
│                  quality_results, features, ewma_states,               │
│                  aim_breakdown, combined_modifier, regime_probs,        │
│                  locked_strategies, tsm_configs, user_silo             │
│       ▲ per_account breakdown + quality_score in signal payload        │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘

Block 6 ──► signal_queue[user_id] ──► Captain (Command) → GUI (user's session)

Block 7 (Monitoring) ──► per-user position tracking
                     ──► P3-D03 (trade outcomes, tagged with user_id)
                     ──► Capital silo update (P3-D16[user_id])
                     ──► Captain (Offline) Block 1,2,8 (shared learning)

┌─ POST-USER-LOOP (computed once per session after all users) ───────────┐
│                                                                        │
│  Block 8 (Concentration) ──► P3-D17.concentration_history              │
│       ▲ aggregates exposure across all users, alerts ADMINs if breach  │
│       ▲ proactive: recommends universe expansion if alerts frequent    │
│                                                                        │
│  Block 9 (Capacity) ──► P3-D17.capacity_state                         │
│       ▲ signal supply ratio, quality pass rate, constraint analysis    │
│       ▲ feeds System Overview GUI (ADMIN only)                         │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

# ERROR HANDLING

| Block | Failure | Response |
|-------|---------|----------|
| Block 1 (Ingestion) | Data feed unavailable | Use last known values, flag staleness in signal, alert |
| Block 2 (Regime) | Classifier fails | Use 50/50 regime probs, flag uncertainty, use robust Kelly |
| Block 3 (AIM) | All AIMs fail | combined_modifier = 1.0, proceed with base Kelly |
| Block 4 (Kelly) | Kelly computation error | Fall back to minimum position size (1 contract) or skip |
| Block 5 (Selection) | No assets pass | Generate "NO TRADE" signal, log reason |
| Block 6 (Output) | Signal queue full | Alert, drop oldest non-critical signals first, increase queue size |
| Block 7 (Monitoring) | Price feed drops | Alert immediately, use last known price, flag to user |
| Per-User Loop | User silo (P3-D16) unavailable | Skip this user for current session, alert. Other users unaffected. |
| Per-User Loop | User has zero accounts | Skip user (no accounts to size). Log warning. |
| Block 5B (Quality Gate) | Quality score computation fails | Pass all selected_trades through unfiltered (fail-open). Log warning. Alert ADMIN. |
| Block 8 (Concentration) | Aggregation or notification fails | Signals already delivered — no impact on current session. Log error. Alert ADMIN. Retry next session. |
| Block 9 (Capacity) | Capacity computation fails | Previous capacity_state retained. Log error. Non-blocking — does not affect signal delivery. |
| Block 7 (Commission) | `resolve_commission` returns 0 (no data) | Trade resolution continues with commission=0. User notified to input. PnL temporarily gross; corrected when user provides data. |
| Block 7 (Entry price) | `resolve_actual_entry_price` returns None | Signal entry price used as interim. Slippage = None. User notified. AIM-12 skips this trade for slippage learning. |
| Block 1 (Roll check) | Roll calendar data missing for asset | Asset proceeds normally (no roll protection). Log warning. ADMIN notified to upload roll calendar. |

---

*This document specifies all Captain (Online) operations. For Captain (Offline) see `Program3_Offline.md`. For Captain (Command) see `Program3_Command.md`.*
