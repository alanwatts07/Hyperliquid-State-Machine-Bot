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
DATA_FILE = "ltc_price_data.json"
SIGNAL_FILE = "trade_signals.json"
COIN_TO_TRACK = "LTC"
APP_REFRESH_SECONDS = 5
# NEW: ATR Configuration for Stop Loss
ATR_PERIOD = 14
ATR_MULTIPLIER = 1.5 # Common values are 1.5, 2.0, or 2.5

# --- Fibonacci Calculator Class ---
# Integrated directly into the app for simplicity
class FibonacciCalculator:
    def __init__(self, config=None):
        # Using a simple dict for config instead of a separate file
        self.config = config if config is not None else {
            'trading': {
                'wma_fib_0_offset_pct': 0.0,
                'fib_entry_offset_pct': 0.005, # 0.1% below wma_fib_0 for entry
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
app.layout = html.Div(style={
    'backgroundColor': '#111111',
    'color': '#FFFFFF',
    'fontFamily': 'sans-serif',
    'height': '100vh',
    'display': 'flex',
    'flexDirection': 'column'
}, children=[
    # NEW: Expanded state to include position and stop-loss tracking
    dcc.Store(id='trade-state-storage', data={
        'trigger_on': False,
        'in_position': False,
        'entry_price': None,
        'stop_loss_level': None,
        'stop_loss_hit': False # To display a message for one tick
    }),
    
    html.H1(f"{COIN_TO_TRACK} - 5-Minute Bottomfeeder Chart", style={'textAlign': 'center', 'padding': '20px'}),
    html.Div("Live data from [UNDISCLOSED] API with Fibonacci Levels", style={'textAlign': 'center', 'color': '#BBBBBB'}),
    
    dcc.Graph(id='live-candlestick-chart', style={'flex-grow': '1'}),
    
    html.Div(id='indicator-display', style={'textAlign': 'center', 'padding': '20px', 'fontSize': '18px'}),
    dcc.Interval(id='interval-component', interval=APP_REFRESH_SECONDS * 1000, n_intervals=0)
])

# --- Callback to Update the Chart and Indicators ---
@app.callback(
    [Output('live-candlestick-chart', 'figure'),
     Output('indicator-display', 'children'),
     Output('trade-state-storage', 'data')],
    Input('interval-component', 'n_intervals'),
    State('trade-state-storage', 'data')
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

        if len(ohlc_df) < 200: # Check for enough data for 200 EMA
            # You can decide how to handle this, for now, we'll proceed but EMA will be mostly NaN
            pass 

        # --- Indicator Calculations ---
        fib_calculator = FibonacciCalculator()
        df_with_fibs = fib_calculator.calculate_fib_levels(ohlc_df)
        
        fib_entry_offset = fib_calculator.config['trading']['fib_entry_offset_pct']
        df_with_fibs['fib_entry'] = df_with_fibs['wma_fib_0'] * (1 - fib_entry_offset)

        # ATR Calculation
        high_low = df_with_fibs['high'] - df_with_fibs['low']
        high_prev_close = np.abs(df_with_fibs['high'] - df_with_fibs['close'].shift())
        low_prev_close = np.abs(df_with_fibs['low'] - df_with_fibs['close'].shift())
        tr = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
        df_with_fibs['atr'] = tr.rolling(window=ATR_PERIOD).mean()
        
        # NEW: 200 EMA Calculation
        df_with_fibs['ema_200'] = df_with_fibs['close'].ewm(span=200, adjust=False).mean()

        # --- State Machine Logic ---
        latest_close = df_with_fibs['close'].iloc[-1]
        latest_wma_0 = df_with_fibs['wma_fib_0'].iloc[-1]
        latest_fib_entry = df_with_fibs['fib_entry'].iloc[-1]
        latest_atr = df_with_fibs['atr'].iloc[-1]
        
        # Unpack state
        trigger_on = trade_state.get('trigger_on', False)
        in_position = trade_state.get('in_position', False)
        entry_price = trade_state.get('entry_price')
        stop_loss_level = trade_state.get('stop_loss_level')
        
        # Local flags for this update cycle
        buy_signal = False
        stop_loss_hit = False

        reset_threshold = latest_wma_0 * (1 + fib_calculator.config['trading']['reset_pct_above_fib_0'])

        # --- Main State Evaluation ---
        if in_position:
            if stop_loss_level and latest_close < stop_loss_level:
                stop_loss_hit = True
                in_position = False 
                trigger_on = False
            elif latest_close > reset_threshold:
                in_position = False 
                trigger_on = False
        else:
            if latest_close > reset_threshold:
                trigger_on = False
            elif latest_close < latest_fib_entry:
                trigger_on = True
            
            if trigger_on and latest_close > latest_wma_0:
                buy_signal = True
                trigger_on = False
                
                in_position = True
                entry_price = latest_close
                if not pd.isnull(latest_atr):
                    stop_loss_level = entry_price - (latest_atr * ATR_MULTIPLIER)
                else:
                    stop_loss_level = None

        # --- Charting ---
        fig = go.Figure(data=[go.Candlestick(
            x=df_with_fibs.index, open=df_with_fibs['open'], high=df_with_fibs['high'],
            low=df_with_fibs['low'], close=df_with_fibs['close'], name='Candles'
        )])

        fig.add_trace(go.Scatter(x=df_with_fibs.index, y=df_with_fibs['wma_fib_0'], mode='lines', name='WMA Fib 0 (Buy Zone Upper)', line=dict(color='lime', width=1)))
        fig.add_trace(go.Scatter(x=df_with_fibs.index, y=df_with_fibs['fib_entry'], mode='lines', name='Fib Entry (Buy Zone Lower)', line=dict(color='cyan', width=1, dash='dash')))
        fig.add_trace(go.Scatter(x=df_with_fibs.index, y=df_with_fibs['wma_fib_50'], mode='lines', name='WMA Fib 50 (Target)', line=dict(color='red', width=1)))
        
        # NEW: Add 200 EMA trace to the plot
        fig.add_trace(go.Scatter(x=df_with_fibs.index, y=df_with_fibs['ema_200'], mode='lines', name='200 EMA', line=dict(color='yellow', width=2)))

        if in_position and stop_loss_level:
            fig.add_hline(
                y=stop_loss_level, line_dash="dot", line_color="orange",
                annotation_text=f"Stop Loss {stop_loss_level:.2f}",
                annotation_position="bottom right", annotation_font=dict(color="orange")
            )

        fig.update_layout(
            title_text=f'Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            yaxis_title=f'Price (USD)', xaxis_rangeslider_visible=False, template='plotly_dark',
            autosize=True
        )
        
        # --- Update Display and Final State ---
        # Build Line 1 (Price, Zone, ATR)
        indicator_text = [
            html.Span(f"Latest Price: ${latest_close:,.2f} | ", style={'color': '#FFFFFF'}),
            html.Span(f"Buy Zone: ${latest_fib_entry:,.2f}", style={'color': 'cyan'}),
            html.Span(f" - ${latest_wma_0:,.2f}", style={'color': 'lime'}),
            html.Span(f" | ATR: {latest_atr:,.3f}", style={'color': '#BBBBBB'}),
            html.Br()
        ]

        # Build Line 2 (The Status Line)
        status_line = [html.Span("STATUS: ", style={'fontWeight': 'bold'})]

        if stop_loss_hit:
            status_line.append(html.Span("STOP LOSS HIT", style={'fontWeight': 'bold', 'color': 'red'}))
        elif in_position:
            status_line.append(html.Span(f"In Position: True", style={'fontWeight': 'bold', 'color': 'orange'}))
            if entry_price and stop_loss_level:
                status_line.append(html.Span(f" | Entry: ${entry_price:,.2f} | Stop: ${stop_loss_level:,.2f}", style={'color': 'orange'}))
        else:
            trigger_color = 'lime' if trigger_on else '#BBBBBB'
            buy_color = 'lime' if buy_signal else '#BBBBBB'
            
            status_line.append(html.Span(f"In Position: False", style={'color': '#BBBBBB', 'marginRight': '15px'}))
            status_line.append(html.Span(f"| Trigger Armed: {trigger_on}", style={'color': trigger_color, 'marginRight': '15px'}))
            status_line.append(html.Span(f"| BUY SIGNAL: {buy_signal}", style={'color': buy_color, 'fontWeight': 'bold' if buy_signal else 'normal'}))

        indicator_text.extend(status_line)

        new_state = {
            'trigger_on': trigger_on,
            'in_position': in_position,
            'entry_price': entry_price if in_position else None,
            'stop_loss_level': stop_loss_level if in_position else None,
            'stop_loss_hit': stop_loss_hit
        }
        
        return fig, indicator_text, new_state

    except (FileNotFoundError, json.JSONDecodeError, ValueError, IndexError) as e:
        fig = go.Figure().update_layout(title_text=f"Waiting for data... ({e})", template='plotly_dark', autosize=True)
        return fig, f"Error: {e}", {'trigger_on': False, 'in_position': False, 'entry_price': None, 'stop_loss_level': None, 'stop_loss_hit': False}

if __name__ == '__main__':
    app.run(debug=True)