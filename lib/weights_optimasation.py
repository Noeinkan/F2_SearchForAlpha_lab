# walk_forward_optimization module

import pandas as pd
import numpy as np
from scipy.optimize import minimize

def walk_forward_optimisation(df, indicators, initial_lookback=252, 
                              optimization_window=126, validation_window=63):
    
    optimized_weights = pd.DataFrame(index=df.index, columns=indicators)
    
    for start in range(initial_lookback, len(df) - validation_window, validation_window):
        end = start + optimization_window
        validation_end = end + validation_window
        
        # Subset di dati per l'ottimizzazione
        optimization_data = df.iloc[start:end]
        
        # Ottimizzazione dei pesi
        weights = optimize_weights(optimization_data, indicators)
        
        # Applicazione dei pesi ottimizzati al periodo di validazione
        optimized_weights.iloc[end:validation_end] = pd.Series(weights)
    
    # Riempimento dei valori NaN con pesi uguali
    optimized_weights = optimized_weights.fillna(1/len(indicators))
    
    return optimized_weights

def optimize_weights(data, indicators):
    def objective(weights, data, indicators):
        weighted_signal = sum(data[ind] * w for ind, w in zip(indicators, weights))
        return -np.corrcoef(weighted_signal, data['returns'])[0,1]
    
    constraints = ({'type': 'eq', 'fun': lambda w: np.sum(w) - 1})
    bounds = tuple((0, 1) for _ in indicators)
    
    result = minimize(objective, [1/len(indicators)]*len(indicators), 
                      args=(data, indicators), 
                      method='SLSQP', constraints=constraints, bounds=bounds)
    
    return dict(zip(indicators, result.x))
