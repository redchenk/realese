#!/usr/bin/env python3
"""
币安(Binance) 行情分析工具
国内可直接访问，无需代理
"""

import urllib.request
import urllib.parse
import json
import time
import sys

BINANCE_URL = "https://api.binance.com"

def get(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json'
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"❌ 请求失败: {e}", file=sys.stderr)
        return None

def get_tickers():
    """获取所有USDT交易对"""
    return get(f"{BINANCE_URL}/api/v3/ticker/24hr")

def get_kline(symbol, interval="1h", limit=50):
    """获取K线"""
    return get(f"{BINANCE_URL}/api/v3/klines", 
               {"symbol": symbol, "interval": interval, "limit": limit})

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

def analyze(symbol):
    data = get_kline(symbol, "1h", 50)
    if not data: return None
    
    closes = [float(k[4]) for k in data]
    if len(closes) < 20: return None
    
    rsi = calc_rsi(closes)
    ma20 = calc_ma(closes, 20)
    ma50 = calc_ma(closes, 50) if len(closes) >= 50 else None
    
    signal, reasons = "HOLD", []
    price = closes[-1]
    
    if rsi:
        if rsi < 30: signal, reasons = "BUY", [f"RSI={rsi}(超卖)"]
        elif rsi > 70: signal, reasons = "SELL", [f"RSI={rsi}(超买)"]
    
    if ma20 and ma50:
        reasons.append(f"MA20>{ma50}" if ma20 > ma50 else f"MA20<{ma50}")
    
    return {"symbol": symbol, "price": price, "signal": signal, "reasons": reasons, "rsi": rsi}

def main():
    print("\n" + "="*50)
    print("📊 币安行情分析工具 v1.0")
    print("="*50)
    
    print("\n🔄 正在获取市场数据...")
    tickers = get_tickers()
    
    if not tickers:
        print("❌ 无法获取数据")
        return
    
    # 过滤USDT交易对并按成交量排序
    usdt_pairs = [(t["symbol"], float(t["quoteVolume"])) 
                  for t in tickers if t["symbol"].endswith("USDT")]
    usdt_pairs.sort(key=lambda x: x[1], reverse=True)
    
    print(f"✅ 找到 {len(usdt_pairs)} 个USDT交易对\n")
    
    results = []
    for i, (sym, vol) in enumerate(usdt_pairs[:15]):
        print(f"  分析 {sym}...", end="\r", flush=True)
        r = analyze(sym)
        if r:
            r["volume"] = vol
            results.append(r)
        time.sleep(0.3)
    
    print("\n\n" + "="*50)
    
    buys = [r for r in results if r["signal"]=="BUY"]
    sells = [r for r in results if r["signal"]=="SELL"]
    
    print(f"🟢 买入信号 ({len(buys)}个):")
    for r in buys:
        print(f"  {r['symbol']} ${r['price']:.4f} | {' '.join(r['reasons'])}")
    
    print(f"\n🔴 卖出信号 ({len(sells)}个):")
    for r in sells:
        print(f"  {r['symbol']} ${r['price']:.4f} | {' '.join(r['reasons'])}")
    
    print(f"\n⚪ 观望 (前5):")
    for r in [r for r in results if r["signal"]=="HOLD"][:5]:
        print(f"  {r['symbol']} ${r['price']:.4f} | RSI={r['rsi']}")
    
    print("\n" + "="*50)
    print("⚠️ 仅供参考，不构成投资建议")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
