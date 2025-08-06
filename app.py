# Hyperliquid Candlestick Dashboard (app.py)
#
# This Dash application reads price data, calculates signals, and determines
# its initial position state by reading a trade log file on startup.
# It now displays the PnL %, plots individual trades, shows the average entry price,
# and passes the ATR value to the signal file.
# NOTE: This version has had the ATR-based stop-loss functionality removed.
#
# Prerequisites:
# pip install dash pandas plotly numpy
#
# To Run:
# 1. Ensure your trade logs are up-to-date.
# 2. Make sure 'collector.py' is running in a separate terminal.
# 3. Save this file as 'app.py'.
# 4. Run from your terminal: python app.py

import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import pandas as pd
import json
import os
from datetime import datetime
import numpy as np

# --- Configuration ---
DATA_FILE = "ltc_price_data.json"
SIGNAL_FILE = "trade_signals.json"
LOG_FILE = "trade_log.json"
COIN_TO_TRACK = "LTC"
APP_REFRESH_SECONDS = 5
ATR_PERIOD = 14
# ATR_MULTIPLIER has been removed as it was only for the stop-loss.

# --- Helper function to read trade logs ---
def read_trade_logs(log_file_path):
    """Safely reads and returns the contents of the trade log file."""
    try:
        if not os.path.exists(log_file_path):
            return []
        with open(log_file_path, 'r') as f:
            logs = json.load(f)
        return logs if isinstance(logs, list) else []
    except (json.JSONDecodeError, Exception):
        return []

# --- Function to Read Logs and Determine Initial State ---
def get_initial_trade_state(log_file_path):
    """Reads the trade log to determine the current position state on startup."""
    default_state = {'in_position': False, 'entry_price': None, 'position_size': 0.0}
    logs = read_trade_logs(log_file_path)
    if not logs:
        print(f"[*] Log file '{log_file_path}' not found or empty. Starting with no position.")
        return default_state

    try:
        last_sell_index = -1
        for i in range(len(logs) - 1, -1, -1):
            if logs[i].get('trade_type') == 'sell':
                last_sell_index = i
                break
        
        trades_since_last_sell = logs[last_sell_index + 1:]
        buys_in_cycle = [t for t in trades_since_last_sell if t.get('trade_type') == 'buy' or 'trade_type' not in t]

        if not buys_in_cycle:
            return default_state
        else:
            total_size = sum(float(b.get('calculated_asset_size', 0)) for b in buys_in_cycle)
            # For simplicity, using the first buy price as the entry for the cycle. A weighted average is also an option.
            first_buy_price = float(buys_in_cycle[0]['exchange_response']['response']['data']['statuses'][0]['filled']['avgPx'])
            print(f"✅ STATE RECOVERY: Found active position. Size: {total_size}, Entry: {first_buy_price}")
            return {'in_position': True, 'entry_price': first_buy_price, 'position_size': total_size}
    except Exception as e:
        print(f"❌ Error processing log file for initial state: {e}")
        return default_state

# --- Fibonacci Calculator Class ---
class FibonacciCalculator:
    def __init__(self, config=None):
        self.config = config or {'trading': {'fib_entry_offset_pct': 0.005, 'reset_pct_above_fib_0': 0.005}}

    def calculate_fib_levels(self, df):
        if len(df) < 66:
            df['wma_fib_0'], df['wma_fib_50'] = np.nan, np.nan
            return df
        df_copy = df.copy()
        df_copy['highest_high'] = df_copy['high'].rolling(window=42).max()
        df_copy['lowest_low'] = df_copy['low'].rolling(window=42).min()
        df_copy['wma_fib_0'] = df_copy['lowest_low'].rolling(window=24).mean()
        df_copy['wma_fib_50'] = (df_copy['highest_high'] - ((df_copy['highest_high'] - df_copy['lowest_low']) * 0.5)).rolling(window=24).mean()
        return df_copy

# --- Dash App Initialization ---
app = dash.Dash(__name__)
app.title = f"{COIN_TO_TRACK} Price Dashboard"
initial_state = get_initial_trade_state(LOG_FILE)

# --- App Layout ---
app.layout = html.Div(style={'backgroundColor': '#111111', 'color': '#FFFFFF', 'fontFamily': 'sans-serif', 'height': '100vh', 'display': 'flex', 'flexDirection': 'column'}, children=[
    dcc.Store(id='trade-state-storage', data={'trigger_on': False, 'in_position': initial_state['in_position'], 'entry_price': initial_state['entry_price'], 'position_size': initial_state['position_size']}),
    html.H1(f"{COIN_TO_TRACK} - 5-Minute Bottomfeeder Bot", style={'textAlign': 'center', 'padding': '20px'}),
    dcc.Graph(id='live-candlestick-chart', style={'flex-grow': '1'}),
    html.Div(id='indicator-display', style={'textAlign': 'center', 'padding': '20px', 'fontSize': '18px'}),
    dcc.Interval(id='interval-component', interval=APP_REFRESH_SECONDS * 1000, n_intervals=0)
])

# --- Main Callback ---
@app.callback(
    [Output('live-candlestick-chart', 'figure'), Output('indicator-display', 'children'), Output('trade-state-storage', 'data')],
    Input('interval-component', 'n_intervals'),
    [State('trade-state-storage', 'data'), State('live-candlestick-chart', 'relayoutData')]
)
def update_chart_and_indicators(n, trade_state, relayout_data):
    try:
        with open(DATA_FILE, 'r') as f: data = json.load(f)
        if not data: raise ValueError("No data in file")

        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        ohlc_df = df['price'].resample('5T').ohlc()
        ohlc_df.dropna(inplace=True)

        fib_calculator = FibonacciCalculator()
        df_with_fibs = fib_calculator.calculate_fib_levels(ohlc_df)
        df_with_fibs['fib_entry'] = df_with_fibs['wma_fib_0'] * (1 - fib_calculator.config['trading']['fib_entry_offset_pct'])
        
        # ATR calculation is kept as it's passed to the signal file, but not used for a stop-loss here.
        high_low = df_with_fibs['high'] - df_with_fibs['low']
        high_prev_close = np.abs(df_with_fibs['high'] - df_with_fibs['close'].shift())
        low_prev_close = np.abs(df_with_fibs['low'] - df_with_fibs['close'].shift())
        tr = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
        df_with_fibs['atr'] = tr.rolling(window=ATR_PERIOD).mean()
        
        latest_close, latest_wma_0, latest_fib_entry, latest_atr, latest_wma_50 = [df_with_fibs[col].iloc[-1] for col in ['close', 'wma_fib_0', 'fib_entry', 'atr', 'wma_fib_50']]
        
        trigger_on, in_position, entry_price, position_size = [trade_state.get(k) for k in ['trigger_on', 'in_position', 'entry_price', 'position_size']]
        buy_signal = False
        reset_threshold = latest_wma_0 * (1 + fib_calculator.config['trading']['reset_pct_above_fib_0'])

        # --- Simplified Trading Logic (No Stop-Loss) ---
        if not in_position:
            # Logic to arm or disarm the buy trigger
            if latest_close > reset_threshold:
                trigger_on = False
            elif latest_close < latest_fib_entry:
                trigger_on = True
            
            # Check for a buy signal if the trigger is armed
            if trigger_on and latest_close > latest_wma_0:
                buy_signal = True
                in_position = True
                entry_price = latest_close
                # Note: No stop-loss is set upon entry.

        # --- Charting Logic ---
        fig = go.Figure(data=[go.Candlestick(x=df_with_fibs.index, open=df_with_fibs['open'], high=df_with_fibs['high'], low=df_with_fibs['low'], close=df_with_fibs['close'], name='Candles')])
        fig.add_trace(go.Scatter(x=df_with_fibs.index, y=df_with_fibs['wma_fib_0'], mode='lines', name='WMA Fib 0', line=dict(color='lime', width=1)))
        fig.add_trace(go.Scatter(x=df_with_fibs.index, y=df_with_fibs['fib_entry'], mode='lines', name='Fib Entry', line=dict(color='cyan', width=1, dash='dash')))
        fig.add_trace(go.Scatter(x=df_with_fibs.index, y=df_with_fibs['wma_fib_50'], mode='lines', name='WMA Fib 50', line=dict(color='red', width=1)))
        
        if in_position:
            all_logs = read_trade_logs(LOG_FILE)
            last_sell_index = -1
            for i in range(len(all_logs) - 1, -1, -1):
                if all_logs[i].get('trade_type') == 'sell':
                    last_sell_index = i
                    break
            current_buys = [t for t in all_logs[last_sell_index + 1:] if t.get('trade_type') == 'buy' or 'trade_type' not in t]
            
            buy_times = [pd.to_datetime(trade['log_timestamp']) for trade in current_buys]
            buy_prices = [float(trade['exchange_response']['response']['data']['statuses'][0]['filled']['avgPx']) for trade in current_buys]

            fig.add_trace(go.Scatter(x=buy_times, y=buy_prices, mode='markers', name='Buy Trades', marker=dict(color='lime', size=10, symbol='triangle-up')))
            
            if entry_price:
                fig.add_hline(y=entry_price, line_dash="dash", line_color="purple", annotation_text=f"Avg Entry {entry_price:.2f}", annotation_position="bottom left", annotation_font=dict(color="purple"))
        
        # Removed the plotting for the stop-loss level.
        
        fig.update_layout(title_text=f'Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', yaxis_title='Price (USD)', xaxis_rangeslider_visible=False, template='plotly_dark')
        if relayout_data and 'xaxis.range[0]' in relayout_data: fig.update_layout(xaxis_range=[relayout_data['xaxis.range[0]'], relayout_data['xaxis.range[1]']])
        if relayout_data and 'yaxis.range[0]' in relayout_data: fig.update_layout(yaxis_range=[relayout_data['yaxis.range[0]'], relayout_data['yaxis.range[1]']])

        # --- Display Logic ---
        indicator_text = [html.Span(f"Latest Price: ${latest_close:,.2f} | Buy Zone: "), html.Span(f"${latest_fib_entry:,.2f}", style={'color': 'cyan'}), html.Span(f" - ${latest_wma_0:,.2f}", style={'color': 'lime'}), html.Br()]
        status_line = [html.Span("STATUS: ", style={'fontWeight': 'bold'})]
        
        if in_position:
            status_line.append(html.Span("In Position", style={'fontWeight': 'bold', 'color': 'orange'}))
            status_line.append(html.Span(f" | Size: {position_size:.4f} {COIN_TO_TRACK}", style={'color': 'orange'}))
            if entry_price:
                status_line.append(html.Span(f" | Entry: ${entry_price:,.2f}", style={'color': 'orange'}))
                pnl_pct = ((latest_close - entry_price) / entry_price) * 100
                pnl_color = 'lime' if pnl_pct >= 0 else 'red'
                pnl_sign = '+' if pnl_pct >= 0 else ''
                status_line.append(html.Span(f" | PnL: {pnl_sign}{pnl_pct:.2f}%", style={'color': pnl_color, 'fontWeight': 'bold'}))
            # Removed display of stop-loss level.
        else:
            status_line.append(html.Span(f"Trigger Armed: {trigger_on}", style={'color': 'lime' if trigger_on else '#BBBBBB', 'marginRight': '15px'}))
            status_line.append(html.Span(f"| BUY SIGNAL: {buy_signal}", style={'color': 'lime' if buy_signal else '#BBBBBB', 'fontWeight': 'bold' if buy_signal else 'normal'}))
        indicator_text.extend(status_line)

        # --- State Saving ---
        new_state = {'trigger_on': trigger_on, 'in_position': in_position, 'entry_price': entry_price, 'position_size': position_size}
        
        # --- MODIFIED: Added 'atr' to the signal data ---
        signal_data = {
            "timestamp": datetime.now().isoformat(),
            "coin": COIN_TO_TRACK,
            "latest_price": latest_close,
            "fib_entry_level": latest_fib_entry,
            "fib_0_level": latest_wma_0,
            "fib_50_level": latest_wma_50,
            "atr": latest_atr, # <-- ATR is still included for external use
            "state": {
                "trigger_on": trigger_on,
                "buy_signal": buy_signal
            }
        }
        with open(SIGNAL_FILE, 'w') as f: json.dump(signal_data, f, indent=4)
        return fig, indicator_text, new_state

    except (FileNotFoundError, json.JSONDecodeError, ValueError, IndexError) as e:
        error_data = {"timestamp": datetime.now().isoformat(), "coin": COIN_TO_TRACK, "error": str(e), "state": {"trigger_on": False, "buy_signal": False}}
        with open(SIGNAL_FILE, 'w') as f: json.dump(error_data, f, indent=4)
        fig = go.Figure().update_layout(title_text=f"Waiting for data... ({e})", template='plotly_dark')
        return fig, f"Error: {e}", trade_state

if __name__ == '__main__':
    app.run(debug=True)