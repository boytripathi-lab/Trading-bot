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
    "BTCUSD":   {"product_id": 27,   "size": 1},
    "ETHUSD":   {"product_id": 3,    "size": 1},
    "SOLUSD":   {"product_id": 1320, "size": 1},
    "XRPUSD":   {"product_id": 66,   "size": 1},
    "BNBUSD":   {"product_id": 11,   "size": 1},
    "AVAXUSD":  {"product_id": 536,  "size": 1},
    "LTCUSD":   {"product_id": 65,   "size": 1},
    "DOTUSD":   {"product_id": 580,  "size": 1},
    "ADAUSD":   {"product_id": 579,  "size": 1},
    "BCHUSD":   {"product_id": 68,   "size": 1},
    "TSLAXUSD": {"product_id": 100,  "size": 1},
    "AAPLXUSD": {"product_id": 101,  "size": 1},
    "NVDAXUSD": {"product_id": 102,  "size": 1},
    "AMZNXUSD": {"product_id": 103,  "size": 1},
    "METAXUSD": {"product_id": 104,  "size": 1},
    "SPYXUSD":  {"product_id": 105,  "size": 1},
    "QQQXUSD":  {"product_id": 106,  "size": 1}
}

DHAN_SYMBOLS = {
    "NIFTY":     {"security_id": "13",  "lot_size": 75},
    "BANKNIFTY": {"security_id": "25",  "lot_size": 15},
    "MIDCAPNIFTY": {"security_id": "442", "lot_size": 75}
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
    try:
        path = "/v2/products/leverage"
        url = DELTA_BASE_URL + path
        data = {"product_id": product_id, "leverage": str(leverage)}
        body = json.dumps(data)
        headers = get_delta_headers("POST", path, body)
        response = requests.post(url, data=body, headers=headers)
        logger.info("Leverage: " + str(response.json()))
    except Exception as e:
        logger.error("Leverage error: " + str(e))

def place_delta_order(symbol, side, sl=None, tp=None):
    config = DELTA_SYMBOLS.get(symbol)
    if not config:
        return {"error": "Symbol not found"}
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

def get_itm_strike(price, action, gap=50):
    if action == "buy":
        atm = math.floor(price / gap) * gap
        return atm - 100, "CE"
    else:
        atm = math.ceil(price / gap) * gap
        return atm + 100, "PE"

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
        gap = 50 if symbol == "NIFTY" else 100
        strike, option_type = get_itm_strike(price, action, gap)
        today = date.today()
        months = ["JAN","FEB","MAR","APR","MAY","JUN",
                 "JUL","AUG","SEP","OCT","NOV","DEC"]
        if today.month == 12:
            expiry_month = "JAN"
            expiry_year = str(today.year + 1)[2:]
        else:
            expiry_month = months[today.month]
            expiry_year = str(today.year)[2:]
        trading_symbol = f"{symbol}{expiry_year}{expiry_month}{strike}{option_type}"
        logger.info("Option symbol: " + trading_symbol)
        url = DHAN_BASE_URL + "/v2/orders"
        data = {
            "dhanClientId": DHAN_CLIENT_ID,
            "transactionType": "BUY",
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
        logger.info("Dhan Option: " + str(result))
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
    action = data.get("action", "").lower()
    symbol = data.get("symbol", "BTC
