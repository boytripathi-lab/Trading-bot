from flask import Flask, request, jsonify
import os
import logging
import requests
import hashlib
import hmac
import time
import json
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_KEY = os.environ.get("DELTA_API_KEY", "")
API_SECRET = os.environ.get("DELTA_API_SECRET", "")
WH_SECRET = os.environ.get("WEBHOOK_SECRET", "mysecret123")

BASE_URL = "https://api.india.delta.exchange"

SYMBOL_CONFIG = {
    "BTCUSD": {"product_id": 27, "size": 5},
    "ETHUSD": {"product_id": 3, "size": 5},
    "SOLUSD": {"product_id": 1320, "size": 5}
}

def get_headers(method, path, body=""):
    timestamp = str(int(time.time()))
    message = method + timestamp + path + body
    signature = hmac.new(
        API_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return {
        "api-key": API_KEY,
        "timestamp": timestamp,
        "signature": signature,
        "Content-Type": "application/json"
    }

def set_leverage(product_id, leverage=25):
    path = "/v2/products/leverage"
    url = BASE_URL + path
    data = {"product_id": product_id, "leverage": str(leverage)}
    body = json.dumps(data)
    headers = get_headers("POST", path, body)
    response = requests.post(url, data=body, headers=headers)
    logger.info("Leverage: " + str(response.json()))

def place_order(symbol, side, sl=None, tp=None):
    config = SYMBOL_CONFIG.get(symbol, {"product_id": 27, "size": 5})
    set_leverage(config["product_id"], 25)
    path = "/v2/orders"
    url = BASE_URL + path
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
    headers = get_headers("POST", path, body)
    response = requests.post(url, data=body, headers=headers)
    result = response.json()
    logger.info("Order: " + str(result))
    return result

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    if data.get("secret") != WH_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    action = data.get("action", "").lower()
    symbol = data.get("symbol", "BTCUSD")
    sl = data.get("sl", None)
    tp = data.get("tp", None)
    if action not in ["buy", "sell"]:
        return jsonify({"error": "Invalid action"}), 400
    result = place_order(symbol, action, sl, tp)
    return jsonify({
        "status": "success",
        "action": action,
        "symbol": symbol,
        "size": 5,
        "leverage": "25X",
        "sl": sl,
        "tp": tp,
        "result": result,
        "time": datetime.now().isoformat()
    }), 200

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "running", "exchange": "Delta Exchange India", "size": 5, "leverage": "25X"})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
