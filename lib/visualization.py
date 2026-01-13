# visualization module

import os
import numpy as np
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.dates import DateFormatter, MonthLocator
from adjustText import adjust_text


def plot_financial_chart(df, ticker, save_path=None, show_buy_signals=None, show_sell_signals=None):
    # Ensure index is datetime
    df.index = pd.to_datetime(df.index)
    
    # Define colors
    sma_colors = ['#006400', '#228B22', '#32CD32', '#90EE90']
    
    # Create a custom style dictionary
    custom_style = mpf.make_mpf_style(base_mpf_style='charles', gridcolor='#D3D3D3', rc={'grid.alpha': 0.3})

    # Create the main figure
    fig = plt.figure(figsize=(16, 24))
    gs = fig.add_gridspec(8, 1)

    # Create axes for price, volume, and signals
    ax1 = fig.add_subplot(gs[0:2, 0])
    ax1v = fig.add_subplot(gs[2, 0], sharex=ax1)
    ax2 = fig.add_subplot(gs[3:5, 0], sharex=ax1)
    ax3 = fig.add_subplot(gs[5, 0], sharex=ax2)  # CCI
    ax4 = fig.add_subplot(gs[6, 0], sharex=ax2)  # RSI
    ax5 = fig.add_subplot(gs[7, 0], sharex=ax2)  # MACD

    # Plot first graph (Price, Volume, Bollinger Bands, and SMAs)
    mpf.plot(df, type='candle', style=custom_style, ax=ax1, volume=ax1v, show_nontrading=True, datetime_format='%m-%Y')
    
    # Add Bollinger Bands and SMAs to the first graph
    ax1.plot(df.index, df['BB_upper'], color='darkred', linestyle='-', linewidth=0.3, label='Upper BB')
    ax1.plot(df.index, df['BB_lower'], color='darkgreen', linestyle='-', linewidth=0.3, label='Lower BB')
    ax1.plot(df.index, df['BB_middle'], color='blue', linewidth=0.2, label='Mid BB')
    ax1.plot(df.index, df['SMA_short'], color=sma_colors[3], linewidth=0.2, label='Short SMA')
    ax1.plot(df.index, df['SMA_medium'], color=sma_colors[2], linewidth=0.2, label='Medium SMA')
    ax1.plot(df.index, df['SMA_long'], color=sma_colors[1], linewidth=0.2, label='Long SMA')
    ax1.plot(df.index, df['SMA_trend'], color=sma_colors[0], linewidth=0.2, label='Trend SMA')
    ax1.legend(loc='upper left', fontsize='x-small')

    # Plot second graph (Price with Buy/Sell Signals)
    mpf.plot(df, type='candle', style=custom_style, ax=ax2, show_nontrading=True, datetime_format='%m-%Y')

    def create_price_annotation(ax, date, y, text, is_buy):
        color = 'darkgreen' if is_buy else 'darkred'
        va = 'top' if is_buy else 'bottom'
        y_offset = -0.05 if is_buy else 0.05
        y_range = ax.get_ylim()[1] - ax.get_ylim()[0]
        text_y = y + y_offset * y_range
        
        return ax.annotate(
            text,
            xy=(date, y), xytext=(date, text_y),
            xycoords='data',
            fontsize=2, color=color,
            bbox=dict(facecolor=color, edgecolor=None, alpha=0.7, boxstyle='round,pad=0.05'),
            ha='center', va=va,
            arrowprops=dict(arrowstyle='-', color=color, lw=0.3, alpha=0.5),
            zorder=10
        )

    def create_indicator_annotation(ax, date, y, text, is_buy, offset=0):
        color = 'darkgreen' if is_buy else 'darkred'
        text_y = y + offset
        return ax.annotate(
            text,
            xy=(date, y), xytext=(date, text_y),
            xycoords='data',
            fontsize=2, color=color,
            bbox=dict(facecolor='white', edgecolor=color, alpha=0.5, boxstyle='round,pad=0.2'),
            ha='center', va='bottom',
            arrowprops=dict(arrowstyle='-', color=color, lw=0.3, alpha=0.5),
            zorder=10
        )

    def add_indicator_annotations(ax, date, row, is_buy, indicator):
        y = row[indicator]
        text = f"{indicator}:{y:.2f}"
        create_indicator_annotation(ax, date, y, text, is_buy)

    # Add buy and sell signals with annotations
    for is_buy in [True, False]:
        if (is_buy and show_buy_signals) or (not is_buy and show_sell_signals):
            signal_col = next((col for col in df.columns if ('buy' if is_buy else 'sell') in col.lower() and 'signal' in col.lower()), None)
            units_col = next((col for col in df.columns if 'units' in col.lower() and ('buy' if is_buy else 'sell') in col.lower()), None)
            
            if signal_col is None or units_col is None:
                print(f"Warning: {'Buy' if is_buy else 'Sell'} signal or units column not found")
                continue
            
            signal_df = df[df[signal_col] == 1]
            
            for date, row in signal_df.iterrows():
                y = row['Close']
                units = row[units_col]
                
                # Plot marker on price chart
                marker = '^' if is_buy else 'v'
                color = 'darkgreen' if is_buy else 'darkred'
                ax2.scatter(date, y, color=color, marker=marker, s=20, alpha=0.5,
                            label='Buy Signal' if is_buy else 'Sell Signal')
                
                # Create annotation for buy/sell signal
                price_text = f"Price: ${y:.2f}\nUnits: {units:.2f}"
                create_price_annotation(ax2, date, y, price_text, is_buy)
                
                # Create annotations for different charts
                add_indicator_annotations(ax3, date, row, is_buy, 'CCI')
                add_indicator_annotations(ax4, date, row, is_buy, 'RSI')
                add_indicator_annotations(ax5, date, row, is_buy, 'MACD')

            # Add vertical lines for signals        
            lines_color = 'darkgreen' if is_buy else 'darkred'
            for date in signal_df.index:
                for ax in [ax1, ax1v, ax2, ax3, ax4, ax5]:
                    ax.axvline(x=date, color=color, linewidth=0.3, linestyle='-.', alpha=0.6)

    # Plot additional indicators
    ax3.plot(df.index, df['CCI'], color='b', linewidth=0.3)
    ax3.axhline(y=100, color='darkblue', linestyle='--', linewidth=0.5)
    ax3.axhline(y=-100, color='darkblue', linestyle='--', linewidth=0.5)
    ax3.set_ylabel('CCI')

    ax4.plot(df.index, df['RSI'], color='m', linewidth=0.3)
    ax4.axhline(y=70, color='darkviolet', linestyle='--', linewidth=0.5)
    ax4.axhline(y=30, color='darkviolet', linestyle='--', linewidth=0.5)
    ax4.set_ylabel('RSI')

    ax5.plot(df.index, df['MACD'], color='b', linewidth=0.3, label='MACD')
    ax5.plot(df.index, df['MACD_signal'], color='r', linewidth=0.3, label='Signal')
    ax5.bar(df.index, df['MACD_hist'], color=['green' if v >= 0 else 'red' for v in df['MACD_hist']], alpha=1, width=1)
    ax5.set_ylabel('MACD')
    ax5.legend(loc='upper left', fontsize='x-small')

    # Set x-axis ticks
    for ax in [ax1, ax1v, ax2, ax3, ax4, ax5]:
        ax.xaxis.set_major_locator(MonthLocator(interval=3))
        ax.xaxis.set_major_formatter(DateFormatter('%b %Y'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

    # Hide x-axis for all subplots except the last one
    for ax in [ax1, ax1v, ax2, ax3, ax4]:
        ax.xaxis.set_visible(False)

    # Adjust y-axis label font size
    for ax in [ax1, ax1v, ax2, ax3, ax4, ax5]:
        ax.yaxis.label.set_fontsize(10)

    # Add titles to the subplots
    ax1.set_title('Price, Bollinger Bands, and SMAs', fontsize=12)
    ax1v.set_title('Volume', fontsize=12)
    ax2.set_title('Price with Buy/Sell Signals', fontsize=12)
    ax3.set_title('CCI', fontsize=12)
    ax4.set_title('RSI', fontsize=12)
    ax5.set_title('MACD', fontsize=12)

    plt.tight_layout()

    # Save and display the chart
    if save_path:
        filename = os.path.join(save_path, f"{ticker}_split_financial_chart.jpg")
    else:
        filename = f"{ticker}_split_financial_chart.jpg"
    
    fig.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"Chart saved as {filename}")
    
    # Open the image automatically (cross-platform)
    if os.name == 'nt':  # Windows
        os.startfile(filename)
    elif os.name == 'posix':  # macOS and Linux
        import subprocess
        opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
        subprocess.call([opener, filename])

    plt.close(fig)