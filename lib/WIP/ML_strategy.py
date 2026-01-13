import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.preprocessing import StandardScaler
from lib.signals.indicators import add_indicators, generate_signals
from lib.strategy import backtest, percentage_of_portfolio
import yfinance as yf

from lib.signals.indicators import add_indicators, generate_signals





def prepare_features(df):
    """Prepare feature set for machine learning model."""
    # Add technical indicators
    df = add_indicators(df)
    
    # Generate trading signals
    df = generate_signals(df)
    
    # Select features for ML model, only including those present in the DataFrame
    all_features = ['CCI', 'BB', 'EMA', 'RSI', 'MACD', 'SMA']
    features = [f for f in all_features if f in df.columns]
    
    # Create target variable (1 for buy, -1 for sell, 0 for hold)
    df['Target'] = 0
    
    # Consider all buy signals
    buy_columns = [col for col in df.columns if col.endswith('Buy')]
    df.loc[df[buy_columns].any(axis=1), 'Target'] = 1
    
    # Consider all sell signals
    sell_columns = [col for col in df.columns if col.endswith('Sell')]
    df.loc[df[sell_columns].any(axis=1), 'Target'] = -1
    
    return df[features], df['Target']

def train_model(X, y):
    """Train a Random Forest model."""
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train_scaled, y_train)
    
    y_pred = model.predict(X_test_scaled)
    accuracy = accuracy_score(y_test, y_pred)
    print(f"Model Accuracy: {accuracy}")
    print(classification_report(y_test, y_pred))
    
    return model, scaler

def predict_signals(model, scaler, X):
    """Predict buy/sell signals using the trained model."""
    X_scaled = scaler.transform(X)
    return model.predict(X_scaled)

def evaluate_strategy(df, initial_capital=10000, percent=0.1):
    """Evaluate the trading strategy using backtest."""
    df['ML_Buy_signal'] = (df['ML_signal'] == 1).astype(int)
    df['ML_Sell_signal'] = (df['ML_signal'] == -1).astype(int)
    
    results = backtest(
        df, 
        initial_capital, 
        percentage_of_portfolio,
        buy_indicators=['ML_Buy_signal'],
        sell_indicators=['ML_Sell_signal'],
        percent=percent,
        delay=1
    )
    
    final_portfolio_value = results['Portfolio_Value'].iloc[-1]
    total_return = (final_portfolio_value - initial_capital) / initial_capital
    
    print(f"Final Portfolio Value: ${final_portfolio_value:.2f}")
    print(f"Total Return: {total_return:.2%}")

