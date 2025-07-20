import time
import math
import requests
import certifi
from binance.client import Client
from binance.enums import *
from datetime import datetime
import ssl

# Debug: tampilkan path certifi
print('Certifi path:', certifi.where())

# Coba context SSL normal, jika gagal, pakai unverified context
try:
    ssl._create_default_https_context = ssl.create_default_context
    client = Client('5q9CdqcS10OnNHdVAE6fRyz09UNZ7wxtdlcU56FwGp5mSqMQadDDgYBrRVjwhaUc',
                    'BhhA0lAOHcixjyDlUeTxy5XJWTV0HQ4qtiO1kCNRTeaMBBd4FIFSTBjaBrBkDHIo')
    # Test ping
    client.ping()
except Exception as e:
    print('SSL error detected, trying to bypass SSL verification...')
    ssl._create_default_https_context = ssl._create_unverified_context
    try:
        client = Client('5q9CdqcS10OnNHdVAE6fRyz09UNZ7wxtdlcU56FwGp5mSqMQadDDgYBrRVjwhaUc',
                        'BhhA0lAOHcixjyDlUeTxy5XJWTV0HQ4qtiO1kCNRTeaMBBd4FIFSTBjaBrBkDHIo')
        client.ping()
        print('Bypass SSL verification: SUCCESS')
    except Exception as e2:
        print('Bypass SSL verification: FAILED')
        print('Error:', e2)
        raise SystemExit('Tidak bisa terhubung ke Binance karena masalah SSL. Coba reinstall Python dari python.org!')

# Konfigurasi strategi
symbol = 'BTCUSDT'
timeframe = '15m'
ema_fast = 12
ema_slow = 26
tp1_pct = 0.3 / 100
tp2_pct = 0.6 / 100
tp3_pct = 1.0 / 100
sl_pct = 0.4 / 100
use_vwap = True  # Aktifkan filter VWAP

# Konfigurasi trading
max_trade_amount_usdt = 3
leverage = 50
quantity_precision = 3  # Jumlah digit desimal untuk quantity

# Fungsi mengambil data klines

def get_klines(symbol, interval, limit=100):
    return client.get_klines(symbol=symbol, interval=interval, limit=limit)

# Fungsi hitung EMA

def EMA(data, period):
    k = 2 / (period + 1)
    ema = data[0]
    for price in data[1:]:
        ema = price * k + ema * (1 - k)
    return ema

# Fungsi hitung VWAP

def calculate_vwap(klines):
    cumulative_vp = 0
    cumulative_volume = 0
    for k in klines:
        high = float(k[2])
        low = float(k[3])
        close = float(k[4])
        volume = float(k[5])
        typical_price = (high + low + close) / 3
        cumulative_vp += typical_price * volume
        cumulative_volume += volume
    return cumulative_vp / cumulative_volume if cumulative_volume != 0 else 0

# Fungsi hitung harga entry dan TP/SL

def calculate_levels(entry_price):
    tp1 = entry_price * (1 + tp1_pct)
    tp2 = entry_price * (1 + tp2_pct)
    tp3 = entry_price * (1 + tp3_pct)
    sl = entry_price * (1 - sl_pct)
    return tp1, tp2, tp3, sl

# Fungsi open posisi long

def open_long():
    usdt_balance = float(client.get_asset_balance(asset='USDT')['free'])
    trade_amount = min(max_trade_amount_usdt, usdt_balance)
    qty = round((trade_amount * leverage) / current_price, quantity_precision)
    order = client.futures_create_order(
        symbol=symbol,
        side=SIDE_BUY,
        type=ORDER_TYPE_MARKET,
        quantity=qty
    )
    print(f"[LONG] Opened: {order}")
    return qty

# Fungsi open posisi short

def open_short():
    usdt_balance = float(client.get_asset_balance(asset='USDT')['free'])
    trade_amount = min(max_trade_amount_usdt, usdt_balance)
    qty = round((trade_amount * leverage) / current_price, quantity_precision)
    order = client.futures_create_order(
        symbol=symbol,
        side=SIDE_SELL,
        type=ORDER_TYPE_MARKET,
        quantity=qty
    )
    print(f"[SHORT] Opened: {order}")
    return qty

# Fungsi utama loop
position = None
entry_price = 0
qty = 0
current_price = 0

def run():
    global position, entry_price, qty, current_price
    while True:
        try:
            klines = get_klines(symbol, timeframe, limit=100)
            closes = [float(k[4]) for k in klines]
            current_price = closes[-1]

            ema_fast_val = EMA(closes[-ema_fast:], ema_fast)
            ema_slow_val = EMA(closes[-ema_slow:], ema_slow)

            vwap = calculate_vwap(klines) if use_vwap else None

            print(f"Price: {current_price}, EMA Fast: {ema_fast_val}, EMA Slow: {ema_slow_val}, VWAP: {vwap}")

            if position is None:
                # Entry Long
                if ema_fast_val > ema_slow_val and (not use_vwap or current_price > vwap):
                    qty = open_long()
                    position = 'long'
                    entry_price = current_price
                # Entry Short
                elif ema_fast_val < ema_slow_val and (not use_vwap or current_price < vwap):
                    qty = open_short()
                    position = 'short'
                    entry_price = current_price

            else:
                tp1, tp2, tp3, sl = calculate_levels(entry_price)

                # LONG Management
                if position == 'long':
                    if current_price >= tp3:
                        client.futures_create_order(symbol=symbol, side=SIDE_SELL, type=ORDER_TYPE_MARKET, quantity=qty)
                        print("[TP3] Long Closed")
                        position = None
                    elif current_price <= sl:
                        client.futures_create_order(symbol=symbol, side=SIDE_SELL, type=ORDER_TYPE_MARKET, quantity=qty)
                        print("[SL] Long Closed")
                        position = None

                # SHORT Management
                elif position == 'short':
                    if current_price <= entry_price * (1 - tp3_pct):
                        client.futures_create_order(symbol=symbol, side=SIDE_BUY, type=ORDER_TYPE_MARKET, quantity=qty)
                        print("[TP3] Short Closed")
                        position = None
                    elif current_price >= entry_price * (1 + sl_pct):
                        client.futures_create_order(symbol=symbol, side=SIDE_BUY, type=ORDER_TYPE_MARKET, quantity=qty)
                        print("[SL] Short Closed")
                        position = None

        except Exception as e:
            print(f"Error: {e}")

        time.sleep(10)

# Jalankan bot
run()
