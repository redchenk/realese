#!/usr/bin/env python3
"""
欧易(OKX) 自动交易机器人 v2.0
根据官方API文档编写
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
from datetime import datetime, timezone, timedelta

# ============ 配置区域 ============
REAL_TRADE = True   # True=实盘交易, False=模拟交易
API_KEY = "a05bbacd-b17c-4b5b-a7aa-67657bb01488"        # 你的API Key (重新申请!)
API_SECRET = "7837763198B4E1B34530FA718E43FF73"     # 你的API Secret
PASSPHRASE = "@Aa620880123"     # API密码(如果设置了的话)

# 代理设置 (如果有VPN/代理在这里填)
PROXY = ""          # 例如: "http://127.0.0.1:7890"

SYMBOL = "TRX-USDT"    # 交易对
TRADE_AMOUNT = 1      # 每次买入金额(USDT)
# ==========================================

OKX_URL = "https://www.okx.com"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# OKX 签名生成
def gen_signature(timestamp, method, request_path, body=""):
    """生成OKX API签名"""
    message = timestamp + method + request_path + body
    mac = hmac.new(API_SECRET.encode(), message.encode(), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()

def http_request(method, url, params=None, body=None, need_sign=True):
    """发送HTTP请求"""
    headers = {'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
    
    if need_sign and API_KEY and API_SECRET:
        timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        
        if method == 'GET' and params:
            request_path = url.replace(OKX_URL, '') + '?' + urllib.parse.urlencode(params)
        else:
            request_path = url.replace(OKX_URL, '')
        
        sign = gen_signature(timestamp, method, request_path, body or '')
        
        headers.update({
            'OK-ACCESS-KEY': API_KEY,
            'OK-ACCESS-SIGN': sign,
            'OK-ACCESS-TIMESTAMP': timestamp,
        })
        if PASSPHRASE:
            headers['OK-ACCESS-PASSPHRASE'] = PASSPHRASE
    
    try:
        if method == 'GET':
            if params:
                url += '?' + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers=headers)
        else:
            req = urllib.request.Request(url, data=body.encode() if body else None, headers=headers, method=method)
        
        proxy_handler = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}) if PROXY else None
        
        if proxy_handler:
            opener = urllib.request.build_opener(proxy_handler)
            resp = opener.open(req, timeout=15)
        else:
            resp = urllib.request.urlopen(req, timeout=15)
        
        return json.loads(resp.read().decode())
    except Exception as e:
        log(f"请求失败: {e}")
        return None

# ============ 行情API ============
def get_ticker(instId):
    """获取市场行情"""
    url = f"{OKX_URL}/api/v5/market/ticker"
    return http_request('GET', url, {"instId": instId}, need_sign=False)

def get_kline(instId, bar="1h", limit=50):
    """获取K线数据"""
    url = f"{OKX_URL}/api/v5/market/history-candles"
    return http_request('GET', url, {"instId": instId, "bar": bar, "limit": str(limit)}, need_sign=False)

# ============ 交易API ============
def get_balance():
    """获取账户余额"""
    if not REAL_TRADE:
        log("🔮 [模拟] 余额: USDT 1000")
        return {"USDT": 1000}
    
    url = f"{OKX_URL}/api/v5/account/balance"
    data = http_request('GET', url, need_sign=True)
    
    if data and data.get("code") == "0":
        for bal in data["data"][0]["details"]:
            if bal["ccy"] in ["USDT", "TRX"]:
                log(f"  {bal['ccy']}: {bal['availBal']}")
        return {b["ccy"]: float(b["availBal"]) for b in data["data"][0]["details"]}
    return None

def place_order(instId, side, ordType="market", sz="", px=""):
    """下单"""
    # 现货模式使用 cash
    tdMode = "cash"
    
    order_data = {
        "instId": instId,
        "tdMode": tdMode,
        "side": side,
        "ordType": ordType,
    }
    
    if sz:
        order_data["sz"] = str(sz)
    if px:
        order_data["px"] = px
    
    body = json.dumps(order_data)
    
    if not REAL_TRADE:
        log(f"🔮 [模拟] {'买入' if side=='buy' else '卖出'} {instId} 数量:{sz}")
        return {"ordId": "SIMULATION", "sCode": "0"}
    
    url = f"{OKX_URL}/api/v5/trade/order"
    data = http_request('POST', url, body=body, need_sign=True)
    
    if data and data.get("code") == "0":
        return data["data"][0]
    else:
        log(f"下单失败: {data}")
        return None

# ============ 技术指标 ============
def calc_rsi(prices, n=14):
    if len(prices) < n+1: return None
    gains, losses = 0, 0
    for i in range(1, n+1):
        diff = prices[-i] - prices[-i-1]
        if diff > 0: gains += diff
        else: losses -= diff
    if losses == 0: return 100
    return round(100 - (100/(1+gains/losses)), 2)

def calc_ma(prices, n=20):
    if len(prices) < n: return None
    return round(sum(prices[-n:])/n, 4)

# ============ 交易机器人 ============
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
        
        price = closes[-1]
        
        signal = None
        if rsi and rsi < 30:
            signal = "BUY"
        elif rsi and rsi > 70:
            signal = "SELL"
        
        return {"price": price, "rsi": rsi, "ma20": ma20, "signal": signal}
    
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
            qty = round(self.amount / price, 2)
            result = place_order(self.symbol, "buy", sz=qty)
            
            if result:
                self.position += qty
                self.entry_price = price
                log(f"✅ 买入成功! 数量: {qty}")
            self.last_signal = "BUY"
            
        # 卖出
        elif signal == "SELL" and self.last_signal != "SELL" and self.position > 0:
            qty = round(self.position, 2)
            result = place_order(self.symbol, "sell", sz=qty)
            
            if result:
                profit = (price - self.entry_price) * self.position
                log(f"✅ 卖出成功! 盈利: ${profit:.2f}")
                self.position = 0
            self.last_signal = "SELL"
        
        # 持仓状态
        if self.position > 0:
            profit = (price - self.entry_price) * self.position
            log(f"💰 持仓: {self.position:.2f} | 盈亏: ${profit:+.2f}")

# ============ 主程序 ============
def main():
    print("\n" + "="*50)
    print("🤖 欧易自动交易机器人 v2.0")
    print("="*50)
    print(f"模式: {'⚠️ 实盘交易' if REAL_TRADE else '🔮 模拟交易'}")
    print(f"交易对: {SYMBOL}")
    print(f"每次金额: {TRADE_AMOUNT} USDT")
    print("="*50 + "\n")
    
    if REAL_TRADE:
        if not API_KEY or not API_SECRET:
            log("❌ 请先填写 API_KEY 和 API_SECRET!")
            return
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
