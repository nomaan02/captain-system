"""Phase 2a regression: COLUMN_TYPES auto-derived from canonical_schemas DDL.

Validates the typed-INSERT helper's column-type lookup produces the right
answer for every table and every migration. Single source of truth: the
DDL strings + CANONICAL_MIGRATIONS in shared/canonical_schemas.py.
"""
from shared.canonical_schemas import COLUMN_TYPES


def test_every_canonical_table_has_columns():
    """Every CANONICAL_DDLS entry must produce a non-empty column dict."""
    from shared.canonical_schemas import CANONICAL_DDLS, table_name_of
    for ddl in CANONICAL_DDLS:
        table = table_name_of(ddl).lower()
        assert table in COLUMN_TYPES, f"{table} missing from COLUMN_TYPES"
        assert len(COLUMN_TYPES[table]) > 0, f"{table} has no columns"


def test_d03_aim_modifier_at_entry_is_double():
    """The May-5 crash column. Must stay DOUBLE per Isaac's spec."""
    assert COLUMN_TYPES["p3_d03_trade_outcome_log"]["aim_modifier_at_entry"] == "DOUBLE"


def test_d03_entry_price_is_decimal_after_migration():
    """Phase B M027 migrated entry_price DOUBLE → DECIMAL(14, 6)."""
    assert COLUMN_TYPES["p3_d03_trade_outcome_log"]["entry_price"] == "DECIMAL(14, 6)"


def test_d03_pnl_is_decimal_after_migration():
    """Phase B M032 migrated pnl DOUBLE → DECIMAL(18, 4)."""
    assert COLUMN_TYPES["p3_d03_trade_outcome_log"]["pnl"] == "DECIMAL(18, 4)"


def test_d03_account_id_is_symbol():
    """SYMBOL columns receive str() not Decimal()."""
    assert COLUMN_TYPES["p3_d03_trade_outcome_log"]["account_id"] == "SYMBOL"


def test_d03_session_is_int():
    """INT columns receive int() not Decimal()."""
    assert COLUMN_TYPES["p3_d03_trade_outcome_log"]["session"] == "INT"


def test_d08_starting_balance_is_decimal():
    """Phase A M010 migrated starting_balance DOUBLE → DECIMAL(18, 2)."""
    assert COLUMN_TYPES["p3_d08_tsm_state"]["starting_balance"] == "DECIMAL(18, 2)"


def test_d08_max_contracts_is_int():
    assert COLUMN_TYPES["p3_d08_tsm_state"]["max_contracts"] == "INT"


def test_d08_pass_probability_is_double():
    """Bookkeeping double — never migrated."""
    assert COLUMN_TYPES["p3_d08_tsm_state"]["pass_probability"] == "DOUBLE"


def test_d16_total_capital_is_decimal():
    """Phase C M035 migrated total_capital DOUBLE → DECIMAL(18, 2)."""
    assert COLUMN_TYPES["p3_d16_user_capital_silos"]["total_capital"] == "DECIMAL(18, 2)"


def test_d16_max_portfolio_risk_pct_is_double():
    """Bookkeeping double — never migrated."""
    assert COLUMN_TYPES["p3_d16_user_capital_silos"]["max_portfolio_risk_pct"] == "DOUBLE"


def test_d23_l_t_is_decimal_after_migration():
    """Phase A M019 migrated l_t DOUBLE → DECIMAL(18, 2)."""
    assert COLUMN_TYPES["p3_d23_circuit_breaker_intraday"]["l_t"] == "DECIMAL(18, 2)"


def test_d23_session_id_is_int_via_add_column():
    """M043 ADD COLUMN session_id INT — must appear in COLUMN_TYPES."""
    assert COLUMN_TYPES["p3_d23_circuit_breaker_intraday"]["session_id"] == "INT"


def test_d25_l_star_is_decimal_after_migration():
    """Phase A M020 migrated l_star DOUBLE → DECIMAL(18, 2)."""
    assert COLUMN_TYPES["p3_d25_circuit_breaker_params"]["l_star"] == "DECIMAL(18, 2)"


def test_d25_r_bar_is_double():
    assert COLUMN_TYPES["p3_d25_circuit_breaker_params"]["r_bar"] == "DOUBLE"


def test_d00_point_value_is_decimal_after_migration():
    """Phase C M036 migrated point_value DOUBLE → DECIMAL(14, 6)."""
    assert COLUMN_TYPES["p3_d00_asset_universe"]["point_value"] == "DECIMAL(14, 6)"


def test_d00_warm_up_progress_is_double():
    assert COLUMN_TYPES["p3_d00_asset_universe"]["warm_up_progress"] == "DOUBLE"


def test_d30_open_high_low_close_are_decimal_after_migration():
    """Phase C M039-M042 migrated OHLC DOUBLE → DECIMAL(14, 6)."""
    for col in ("open", "high", "low", "close"):
        assert COLUMN_TYPES["p3_d30_daily_ohlcv"][col] == "DECIMAL(14, 6)", f"{col} missing or wrong"


def test_d30_volume_is_long():
    assert COLUMN_TYPES["p3_d30_daily_ohlcv"]["volume"] == "LONG"


def test_d11_sharpe_baseline_via_add_column():
    """M003 ADD COLUMN sharpe_baseline DOUBLE — must appear."""
    assert COLUMN_TYPES["p3_d11_pseudotrader_results"]["sharpe_baseline"] == "DOUBLE"


def test_d03_signal_id_via_add_column():
    """M002 ADD COLUMN signal_id STRING — must appear."""
    assert COLUMN_TYPES["p3_d03_trade_outcome_log"]["signal_id"] == "STRING"


def test_d03_model_m_via_add_column():
    """M001 ADD COLUMN model_m INT — must appear."""
    assert COLUMN_TYPES["p3_d03_trade_outcome_log"]["model_m"] == "INT"
