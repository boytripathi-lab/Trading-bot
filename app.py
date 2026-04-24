from flask import Flask, request, jsonify
from binance.client import Client
from binance.enums import *
import os
import logging
from datetime import datetime

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_KEY    = os.environ.get("BINANCE_API_KEY", "")
API_SECRET = os.environ.get("BINANCE_API_SECRET", "")
WH_SECRET  = os.environ.get("WEBHOOK_SECRET", "mysecret123")
TESTNET    = os.environ.get("TESTNET", "true").lower() == "true"

if TESTNET:
    client = Client(API_KEY, API_SECRET, testnet=True)
else:
    client = Client(API_KEY, API_SECRET)

def place_order(symbol, side, quantity):
    order_side = SIDE_BUY if side.lower() == "buy" else SIDE_SELL
    order = client.create_order(
        symbol=symbol.upper(),
        side=order_side,
        type=ORDER_TYPE_MARKET,
        quantity=quantity
    )
    logger.info(f"Order placed: {side} {quantity} {symbol}")
    return order

def get_balance(asset="USDT"):
    balance = client.get_asset_balance(asset=asset)
    return float(balance['free'])

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    if data.get("secret") != WH_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    action = data.get("action", "").lower()
    symbol = data.get("symbol", "BTCUSDT").upper()
    qty    = data.get("qty", "0.001")
    if action not in ["buy", "sell"]:
        return jsonify({"error": "Invalid action"}), 400
    order = place_order(symbol, action, qty)
    return jsonify({
        "status": "success",
        "action": action,
        "symbol": symbol,
        "qty": qty,
        "order_id": order.get("orderId"),
        "time": datetime.now().isoformat()
    }), 200

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "running", "mode": "TESTNET" if TESTNET else "LIVE"})

@app.route("/balance", methods=["GET"])
def balance():
    usdt = get_balance("USDT")
    btc  = get_balance("BTC")
    return jsonify({"USDT": usdt, "BTC": btc})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port​​​​​​​​​​​​​​​​
