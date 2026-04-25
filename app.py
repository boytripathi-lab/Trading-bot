from flask import Flask, request, jsonify
import os
import logging
import requests
import hashlib
import hmac
import time
import json
from datetime import datetime, date
import math

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DELTA_API_KEY = os.environ.get("DELTA_API_KEY", "")
DELTA_API_SECRET = os.environ.get("DELTA_API_SECRET", "")
DHAN_CLIENT_ID = os.environ.get("DHAN_CLIENT_ID", "")
DHAN_ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN", "")
WH_SECRET = os.environ.get("WEBHOOK_SECRET", "mysecret123")

DELTA_BASE_URL = "https://api.india.delta.exchange"
DHAN_BASE_URL = "https://api.dhan.co"

DELTA_SYMBOLS = {
    "BTCUSD": {"product_id": 27, "size": 5},
    "ETHUSD": {"product_id": 3, "size": 5},
    "SOLUSD": {"product_id": 1320, "size": 5}
}

def get_delta_headers(method, path, body=""):
    timestamp = str(int(time.time()))
    message = method + timestamp + path + body
    signature = hmac.new(
        DELTA_API_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return {
        "api-key": DELTA_API_KEY,
        "timestamp": timestamp,
        "signature": signature,
        "Content-Type": "application/json"
    }

def set_delta_leverage(product_id, leverage=25):
    path = "/v2/products/leverage"
    url = DELTA_BASE_URL + path
    data = {"product_id": product_id, "leverage": str(leverage)}
    body = json.dumps(data)
    headers = get_delta_headers("POST", path, body)
    requests.post(url, data=body, headers=headers)

def place_delta_order(symbol, side, sl=None, tp=None):
    config = DELTA_SYMBOLS.get(symbol, {"product_id": 27, "size": 5})
    set_delta_leverage(config["product_id"], 25)
    path = "/v2/orders"
    url = DELTA_BASE_URL + path
    data = {
        "product_symbol": symbol,
        "side": side,
        "order_type": "market_order",
        "size": config["size"]
    }
    if sl and tp:
        data["bracket_order"] = {
            "stop_loss_price": str(sl),
            "take_profit_price": str(tp)
        }
    body = json.dumps(data)
    headers = get_delta_headers("POST", path, body)
    response = requests.post(url, data=body, headers=headers)
    result = response.json()
    logger.info("Delta Order: " + str(result))
    return result

def get_itm_strike(nifty_price, action):
    strike_gap = 50
    if action == "buy":
        atm = math.floor(nifty_price / strike_gap) * strike_gap
        itm_strike = atm - 100
        option_type = "CE"
    else:
        atm = math.ceil(nifty_price / strike_gap) * strike_gap
        itm_strike = atm + 100
        option_type = "PE"
    return itm_strike, option_type

def get_nifty_price():
    try:
        url = DHAN_BASE_URL + "/v2/marketfeed/ltp"
        headers = {
            "access-token": DHAN_ACCESS_TOKEN,
            "Content-Type": "application/json"
        }
        data = {
            "NSE_EQ": ["13"]
        }
        response = requests.post(url, json=data, headers=headers)
        result = response.json()
        price = result["data"]["NSE_EQ"]["13"]["ltp"]
        return float(price)
    except Exception as e:
        logger.error("Price fetch error: " + str(e))
        return 23900.0

def place_dhan_option_order(action, quantity=75):
    try:
        nifty_price = get_nifty_price()
        itm_strike, option_type = get_itm_strike(nifty_price, action)
        today = date.today()
        if today.month == 12:
            expiry_month = "JAN"
            expiry_year = str(today.year + 1)[2:]
        else:
            months = ["JAN","FEB","MAR","APR","MAY","JUN",
                     "JUL","AUG","SEP","OCT","NOV","DEC"]
            expiry_month = months[today.month]
            expiry_year = str(today.year)[2:]
        trading_symbol = f"NIFTY{expiry_year}{expiry_month}{itm_strike}{option_type}"
        logger.info("Trading symbol: " + trading_symbol)
        url = DHAN_BASE_URL + "/v2/orders"
        transaction_type = "BUY"
        data = {
            "dhanClientId": DHAN_CLIENT_ID,
            "transactionType": transaction_type,
            "exchangeSegment": "NSE_FNO",
            "productType": "INTRADAY",
            "orderType": "MARKET",
            "validity": "DAY",
            "tradingSymbol": trading_symbol,
            "quantity": quantity,
            "price": 0
        }
        headers = {
            "access-token": DHAN_ACCESS_TOKEN,
            "Content-Type": "application/json"
        }
        response = requests.post(url, json=data, headers=headers)
        result = response.json()
        logger.info("Dhan Option Order: " + str(result))
        return result
    except Exception as e:
        logger.error("Dhan order error: " + str(e))
        return {"error": str(e)}

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    if data.get("secret") != WH_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    action = data.get("action", "").lower()
    symbol = data.get("symbol", "BTCUSD").upper()
    quantity = int(data.get("quantity", 75))
    sl = data.get("sl", None)
    tp = data.get("tp", None)
    if action not in ["buy", "sell"]:
        return jsonify({"error": "Invalid action"}), 400
    if symbol in DELTA_SYMBOLS:
        result = place_delta_order(symbol, action, sl, tp)
        exchange = "Delta"
    elif symbol == "NIFTY":
        result = place_dhan_option_order(action, quantity)
        exchange = "Dhan Options"
    else:
        return jsonify({"error": "Symbol not supported"}), 400
    return jsonify({
        "status": "success",
        "exchange": exchange,
        "action": action,
        "symbol": symbol,
        "result": result,
        "time": datetime.now().isoformat()
    }), 200

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "exchanges": ["Delta Exchange", "Dhan Options"],
        "crypto": ["BTCUSD", "ETHUSD", "SOLUSD"],
        "options": ["NIFTY Monthly ITM"]
    })

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
