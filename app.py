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

DELTA_API_KEY     = os.environ.get("DELTA_API_KEY", "")
DELTA_API_SECRET  = os.environ.get("DELTA_API_SECRET", "")
DHAN_CLIENT_ID    = os.environ.get("DHAN_CLIENT_ID", "")
DHAN_ACCESS_TOKEN = os.environ.get("DHAN_ACCESS_TOKEN", "")
WH_SECRET         = os.environ.get("WEBHOOK_SECRET", "mysecret123")

DELTA_BASE_URL = "https://api.india.delta.exchange"
DHAN_BASE_URL  = "https://api.dhan.co"

DELTA_SYMBOLS = {
    "BTCUSD":  {"product_id": 27,   "size": 1},
    "ETHUSD":  {"product_id": 3,    "size": 1},
    "SOLUSD":  {"product_id": 1320, "size": 1},
    "PAXGUSD": {"product_id": 35,   "size": 1}
}

DHAN_SYMBOLS = {
    "NIFTY":     {"security_id": "13",  "lot_size": 75,  "strike_gap": 50},
    "BANKNIFTY": {"security_id": "25",  "lot_size": 15,  "strike_gap": 100}
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

def set_leverage(product_id, leverage=50):
    try:
        path = "/v2/products/leverage"
        url = DELTA_BASE_URL + path
        data = {"product_id": product_id, "leverage": str(leverage)}
        body = json.dumps(data)
        headers = get_delta_headers("POST", path, body)
        response = requests.post(url, data=body, headers=headers)
        logger.info("Leverage set: " + str(response.json()))
    except Exception as e:
        logger.error("Leverage error: " + str(e))

def place_delta_order(symbol, side):
    try:
        config = DELTA_SYMBOLS.get(symbol)
        if not config:
            return {"error": "Symbol not found"}

        set_leverage(config["product_id"], 50)

        path = "/v2/orders"
        url = DELTA_BASE_URL + path
        data = {
            "product_symbol": symbol,
            "side": side,
            "order_type": "market_order",
            "size": config["size"]
        }
        body = json.dumps(data)
        headers = get_delta_headers("POST", path, body)
        response = requests.post(url, data=body, headers=headers)
        result = response.json()
        logger.info("Delta Order: " + str(result))

        if result.get("success"):
            fill_price = float(result["result"].get("average_fill_price", 0))
            if fill_price > 0:
                set_delta_sl_tp(symbol, side, fill_price, config["product_id"])

        return result
    except Exception as e:
        logger.error("Delta order error: " + str(e))
        return {"error": str(e)}

def set_delta_sl_tp(symbol, side, entry_price, product_id):
    try:
        sl_pct = 0.5
        tp_pct = 1.0

        if side == "buy":
            sl_price = round(entry_price * (1 - sl_pct / 100), 2)
            tp_price = round(entry_price * (1 + tp_pct / 100), 2)
            sl_side = "sell"
        else:
            sl_price = round(entry_price * (1 + sl_pct / 100), 2)
            tp_price = round(entry_price * (1 - tp_pct / 100), 2)
            sl_side = "buy"

        path = "/v2/orders"
        url = DELTA_BASE_URL + path

        sl_data = {
            "product_id": product_id,
            "side": sl_side,
            "order_type": "stop_loss_order",
            "stop_price": str(sl_price),
            "size": DELTA_SYMBOLS.get(symbol, {}).get("size", 1),
            "reduce_only": True
        }
        body = json.dumps(sl_data)
        headers = get_delta_headers("POST", path, body)
        sl_response = requests.post(url, data=body, headers=headers)
        logger.info("SL set: " + str(sl_response.json()))

        tp_data = {
            "product_id": product_id,
            "side": sl_side,
            "order_type": "limit_order",
            "limit_price": str(tp_price),
            "size": DELTA_SYMBOLS.get(symbol, {}).get("size", 1),
            "reduce_only": True
        }
        body = json.dumps(tp_data)
        headers = get_delta_headers("POST", path, body)
        tp_response = requests.post(url, data=body, headers=headers)
        logger.info("TP set: " + str(tp_response.json()))

    except Exception as e:
        logger.error("SL/TP error: " + str(e))

def get_index_price(security_id):
    try:
        url = DHAN_BASE_URL + "/v2/marketfeed/ltp"
        headers = {
            "access-token": DHAN_ACCESS_TOKEN,
            "Content-Type": "application/json"
        }
        data = {"NSE_EQ": [security_id]}
        response = requests.post(url, json=data, headers=headers)
        result = response.json()
        return float(result["data"]["NSE_EQ"][security_id]["ltp"])
    except Exception as e:
        logger.error("Price error: " + str(e))
        return None

def get_itm_strike(price, action, gap):
    if action == "buy":
        atm = math.floor(price / gap) * gap
        return atm - gap, "CE"
    else:
        atm = math.ceil(price / gap) * gap
        return atm + gap, "PE"

def place_dhan_option_order(symbol, action, quantity=None):
    try:
        config = DHAN_SYMBOLS.get(symbol)
        if not config:
            return {"error": "Symbol not found"}

        if quantity is None:
            quantity = config["lot_size"]

        price = get_index_price(config["security_id"])
        if not price:
            return {"error": "Could not fetch price"}

        strike, option_type = get_itm_strike(price, action, config["strike_gap"])

        today = date.today()
        months = ["JAN","FEB","MAR","APR","MAY","JUN",
                  "JUL","AUG","SEP","OCT","NOV","DEC"]

        if today.month == 12:
            expiry_month = "JAN"
            expiry_year  = str(today.year + 1)[2:]
        else:
            expiry_month = months[today.month]
            expiry_year  = str(today.year)[2:]

        trading_symbol = symbol + expiry_year + expiry_month + str(strike) + option_type
        logger.info("Dhan symbol: " + trading_symbol)

        url = DHAN_BASE_URL + "/v2/orders"
        data = {
            "dhanClientId":    DHAN_CLIENT_ID,
            "transactionType": "BUY",
            "exchangeSegment": "NSE_FNO",
            "productType":     "INTRADAY",
            "orderType":       "MARKET",
            "validity":        "DAY",
            "tradingSymbol":   trading_symbol,
            "quantity":        quantity,
            "price":           0
        }
        headers = {
            "access-token": DHAN_ACCESS_TOKEN,
            "Content-Type": "application/json"
        }
        response = requests.post(url, json=data, headers=headers)
        result = response.json()
        logger.info("Dhan Order: " + str(result))
        return result

    except Exception as e:
        logger.error("Dhan error: " + str(e))
        return {"error": str(e)}

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    if data.get("secret") != WH_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    action   = data.get("action", "").lower()
    symbol   = data.get("symbol", "BTCUSD").upper()
    quantity = data.get("quantity", None)
    if quantity:
        quantity = int(quantity)

    if action not in ["buy", "sell"]:
        return jsonify({"error": "Invalid action"}), 400

    if symbol in DELTA_SYMBOLS:
        result   = place_delta_order(symbol, action)
        exchange = "Delta"
    elif symbol in DHAN_SYMBOLS:
        result   = place_dhan_option_order(symbol, action, quantity)
        exchange = "Dhan"
    else:
        return jsonify({"error": "Symbol not supported"}), 400

    return jsonify({
        "status":   "success",
        "exchange": exchange,
        "action":   action,
        "symbol":   symbol,
        "result":   result,
        "time":     datetime.now().isoformat()
    }), 200

@app.route("/symbols", methods=["GET"])
def symbols():
    return jsonify({
        "delta":  list(DELTA_SYMBOLS.keys()),
        "dhan":   list(DHAN_SYMBOLS.keys())
    })

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "running", "leverage": "50X", "margin": "$10"})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
