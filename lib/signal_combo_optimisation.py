
from typing import List, Tuple, Callable, Literal, Dict, Any
import pandas as pd
import numpy as np
import dask.dataframe as dd
import pyarrow as pa
import pyarrow.parquet as pq
from dask.distributed import Client, progress
from tqdm.auto import tqdm
import sys
import os
import itertools
from datetime import datetime
from functools import partial, lru_cache

from lib.strategy import *
from lib.data_processing import *

import pandas as pd
import numpy as np
import dask.dataframe as dd
from typing import List, Tuple, Dict, Any
from tqdm.auto import tqdm

from lib.strategy import run_backtest, calculate_max_drawdown
from lib.data_processing import calculate_sharpe_ratio, calculate_win_rate, calculate_profit_factor, calculate_average_trade_duration


# Configurazione
DEFAULT_CHUNK_SIZE = 100
MAX_CACHE_SIZE = 128

def get_default_output_file() -> str:
    """Generate a default output file name in the 'results' directory one level up."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    results_dir = os.path.join(parent_dir, 'results')
    os.makedirs(results_dir, exist_ok=True)
    #timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(results_dir, f'signal_combination_results.parquet')
    #return os.path.join(results_dir, f'signal_combination_results.parquet')

def setup_environment() -> None:
    """Configure the execution environment."""
    current_dir = os.getcwd()
    parent_dir = os.path.dirname(current_dir)
    sys.path.append(parent_dir)

@lru_cache(maxsize=MAX_CACHE_SIZE)
def generate_ordered_combinations(buy_signals: Tuple[str, ...], sell_signals: Tuple[str, ...], max_signals: int) -> List[Tuple[Tuple[str, ...], Tuple[str, ...]]]:
    """Generate ordered combinations of buy and sell signals."""
    all_combinations = []
    for i in range(1, max_signals + 1):
        buy_combos = list(itertools.combinations(buy_signals, i))
        sell_combos = list(itertools.combinations(sell_signals, i))
        all_combinations.extend(itertools.product(buy_combos, sell_combos))
    return all_combinations

def test_combination(df: dd.DataFrame, params: Dict[str, Any]) -> pd.Series:
    """Test a combination of buy and sell signals using run_backtest."""
    try:
        result_df = run_backtest(
            df=df,
            initial_capital=params['initial_capital'],
            buy_indicators=list(params['buy_combo']),
            sell_indicators=list(params['sell_combo'])
        )

        buy_signals_count = result_df[list(params['buy_combo'])].sum().sum() if params['buy_combo'] else 0
        sell_signals_count = result_df[list(params['sell_combo'])].sum().sum() if params['sell_combo'] else 0
            
        final_portfolio_value = result_df['Portfolio_Value'].iloc[-1]
        total_return = (final_portfolio_value - params['initial_capital']) / params['initial_capital']
        annual_return = (result_df['Cumulative_Returns'].iloc[-1] ** (252 / len(result_df)) - 1)
        
        return pd.Series({
            'Buy_Signals': str(params['buy_combo']),
            'Sell_Signals': str(params['sell_combo']),
            'Buy_Signals_Count': buy_signals_count,
            'Sell_Signals_Count': sell_signals_count,
            'Final_Portfolio_Value': final_portfolio_value,
            'Total_Return': total_return,
            'Annual_Return': annual_return,
            'Max_Drawdown': calculate_max_drawdown(result_df),
            'Sharpe_Ratio': calculate_sharpe_ratio(result_df['Strategy_Returns']),
            'Win_Rate': calculate_win_rate(result_df),
            'Profit_Factor': calculate_profit_factor(result_df),
            'Average_Trade_Duration': calculate_average_trade_duration(result_df)
        })
    except Exception as e:
        print(f"Error in test_combination: {str(e)}")
        print(f"Buy combo: {params['buy_combo']}")
        print(f"Sell combo: {params['sell_combo']}")
        return pd.Series({
            'Buy_Signals': str(params['buy_combo']),
            'Sell_Signals': str(params['sell_combo']),
            'Error': str(e)
        })

# Avoid pytest collecting this production function as a test.
test_combination.__test__ = False

def process_chunk(chunk: List[Tuple[Tuple[str, ...], Tuple[str, ...]]], df: dd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
    """Process a chunk of signal combinations."""
    results = []
    for buy_combo, sell_combo in tqdm(chunk, desc="Processing combinations", leave=False):
        params_copy = params.copy()
        params_copy['buy_combo'] = buy_combo
        params_copy['sell_combo'] = sell_combo
        result = test_combination(df, params_copy)
        results.append(result)
    return pd.DataFrame(results)

def test_all_combinations(
    df: pd.DataFrame,
    initial_capital: float,
    combination_type: str,
    max_combinations: int = 1000,
    max_signals: int = 50,
    output_file: str = None,
    chunk_size: int = 100
) -> Tuple[pd.DataFrame, Tuple[str, ...], Tuple[str, ...], float, str]:
    """Test all combinations of buy and sell signals."""
    setup_environment()
    
    output_file = output_file or get_default_output_file()
    
    buy_signals, sell_signals = extract_signals(df)

    print(f"Available buy signals: {buy_signals}")
    print(f"Available sell signals: {sell_signals}")
    print(f"Maximum signals per combination: {max_signals}")
    print(f"Results will be saved to: {output_file}")
    
    if combination_type == 'Buy_Only':
        combinations = [(combo, tuple()) for combo in generate_ordered_combinations(tuple(buy_signals), tuple(), max_signals)]
    elif combination_type == 'Sell_Only':
        combinations = [(tuple(), combo) for combo in generate_ordered_combinations(tuple(), tuple(sell_signals), max_signals)]
    elif combination_type == 'Buy_&_Sell':
        combinations = generate_ordered_combinations(tuple(buy_signals), tuple(sell_signals), max_signals)
    else:
        raise ValueError("Invalid combination_type. Must be 'Buy_Only', 'Sell_Only', or 'Buy_&_Sell'.")
    
    combinations = combinations[:max_combinations]
    total_combinations = len(combinations)
    print(f"Testing {total_combinations} combinations...")

    params = {
        'initial_capital': initial_capital,
    }

    all_results = []
    with Client() as client:
        futures = []
        for i in range(0, total_combinations, chunk_size):
            chunk = combinations[i:i+chunk_size]
            future = client.submit(process_chunk, chunk, df, params)
            futures.append(future)
        
        for future in tqdm(futures, desc="Processing chunks"):
            result = future.result()
            all_results.append(result)

    final_results = pd.concat(all_results, ignore_index=True)

    try:
        save_to_parquet(final_results, output_file)
        print(f"Results saved to {output_file}")
    except Exception as e:
        print(f"Error saving results to Parquet file: {str(e)}")
        print("Using in-memory results instead.")

    print("Columns in the results DataFrame:", final_results.columns.tolist())
    print("First 5 results:")
    print(final_results.head())

    if final_results.empty:
        print("No valid strategies found after filtering. Try adjusting your parameters.")
        return pd.DataFrame(), None, None, None, output_file
    
    best_column = 'Final_Portfolio_Value' if 'Final_Portfolio_Value' in final_results.columns else final_results.columns[-1]
    best_strategy = final_results.loc[final_results[best_column].idxmax()]
    
    return final_results, eval(best_strategy['Buy_Signals']), eval(best_strategy['Sell_Signals']), best_strategy[best_column], output_file

def extract_signals(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    """Extract buy and sell signals from DataFrame columns."""
    buy_signals = [col for col in df.columns if 'buy' in col.lower()]
    sell_signals = [col for col in df.columns if 'sell' in col.lower()]
    return buy_signals, sell_signals

def save_to_parquet(df: pd.DataFrame, output_file: str) -> None:
    """Save DataFrame to Parquet file."""
    for col in df.columns:
        if df[col].dtype == 'object':
            df[col] = df[col].astype(str)
    table = pa.Table.from_pandas(df)
    pq.write_table(table, output_file)