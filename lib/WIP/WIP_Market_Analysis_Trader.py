import numpy as np
import pandas as pd
from typing import List, Tuple
from scipy.signal import savgol_filter, find_peaks
from sklearn.cluster import DBSCAN
from dataclasses import dataclass

# Configurazione
CONFIG = {
    'window_length': 21,
    'poly_order': 3,
    'prominence': 0.02,
    'eps': 0.02,
    'min_samples': 2,
    'lookback': 5,
    'threshold': 0.01,
    'consolidation_window': 20,
    'consolidation_threshold': 0.02
}

@dataclass
class TradingParameters:
    window_length: int
    poly_order: int
    prominence: float
    eps: float
    min_samples: int
    lookback: int
    threshold: float
    consolidation_window: int
    consolidation_threshold: float

    @classmethod
    def from_config(cls, config: dict) -> 'TradingParameters':
        return cls(**config)

class MarketAnalysisTrader:
    def __init__(self, price_data: List[float], params: TradingParameters):
        self.df = pd.DataFrame({'price': price_data})
        self.df['timestamp'] = pd.date_range(start='2023-01-01', periods=len(price_data), freq='D')
        self.df.set_index('timestamp', inplace=True)
        self.support_levels: List[Tuple[pd.Timestamp, float]] = []
        self.resistance_levels: List[Tuple[pd.Timestamp, float]] = []
        self.params = params

    def identify_support_resistance(self) -> None:
        self.df['smoothed_price'] = savgol_filter(self.df['price'], 
                                                  self.params.window_length, 
                                                  self.params.poly_order)

        peaks, _ = find_peaks(self.df['smoothed_price'], prominence=self.params.prominence)
        troughs, _ = find_peaks(-self.df['smoothed_price'], prominence=self.params.prominence)

        self.resistance_levels = self._cluster_levels(peaks)
        self.support_levels = self._cluster_levels(troughs)

    def _cluster_levels(self, indices: np.ndarray) -> List[Tuple[pd.Timestamp, float]]:
        if len(indices) == 0:
            return []

        prices = self.df['price'].iloc[indices].values.reshape(-1, 1)
        clustering = DBSCAN(eps=self.params.eps, min_samples=self.params.min_samples).fit(prices)

        return [
            (self.df.index[cluster_indices].mean(), self.df['price'].iloc[cluster_indices].mean())
            for cluster in set(clustering.labels_) if cluster != -1
            for cluster_indices in [indices[clustering.labels_ == cluster]]
        ]

    def is_liquidity_clearout(self) -> pd.Series:
        high = self.df['price'].rolling(window=self.params.lookback).max()
        low = self.df['price'].rolling(window=self.params.lookback).min()
        
        clearout_up = (self.df['price'] > high.shift(1) * (1 + self.params.threshold)) & (self.df['price'].shift(-1) < self.df['price'])
        clearout_down = (self.df['price'] < low.shift(1) * (1 - self.params.threshold)) & (self.df['price'].shift(-1) > self.df['price'])
        
        return pd.Series(data=np.select([clearout_up, clearout_down], ['UP', 'DOWN'], default='NONE'), index=self.df.index)

    def find_consolidation(self) -> pd.DataFrame:
        self.df['rolling_std'] = self.df['price'].rolling(window=self.params.consolidation_window).std()
        overall_std = self.df['price'].std()
        
        consolidation_mask = self.df['rolling_std'] < (overall_std * self.params.consolidation_threshold)
        
        consolidation_groups = consolidation_mask.ne(consolidation_mask.shift()).cumsum()
        consolidations = consolidation_mask.groupby(consolidation_groups).agg(['all', 'idxmin', 'idxmax'])
        consolidations = consolidations[consolidations['all']]
        
        return consolidations[['idxmin', 'idxmax']].rename(columns={'idxmin': 'start', 'idxmax': 'end'})

    def generate_trade_signals(self) -> pd.Series:
        clearouts = self.is_liquidity_clearout()
        
        round_numbers = self.df['price'].round(-1)
        near_round = (abs(self.df['price'] - round_numbers) / self.df['price']) < 0.01
        
        return pd.Series(index=self.df.index, data='HOLD').mask(
            clearouts == 'UP', 'BUY'
        ).mask(
            clearouts == 'DOWN', 'SELL'
        ).mask(
            near_round, 'POTENTIAL_REVERSAL'
        )

    def backtest_strategy(self) -> float:
        signals = self.generate_trade_signals()
        
        self.df['position'] = signals.map({'BUY': 1, 'SELL': -1, 'HOLD': 0, 'POTENTIAL_REVERSAL': 0})
        self.df['returns'] = self.df['price'].pct_change()
        self.df['strategy_returns'] = self.df['position'].shift(1) * self.df['returns']
        
        total_return = (1 + self.df['strategy_returns']).prod() - 1
        return total_return * 1000  # Assuming initial balance of 1000

def run_analysis(price_data: List[float]) -> None:
    params = TradingParameters.from_config(CONFIG)
    trader = MarketAnalysisTrader(price_data, params)
    trader.identify_support_resistance()
    profit_loss = trader.backtest_strategy()
    
    print(f"Profit/Loss: ${profit_loss:.2f}")
    print("\nSupport Levels:")
    print(trader.support_levels)
    print("\nResistance Levels:")
    print(trader.resistance_levels)
    print("\nConsolidation Periods:")
    print(trader.find_consolidation())
    print("\nTrade Signals:")
    print(trader.generate_trade_signals().value_counts())

if __name__ == "__main__":
    price_data = [100, 101, 102, 101, 100, 99, 98, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 105, 104, 103]
    run_analysis(price_data)