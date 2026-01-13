def backtest(df: pd.DataFrame, 
             initial_capital: float,
             position_sizing_strategy: str,
             position_sizing_params: dict,
             buy_indicators: List[str],
             sell_indicators: List[str],
             use_signal_strength: bool = False,
             indicator_weights: Dict[str, float] = None,
             buy_threshold: float = 0.5,
             sell_threshold: float = 0.5,
             delay: int = 1,
             min_holding_period: int = 0,
             position_scaling: float = 0.25,
             trailing_stop_loss: float = 0.05,
             volatility_window: int = 20) -> pd.DataFrame:

    num_rows = len(df)
    
    # Initialize arrays
    units = np.zeros(num_rows)
    cash_value = np.full(num_rows, initial_capital)
    stocks_value = np.zeros(num_rows)
    portfolio_value = np.full(num_rows, initial_capital)
    units_to_buy = np.zeros(num_rows)
    units_to_sell = np.zeros(num_rows)
    buy_signal_counter = np.zeros(num_rows, dtype=int)
    sell_signal_counter = np.zeros(num_rows, dtype=int)
    holding_period = np.zeros(num_rows, dtype=int)
    trailing_stop = np.full(num_rows, np.inf)

    # Get position sizer function
    position_sizer = get_position_sizer(position_sizing_strategy, **position_sizing_params)

    if use_signal_strength:
        buy_signal_strength, sell_signal_strength = calculate_signal_strengths(df, buy_indicators, sell_indicators, indicator_weights)
    else:
        buy_signal_strength = df[buy_indicators].sum(axis=1)
        sell_signal_strength = df[sell_indicators].sum(axis=1)

    # Calculate volatility
    df['Volatility'] = df['Close'].pct_change().rolling(window=volatility_window).std()

    close_prices = df['Close'].values
    returns = np.zeros(num_rows)
    returns[1:] = (close_prices[1:] - close_prices[:-1]) / close_prices[:-1]

    last_buy_price = 0
    position_size = 0

    for i in range(1 + delay, num_rows):
        close_price = close_prices[i]
        prev_portfolio_value = portfolio_value[i-1]
        prev_cash_value = cash_value[i-1]
        prev_units = units[i-1]

        # Update holding period
        if prev_units > 0:
            holding_period[i] = holding_period[i-1] + 1
        else:
            holding_period[i] = 0

        # Check for trailing stop loss
        if prev_units > 0 and close_price <= trailing_stop[i-1]:
            units_to_sell[i] = prev_units
            value_to_sell = units_to_sell[i] * close_price
            units[i] = 0
            cash_value[i] = prev_cash_value + value_to_sell
            last_buy_price = 0
            position_size = 0
            trailing_stop[i] = np.inf
        else:
            # Buy signal
            if (use_signal_strength and buy_signal_strength[i] > buy_threshold) or \
            (not use_signal_strength and buy_signal_strength[i] > 0):
                buy_signal_counter[i] = buy_signal_counter[i-1] + 1
                position_size = min(position_size + position_scaling, 1)
                
                if position_sizing_strategy == "volatility_based":
                    units_to_buy[i] = position_sizer(prev_portfolio_value, close_price, df['Volatility'].iloc[i])
                else:
                    units_to_buy[i] = position_sizer(prev_portfolio_value, close_price)
                
                units_to_buy[i] = int(units_to_buy[i] * position_size)
                
                if units_to_buy[i] > 0:
                    value_to_buy = units_to_buy[i] * close_price
                    units[i] = prev_units + units_to_buy[i]
                    cash_value[i] = prev_cash_value - value_to_buy
                    last_buy_price = close_price
                    trailing_stop[i] = close_price * (1 - trailing_stop_loss)
                else:
                    units[i] = prev_units
                    cash_value[i] = prev_cash_value
            # Sell signal
            elif (use_signal_strength and sell_signal_strength[i] > sell_threshold) or \
                (not use_signal_strength and sell_signal_strength[i] > 0):
                if holding_period[i] >= min_holding_period:
                    sell_signal_counter[i] = sell_signal_counter[i-1] + 1
                    position_size = max(position_size - position_scaling, 0)
                    
                    if position_sizing_strategy == "volatility_based":
                        units_to_sell[i] = position_sizer(prev_portfolio_value, close_price, df['Volatility'].iloc[i])
                    else:
                        units_to_sell[i] = position_sizer(prev_portfolio_value, close_price)
                    
                    units_to_sell[i] = min(int(units_to_sell[i] * (1 - position_size)), prev_units)
                    
                    if units_to_sell[i] > 0:
                        value_to_sell = units_to_sell[i] * close_price
                        units[i] = prev_units - units_to_sell[i]
                        cash_value[i] = prev_cash_value + value_to_sell
                        if units[i] == 0:
                            last_buy_price = 0
                            trailing_stop[i] = np.inf
                        else:
                            trailing_stop[i] = max(trailing_stop[i-1], close_price * (1 - trailing_stop_loss))
                    else:
                        units[i] = prev_units
                        cash_value[i] = prev_cash_value
                else:
                    units[i] = prev_units
                    cash_value[i] = prev_cash_value
                    trailing_stop[i] = max(trailing_stop[i-1], close_price * (1 - trailing_stop_loss)) if prev_units > 0 else np.inf
            else:
                units[i] = prev_units
                cash_value[i] = prev_cash_value
                trailing_stop[i] = max(trailing_stop[i-1], close_price * (1 - trailing_stop_loss)) if prev_units > 0 else np.inf

        stocks_value[i] = units[i] * close_price
        portfolio_value[i] = cash_value[i] + stocks_value[i]

    # Calculate returns and create result DataFrame
    strategy_returns, cumulative_returns, cumulative_market_returns = calculate_returns(portfolio_value, returns)
    
    result_df = create_result_dataframe(df, units, units_to_buy, units_to_sell, cash_value, stocks_value, portfolio_value,
                                        buy_signal_strength > buy_threshold, sell_signal_strength > sell_threshold,
                                        returns, strategy_returns, cumulative_returns, cumulative_market_returns,
                                        holding_period, trailing_stop)

    return result_df