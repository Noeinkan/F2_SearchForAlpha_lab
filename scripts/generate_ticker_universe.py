#!/usr/bin/env python3
"""
Generate comprehensive tickers_universe.csv from GitHub and Wikipedia sources.
This populates config/tickers_universe.csv with all S&P 500 and NASDAQ tickers.

Usage:
    python scripts/generate_ticker_universe.py
"""

import sys
from pathlib import Path
import pandas as pd

# Add lib to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.data_processing import (
    _fetch_sp500_from_github,
    _fetch_from_wikipedia,
)

def generate_ticker_universe():
    """Fetch all S&P 500 and NASDAQ tickers and save to CSV."""
    
    print("Generating comprehensive ticker universe...")
    
    # Fetch S&P 500 from GitHub
    print("  • Fetching S&P 500 from GitHub...")
    sp500_df = _fetch_sp500_from_github()
    if sp500_df is not None and not sp500_df.empty:
        print(f"    ✓ Got {len(sp500_df)} S&P 500 tickers")
    else:
        print("    ✗ Failed to fetch S&P 500")
        sp500_df = pd.DataFrame()
    
    # Fetch NASDAQ from Wikipedia
    print("  • Fetching NASDAQ from Wikipedia...")
    nasdaq_df = _fetch_from_wikipedia()
    if nasdaq_df is not None and not nasdaq_df.empty:
        print(f"    ✓ Got {len(nasdaq_df)} NASDAQ tickers")
    else:
        print("    ✗ Failed to fetch NASDAQ")
        nasdaq_df = pd.DataFrame()
    
    # Combine and deduplicate
    combined = pd.concat([sp500_df, nasdaq_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=['Symbol'], keep='first')
    
    # Ensure required columns exist
    if 'Exchange' not in combined.columns:
        if 'Index' in combined.columns:
            combined['Exchange'] = combined['Index'].apply(
                lambda x: 'NASDAQ' if 'NASDAQ' in str(x) else 'NYSE'
            )
        else:
            combined['Exchange'] = 'NYSE'
    
    # Normalize and clean
    combined['Symbol'] = combined['Symbol'].str.strip().str.upper()
    combined = combined[combined['Symbol'].notna()]
    combined = combined[combined['Symbol'] != '']
    
    # Reorder columns
    cols_order = ['Symbol', 'Security', 'Index', 'Exchange']
    available_cols = [c for c in cols_order if c in combined.columns]
    combined = combined[available_cols]
    
    print(f"\n  Total unique tickers: {len(combined)}")
    
    # Save to CSV
    output_path = Path(__file__).parent.parent / 'config' / 'tickers_universe.csv'
    combined.to_csv(output_path, index=False)
    print(f"\n✓ Saved {len(combined)} tickers to {output_path}")
    
    # Show sample
    print("\nFirst 10 tickers:")
    print(combined.head(10).to_string(index=False))
    
    return combined

if __name__ == '__main__':
    try:
        generate_ticker_universe()
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)
