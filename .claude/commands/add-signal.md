Add a new technical indicator signal strategy to the project.

Usage: /add-signal [INDICATOR_NAME]

Example: /add-signal STOCHASTIC

Steps to follow:
1. Read `lib/signals/base_strategy.py` to understand the base class interface.
2. Read one existing strategy (e.g. `lib/signals/signals_RSI.py`) as a reference implementation.
3. Read `lib/signals/indicators.py` to understand how strategies are registered.
4. Read `config/strategy_config.yaml` to understand the config schema.
5. Create `lib/signals/signals_{INDICATOR_NAME}.py`:
   - Class named `{INDICATOR_NAME}_TradingStrategy` inheriting `BaseStrategy`
   - Method `generate_signals(df)` that adds `{INDICATOR_NAME}_*_Buy` and `{INDICATOR_NAME}_*_Sell` columns
   - Pull all configurable params from `self.config` (never hardcode)
6. Register the new strategy in `lib/signals/indicators.py`:
   - Import the class
   - Call it inside `add_indicators()`
   - Add its signal columns to `generate_signals()`
7. Add default parameters to `config/strategy_config.yaml` under a new key.
8. Add a test to `lib/tests/` following the existing test patterns.
9. Report what was created and show a usage example.
