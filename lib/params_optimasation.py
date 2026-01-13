import pandas as pd
import numpy as np
import itertools
from typing import Dict, List, Tuple, Any
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
from lib.strategy import backtest, calculate_max_drawdown



def optimize_parameters(df: pd.DataFrame, 
                        initial_capital: float,
                        param_ranges: Dict[str, List[Any]],
                        metric: str = 'total_return',
                        n_jobs: int = -1) -> Tuple[Dict[str, Any], float]:
    """
    Optimize strategy parameters using grid search.
    
    :param df: DataFrame with price data and indicators
    :param initial_capital: Initial capital for backtesting
    :param param_ranges: Dictionary of parameters and their possible values
    :param metric: Metric to optimize ('total_return', 'sharpe_ratio', etc.)
    :param n_jobs: Number of parallel jobs to run (-1 for all available cores)
    :return: Tuple of best parameters and best metric value
    """
    param_combinations = list(itertools.product(*param_ranges.values()))
    param_keys = list(param_ranges.keys())
    
    def evaluate_params(params):
        param_dict = dict(zip(param_keys, params))
        result_df = backtest(df, initial_capital, **param_dict)
        return param_dict, calculate_metric(result_df, metric)
    
    best_params = None
    best_metric_value = float('-inf') if metric != 'max_drawdown' else float('inf')
    
    with ProcessPoolExecutor(max_workers=n_jobs) as executor:
        futures = [executor.submit(evaluate_params, params) for params in param_combinations]
        
        for future in tqdm(as_completed(futures), total=len(param_combinations), desc="Optimizing parameters"):
            params, metric_value = future.result()
            
            if metric == 'max_drawdown':
                if metric_value < best_metric_value:
                    best_metric_value = metric_value
                    best_params = params
            else:
                if metric_value > best_metric_value:
                    best_metric_value = metric_value
                    best_params = params
    
    return best_params, best_metric_value

def calculate_metric(df: pd.DataFrame, metric: str) -> float:
    if metric == 'total_return':
        return (df['Portfolio_Value'].iloc[-1] / df['Portfolio_Value'].iloc[0]) - 1
    elif metric == 'sharpe_ratio':
        returns = df['Strategy_Returns']
        return (returns.mean() / returns.std()) * np.sqrt(252)  # Annualized Sharpe Ratio
    elif metric == 'max_drawdown':
        return calculate_max_drawdown(df)
    else:
        raise ValueError(f"Unknown metric: {metric}")

