from flask import Flask, request, jsonify
import os
import logging
import requests
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_KEY = os.environ.get("DELTA_API_KEY", "")
API_SECRET = os.environ.get("DELTA_API_SECRET", "")
WH_SECRET = os.environ.get("WEBHOOK_SECRET", "mysecret123")

BASE_URL = "https://api.india.delta.exchange"

def get_headers():
    import hashlib
    import hmac
    import time
    timestamp = str(int(time.time()))
    signature = hmac.new(
        API_SECRET.encode(),
        timestamp.encode(),
        hashlib.sha256
    ).hexdigest()
    return {
        "api-key": API_KEY,
        "timestamp": timestamp,
        "signature": signature,
        "Content-Type": "application/json"
    }

def place_order(symbol, side, size):
    url = BASE_URL + "/v2/orders"
    data = {
        "product_symbol": symbol,
        "side": side,
        "order_type": "market_order",
        "size": int(size)
    }
    response = requests.post(url, json=data, headers=get_headers())
    return response.json()

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    if data.get("secret") != WH_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    action = data.get("action", "").lower()
    symbol = data.get("symbol", "BTCUSD")
    size = data.get("size", "1")
    if action not in ["buy", "sell"]:
        return jsonify({"error": "Invalid action"}), 400
    result = place_order(symbol, action, size)
    logger.info(result)
    return jsonify({
        "status": "success",
        "action": action,
        "symbol": symbol,
        "result": result,
        "time": datetime.now().isoformat()
    }), 200

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "running", "exchange": "Delta Exchange India"})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
