import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from ta.momentum import StochasticOscillator

def optimize_stochastic_params(df, target_column, param_range=(5, 30)):
    best_sharpe = -np.inf
    best_params = None
    
    for k in range(param_range[0], param_range[1]):
        for d in range(1, 10):
            stoch = StochasticOscillator(df['high'], df['low'], df['close'], k, d)
            df['stoch_k'] = stoch.stoch()
            df['stoch_d'] = stoch.stoch_signal()
            
            # Calcola i rendimenti
            df['returns'] = df[target_column].pct_change()
            
            # Strategia semplice: compra quando %K > %D, vendi quando %K < %D
            df['signal'] = np.where(df['stoch_k'] > df['stoch_d'], 1, -1)
            df['strategy_returns'] = df['signal'].shift(1) * df['returns']
            
            # Calcola Sharpe Ratio
            sharpe_ratio = np.sqrt(252) * df['strategy_returns'].mean() / df['strategy_returns'].std()
            
            if sharpe_ratio > best_sharpe:
                best_sharpe = sharpe_ratio
                best_params = (k, d)
    
    return best_params

def detect_hidden_divergence(df, window=14):
    df['low_low'] = df['low'].rolling(window=window).min()
    df['high_high'] = df['high'].rolling(window=window).max()
    
    # Divergenza nascosta rialzista
    df['bullish_div'] = ((df['low'] > df['low_low'].shift(1)) & 
                         (df['stoch_k'] < df['stoch_k'].shift(1)))
    
    # Divergenza nascosta ribassista
    df['bearish_div'] = ((df['high'] < df['high_high'].shift(1)) & 
                         (df['stoch_k'] > df['stoch_k'].shift(1)))
    
    return df

def find_key_levels(df, n=5):
    df['support'] = df['low'].rolling(window=2*n+1, center=True).apply(lambda x: x[n] == min(x))
    df['resistance'] = df['high'].rolling(window=2*n+1, center=True).apply(lambda x: x[n] == max(x))
    return df

def prepare_features(df):
    df['stoch_diff'] = df['stoch_k'] - df['stoch_d']
    df['close_sma_ratio'] = df['close'] / df['close'].rolling(window=50).mean()
    df['volume_sma_ratio'] = df['volume'] / df['volume'].rolling(window=20).mean()
    
    feature_columns = ['stoch_k', 'stoch_d', 'stoch_diff', 'close_sma_ratio', 'volume_sma_ratio']
    return df[feature_columns]

def train_ml_model(df):
    X = prepare_features(df)
    y = np.where(df['close'].shift(-1) > df['close'], 1, 0)  # 1 se il prezzo sale, 0 altrimenti
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    
    return model

def refined_stochastic_strategy(df, target_column='close'):
    # Ottimizza i parametri dello stocastico
    best_k, best_d = optimize_stochastic_params(df, target_column)
    stoch = StochasticOscillator(df['high'], df['low'], df['close'], best_k, best_d)
    df['stoch_k'] = stoch.stoch()
    df['stoch_d'] = stoch.stoch_signal()
    
    # Rileva divergenze nascoste
    df = detect_hidden_divergence(df)
    
    # Trova livelli chiave
    df = find_key_levels(df)
    
    # Addestra il modello di machine learning
    ml_model = train_ml_model(df)
    
    # Genera segnali
    df['ml_prediction'] = ml_model.predict(prepare_features(df))
    
    df['signal'] = 0
    df.loc[(df['stoch_k'] > df['stoch_d']) & (df['bullish_div']) & (df['support']) & (df['ml_prediction'] == 1), 'signal'] = 1
    df.loc[(df['stoch_k'] < df['stoch_d']) & (df['bearish_div']) & (df['resistance']) & (df['ml_prediction'] == 0), 'signal'] = -1
    
    return df

# Uso della strategia
# Assumiamo che 'df' sia un DataFrame con colonne: open, high, low, close, volume
# df = pd.read_csv('your_data.csv')
# df = refined_stochastic_strategy(df)
# 
# # Calcola i rendimenti della strategia
# df['returns'] = df['close'].pct_change()
# df['strategy_returns'] = df['signal'].shift(1) * df['returns']
# 
# # Calcola le performance
# cumulative_returns = (1 + df['strategy_returns']).cumprod()
# total_return = cumulative_returns.iloc[-1] - 1
# sharpe_ratio = np.sqrt(252) * df['strategy_returns'].mean() / df['strategy_returns'].std()
# 
# print(f"Total Return: {total_return:.2%}")
# print(f"Sharpe Ratio: {sharpe_ratio:.2f}")