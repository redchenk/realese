#!/usr/bin/env python3
"""
欧易(OKX) 自动交易机器人 v1.0
⚠️ 免责声明: 此代码仅供参考学习，造成的任何损失与作者无关
"""

import urllib.request
import urllib.parse
import json
import time
import sys
import hmac
import hashlib
import base64
from datetime import datetime

# ============ 配置区域 ============
# ============ 修改这里开启实盘 ============
REAL_TRADE = True   # True=实盘交易, False=模拟交易
API_KEY = "a05bbacd-b17c-4b5b-a7aa-67657bb01488"    # 你的API Key
API_SECRET = "7837763198B4E1B34530FA718E43FF73"     # 你的API Secret
PASSPHRASE = "@Aa620880123"    # API密码(如果设置了的话)
SYMBOL = "TRX-USDT"  # 交易对 (OKX格式)
TRADE_AMOUNT = 1   # 每次买入金额(USDT)
# ==========================================

OKX_URL = "https://www.okx.com"

def log(msg):
    """日志输出"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def http_get(url, params=None, headers=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log(f"请求失败: {e}")
        return None

def http_post(url, data, headers=None):
    try:
        req = urllib.request.Request(
            url, 
            data=urllib.parse.urlencode(data).encode(),
            headers=headers or {},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log(f"请求失败: {e}")
        return None

# OKX 签名
def okx_sign(timestamp, method, request_path, body, secret):
    message = timestamp + method + request_path + (body if body else "")
    mac = hmac.new(secret.encode(), message.encode(), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()

def get_kline(instId, bar="1h", limit=50):
    return http_get(f"{OKX_URL}/api/v5/market/history-candles", 
                   {"instId": instId, "bar": bar, "limit": str(limit)})

def calc_rsi(prices, n=14):
    if len(prices) < n+1: return None
    gains, losses = 0, 0
    for i in range(1, n+1):
        diff = prices[-i] - prices[-i-1]
        if diff > 0: gains += diff
        else: losses -= diff
    if losses == 0: return 100
    rs = gains / losses
    return round(100 - (100/(1+rs)), 2)

def calc_ma(prices, n=20):
    if len(prices) < n: return None
    return round(sum(prices[-n:])/n, 4)

# ============ 交易函数 ============
def create_order(instId, side, size):
    """市价买入/卖出"""
    timestamp = datetime.utcnow().isoformat() + "Z"
    
    # OKX市价单参数
    body = json.dumps({
        "instId": instId,
        "tdMode": "cash",
        "side": side,
        "ordType": "market",
        "sz": str(size)
    })
    
    request_path = "/api/v5/trade/order"
    signature = okx_sign(timestamp, "POST", request_path, body, API_SECRET)
    
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'OK-ACCESS-KEY': API_KEY,
        'OK-ACCESS-SIGN': signature,
        'OK-ACCESS-TIMESTAMP': timestamp,
    }
    if PASSPHRASE:
        headers['OK-ACCESS-PASSPHRASE'] = PASSPHRASE
    
    if not REAL_TRADE:
        log(f"🔮 [模拟] {'买入' if side=='buy' else '卖出'} {size} {instId}")
        return {"ordId": "SIMULATION", "sCode": "0"}
    
    url = f"{OKX_URL}{request_path}"
    return http_post(url, {}, headers={**headers, **{'Body': body}})

def get_balance():
    """获取账户余额"""
    timestamp = datetime.utcnow().isoformat() + "Z"
    request_path = "/api/v5/account/balance"
    signature = okx_sign(timestamp, "GET", request_path, "", API_SECRET)
    
    headers = {
        'OK-ACCESS-KEY': API_KEY,
        'OK-ACCESS-SIGN': signature,
        'OK-ACCESS-TIMESTAMP': timestamp,
    }
    if PASSPHRASE:
        headers['OK-ACCESS-PASSPHRASE'] = PASSPHRASE
    
    if not REAL_TRADE:
        log(f"🔮 [模拟] 余额: USDT 1000")
        return {"USDT": 1000, "TRX": 0}
    
    url = f"{OKX_URL}{request_path}"
    data = http_get(url, {}, headers)
    if data and data.get("data"):
        for bal in data["data"][0]["details"]:
            if bal["ccy"] in ["USDT", "TRX"]:
                print(f"  {bal['ccy']}: {bal['availBal']}")
        return {b["ccy"]: float(b["availBal"]) for b in data["data"][0]["details"]}
    return None

def get_current_price(instId):
    """获取当前价格"""
    data = http_get(f"{OKX_URL}/api/v5/market/ticker", {"instId": instId})
    if data and data.get("data"):
        return float(data["data"][0]["last"])
    return None

# ============ 交易策略 ============
class TradingBot:
    def __init__(self, symbol, amount):
        self.symbol = symbol
        self.amount = amount
        self.last_signal = None
        self.position = 0
        self.entry_price = 0
        
    def analyze(self):
        data = get_kline(self.symbol, "1h", 50)
        if not data or not data.get("data"):
            return None
        
        klines = data["data"]
        closes = [float(k[4]) for k in klines]
        if len(closes) < 20:
            return None
        
        rsi = calc_rsi(closes)
        ma20 = calc_ma(closes, 20)
        ma50 = calc_ma(closes, 50) if len(closes) >= 50 else None
        
        price = closes[-1]
        
        signal = None
        if rsi and rsi < 30:
            signal = "BUY"
        elif rsi and rsi > 70:
            signal = "SELL"
        
        return {
            "price": price,
            "rsi": rsi,
            "ma20": ma20,
            "ma50": ma50,
            "signal": signal
        }
    
    def trade(self):
        analysis = self.analyze()
        if not analysis:
            log("❌ 获取数据失败")
            return
        
        price = analysis["price"]
        rsi = analysis["rsi"]
        signal = analysis["signal"]
        
        mode = "⚠️ 实盘" if REAL_TRADE else "🔮 模拟"
        log(f"{mode} {self.symbol}: ${price:.4f} | RSI: {rsi}")
        
        # 买入
        if signal == "BUY" and self.last_signal != "BUY":
            qty = self.amount / price
            result = create_order(self.symbol, "buy", qty)
            
            if result and result.get("data"):
                self.position += qty
                self.entry_price = price
                log(f"✅ 买入成功! 数量: {qty:.2f}")
            elif not REAL_TRADE:
                self.position += qty
                self.entry_price = price
                log(f"🔮 [模拟] 买入 {qty:.2f} @ ${price:.4f}")
            self.last_signal = "BUY"
            
        # 卖出
        elif signal == "SELL" and self.last_signal != "SELL" and self.position > 0:
            qty = self.position
            result = create_order(self.symbol, "sell", qty)
            
            if result and result.get("data"):
                profit = (price - self.entry_price) * self.position
                log(f"✅ 卖出成功! 盈利: ${profit:.2f}")
                self.position = 0
            elif not REAL_TRADE:
                profit = (price - self.entry_price) * self.position
                log(f"🔮 [模拟] 卖出 {qty:.2f} @ ${price:.4f} | 盈利: ${profit:.2f}")
                self.position = 0
            self.last_signal = "SELL"
        
        # 持仓状态
        if self.position > 0:
            profit = (price - self.entry_price) * self.position
            log(f"💰 持仓: {self.position:.2f} | 盈亏: ${profit:+.2f}")

# ============ 主程序 ============
def main():
    print("\n" + "="*50)
    print("🤖 欧易自动交易机器人 v1.0")
    print("="*50)
    print(f"模式: {'⚠️ 实盘交易' if REAL_TRADE else '🔮 模拟交易'}")
    print(f"交易对: {SYMBOL}")
    print(f"每次金额: {TRADE_AMOUNT} USDT")
    print("="*50 + "\n")
    
    if REAL_TRADE:
        log("获取账户余额:")
        get_balance()
    
    bot = TradingBot(SYMBOL, TRADE_AMOUNT)
    
    try:
        while True:
            bot.trade()
            log("等待下一个周期(60秒)...")
            time.sleep(60)
    except KeyboardInterrupt:
        log("\n🛑 停止交易")

if __name__ == "__main__":
    main()
