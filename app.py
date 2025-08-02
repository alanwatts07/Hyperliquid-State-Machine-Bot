# Hyperliquid Candlestick Dashboard (app.py)
#
# This Dash application reads 1-minute price data from 'price_data.json',
# aggregates it into 5-minute candlestick data, calculates Fibonacci levels,
# and displays the results. It also saves the latest signal data to 'trade_signals.json'.
#
# Prerequisites:
# pip install dash pandas plotly numpy
#
# To Run:
# 1. Make sure 'collector.py' is running in a separate terminal.
# 2. Save this file as 'app.py'.
# 3. Run from your terminal: python app.py
# 4. Open your web browser to http://127.0.0.1:8050/

import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import pandas as pd
import json
from datetime import datetime
import numpy as np

# --- Configuration ---
DATA_FILE = "price_data.json"
SIGNAL_FILE = "trade_signals.json"
COIN_TO_TRACK = "SOL"
APP_REFRESH_SECONDS = 5

# --- Fibonacci Calculator Class ---
# Integrated directly into the app for simplicity
class FibonacciCalculator:
    def __init__(self, config=None):
        # Using a simple dict for config instead of a separate file
        self.config = config if config is not None else {
            'trading': {
                'wma_fib_0_offset_pct': 0.0,
                'fib_entry_offset_pct': 0.001, # 0.1% below wma_fib_0 for entry
                'reset_pct_above_fib_0': 0.005 # NEW: 0.5% above fib_0 to reset state
            }
        }

    def calculate_fib_levels(self, df):
        if len(df) < 66:
            print(f"DEBUG(FibCalc): Not enough data for WMA fibs ({len(df)} < 66).")
            df['wma_fib_0'] = np.nan
            df['wma_fib_50'] = np.nan
            return df
        
        df_copy = df.copy()
        
        df_copy['highest_high'] = df_copy['high'].rolling(window=42).max()
        df_copy['lowest_low'] = df_copy['low'].rolling(window=42).min()
        
        diff = df_copy['highest_high'] - df_copy['lowest_low']
        df_copy['fib_0'] = df_copy['lowest_low']
        df_copy['fib_50'] = df_copy['highest_high'] - (diff * 0.5)
        
        df_copy['wma_fib_0'] = df_copy['fib_0'].rolling(window=24).mean()
        df_copy['wma_fib_50'] = df_copy['fib_50'].rolling(window=24).mean()

        offset_pct = self.config['trading'].get('wma_fib_0_offset_pct', 0.0)
        if offset_pct > 0.0:
            df_copy['wma_fib_0'] = df_copy['wma_fib_0'] * (1 - offset_pct)
            
        return df_copy

# --- Dash App Initialization ---
app = dash.Dash(__name__)
app.title = f"{COIN_TO_TRACK} Price Dashboard"

# --- App Layout ---
app.layout = html.Div(style={'backgroundColor': '#111111', 'color': '#FFFFFF', 'fontFamily': 'sans-serif'}, children=[
    # NEW: Add a dcc.Store component to hold the state
    dcc.Store(id='trade-state-storage', data={'trigger_on': False, 'buy_signal': False}),
    
    html.H1(f"{COIN_TO_TRACK} - 5-Minute Candlestick Chart", style={'textAlign': 'center', 'padding': '20px'}),
    html.Div("Live data from Hyperliquid API with Fibonacci Levels", style={'textAlign': 'center', 'color': '#BBBBBB'}),
    dcc.Graph(id='live-candlestick-chart'),
    html.Div(id='indicator-display', style={'textAlign': 'center', 'padding': '20px', 'fontSize': '18px'}),
    dcc.Interval(id='interval-component', interval=APP_REFRESH_SECONDS * 1000, n_intervals=0)
])

# --- Callback to Update the Chart and Indicators ---
@app.callback(
    [Output('live-candlestick-chart', 'figure'),
     Output('indicator-display', 'children'),
     Output('trade-state-storage', 'data')], # Add output for the state store
    Input('interval-component', 'n_intervals'),
    State('trade-state-storage', 'data') # Get the current state as input
)
def update_chart_and_indicators(n, trade_state):
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        
        if not data: raise ValueError("No data in file")

        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)

        ohlc_df = df['price'].resample('5T').ohlc()
        ohlc_df.dropna(inplace=True)

        if len(ohlc_df) < 2: raise ValueError("Not enough data to form candles.")

        fib_calculator = FibonacciCalculator()
        df_with_fibs = fib_calculator.calculate_fib_levels(ohlc_df)
        
        fib_entry_offset = fib_calculator.config['trading']['fib_entry_offset_pct']
        df_with_fibs['fib_entry'] = df_with_fibs['wma_fib_0'] * (1 - fib_entry_offset)

        # --- State Machine Logic ---
        latest_close = df_with_fibs['close'].iloc[-1]
        latest_wma_0 = df_with_fibs['wma_fib_0'].iloc[-1]
        latest_fib_entry = df_with_fibs['fib_entry'].iloc[-1]
        
        trigger_on = trade_state['trigger_on']
        buy_signal = trade_state['buy_signal']

        # 1. Check Reset Condition
        reset_threshold = latest_wma_0 * (1 + fib_calculator.config['trading']['reset_pct_above_fib_0'])
        if latest_close > reset_threshold:
            trigger_on = False
            buy_signal = False
        else:
            # 2. Check Arming Condition (Trigger)
            if latest_close < latest_fib_entry:
                trigger_on = True
                buy_signal = False # Can't have a buy signal if we just re-armed
            
            # 3. Check Buy Signal Condition
            if trigger_on and latest_close > latest_wma_0:
                buy_signal = True
                trigger_on = False # Consume the trigger once the signal is fired

        # --- Charting ---
        fig = go.Figure(data=[go.Candlestick(
            x=df_with_fibs.index, open=df_with_fibs['open'], high=df_with_fibs['high'],
            low=df_with_fibs['low'], close=df_with_fibs['close'], name='Candles'
        )])

        fig.add_trace(go.Scatter(x=df_with_fibs.index, y=df_with_fibs['wma_fib_0'], mode='lines', name='WMA Fib 0 (Buy Zone Upper)', line=dict(color='lime', width=1)))
        fig.add_trace(go.Scatter(x=df_with_fibs.index, y=df_with_fibs['fib_entry'], mode='lines', name='Fib Entry (Buy Zone Lower)', line=dict(color='cyan', width=1, dash='dash')))
        fig.add_trace(go.Scatter(x=df_with_fibs.index, y=df_with_fibs['wma_fib_50'], mode='lines', name='WMA Fib 50 (Target)', line=dict(color='red', width=1)))

        fig.update_layout(
            title_text=f'Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            yaxis_title=f'Price (USD)', xaxis_rangeslider_visible=False, template='plotly_dark'
        )
        
        # --- Save Signals and Update Display ---
        signal_data = {
            "timestamp": datetime.now().isoformat(),
            "coin": COIN_TO_TRACK,
            "latest_price": latest_close,
            "fib_entry_level": latest_fib_entry if not pd.isnull(latest_fib_entry) else None,
            "fib_0_level": latest_wma_0 if not pd.isnull(latest_wma_0) else None,
            "fib_50_level": df_with_fibs['wma_fib_50'].iloc[-1],
            "state": {
                "trigger_on": trigger_on,
                "buy_signal": buy_signal
            }
        }
        with open(SIGNAL_FILE, 'w') as f:
            json.dump(signal_data, f, indent=4)

        # Update text display
        trigger_color = 'lime' if trigger_on else '#BBBBBB'
        buy_color = 'lime' if buy_signal else '#BBBBBB'
        
        indicator_text = [
            html.Span(f"Latest Price: ${latest_close:,.2f} | ", style={'color': '#FFFFFF'}),
            html.Span(f"Buy Zone: ${latest_fib_entry:,.2f}", style={'color': 'cyan'}),
            html.Span(f" - ${latest_wma_0:,.2f}", style={'color': 'lime'}),
            html.Br(),
            html.Span("STATUS: ", style={'fontWeight': 'bold'}),
            html.Span(f"Trigger Armed: {trigger_on}", style={'color': trigger_color, 'marginRight': '15px'}),
            html.Span(f"BUY SIGNAL: {buy_signal}", style={'color': buy_color, 'fontWeight': 'bold' if buy_signal else 'normal'})
        ]
        
        new_state = {'trigger_on': trigger_on, 'buy_signal': buy_signal}
        return fig, indicator_text, new_state

    except (FileNotFoundError, json.JSONDecodeError, ValueError, IndexError) as e:
        fig = go.Figure().update_layout(title_text=f"Waiting for data... ({e})", template='plotly_dark')
        # Return default state on error
        return fig, f"Error: {e}", {'trigger_on': False, 'buy_signal': False}

if __name__ == '__main__':
    app.run(debug=True)
