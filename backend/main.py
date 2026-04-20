"""
Hassan Charges - Real-Time Forex Exchange Rate Server
FastAPI + Socket.IO + Redis Backend
"""

import asyncio
import json
import random
import time
from pathlib import Path
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from config import FOREX_PAIRS, CURRENCY_NAMES, DEMO_MODE, HOST, PORT

# ══════════════════════════════════════════════════════════
# Socket.IO Server
# ══════════════════════════════════════════════════════════
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    ping_interval=25,
    ping_timeout=60
)

# ══════════════════════════════════════════════════════════
# In-Memory Price Cache
# ══════════════════════════════════════════════════════════
price_cache = {}
price_history = {}
connected_clients = set()

def init_prices():
    """Initialize all currency pair prices."""
    for symbol, cfg in FOREX_PAIRS.items():
        base, quote = symbol.split("/")
        price_cache[symbol] = {
            "symbol": symbol,
            "price": cfg["price"],
            "open": cfg["price"],
            "high": cfg["price"],
            "low": cfg["price"],
            "prev_price": cfg["price"],
            "change": 0.0,
            "change_pct": 0.0,
            "bid": cfg["price"] * 0.99995,
            "ask": cfg["price"] * 1.00005,
            "timestamp": time.time(),
            "category": cfg["cat"],
            "base_flag": cfg["bf"],
            "quote_flag": cfg["qf"],
            "decimals": cfg["d"],
            "base_name": CURRENCY_NAMES.get(base, base),
            "quote_name": CURRENCY_NAMES.get(quote, quote),
        }
        price_history[symbol] = [cfg["price"]]

# ══════════════════════════════════════════════════════════
# Data Manager (Failover Architecture)
# ══════════════════════════════════════════════════════════
class DataManager:
    def __init__(self):
        self.active_source = "primary" # "primary" (TwelveData) or "secondary" (Polygon)
        self.running = False
        init_prices()

    async def start(self):
        self.running = True
        await asyncio.sleep(1.5)
        await sio.emit('initial_prices', price_cache)
        
        while self.running:
            try:
                updates = await self.fetch_data()
                if updates and connected_clients:
                    await sio.emit('price_updates', updates)
            except Exception as e:
                print(f"[-] Error fetching from {self.active_source}: {e}")
                self.switch_fallback()
            
            await asyncio.sleep(1)

    async def fetch_data(self):
        """
        Simulates fetching from APIs. In production:
        if self.active_source == 'primary': return await fetch_twelvedata()
        else: return await fetch_polygon()
        """
        # --- Simulated live data generation ---
        updates = {}
        for symbol, cfg in FOREX_PAIRS.items():
            cur = price_cache[symbol]
            old_price = cur["price"]

            v = {"major": 0.00015, "minor": 0.00020, "exotic": 0.00050, "crypto": 0.0015}.get(cfg["cat"], 0.0003)
            drift = (cfg["price"] - old_price) * 0.001
            
            # Slight random difference based on data source to simulate switch
            source_bias = 0 if self.active_source == "primary" else 0.00001
            change = random.gauss(drift, v * old_price) + source_bias
            new_price = max(old_price + change, old_price * 0.95)

            spread = new_price * 0.00005 if cfg["cat"] in ["major", "minor"] else new_price * 0.0003
            price_change = new_price - cur["open"]
            
            cur.update({
                "price": new_price,
                "prev_price": old_price,
                "change": price_change,
                "change_pct": (price_change / cur["open"]) * 100,
                "bid": new_price - spread / 2,
                "ask": new_price + spread / 2,
                "high": max(cur["high"], new_price),
                "low": min(cur["low"], new_price),
                "timestamp": time.time(),
            })

            history = price_history[symbol]
            history.append(new_price)
            if len(history) > 60: history.pop(0)

            updates[symbol] = cur.copy()
            updates[symbol]["sparkline"] = list(history)
            
        return updates

    def switch_fallback(self):
        """Switch to secondary data source to maintain Data Integrity"""
        old_source = self.active_source
        self.active_source = "secondary" if old_source == "primary" else "primary"
        print(f"[*] DATA INTEGRITY: Switched data source from {old_source} to {self.active_source}")

data_manager = DataManager()

# ══════════════════════════════════════════════════════════
# FastAPI App
# ══════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(data_manager.start())
    yield
    data_manager.running = False
    task.cancel()

app = FastAPI(title="Hassan Charges", lifespan=lifespan)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/api/prices")
async def get_prices():
    return JSONResponse(content=price_cache)

@app.get("/api/health")
async def health():
    return {"status": "ok", "pairs": len(price_cache), "clients": len(connected_clients), "mode": "demo" if DEMO_MODE else "live"}

# Mount static assets
app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")

# ══════════════════════════════════════════════════════════
# Socket.IO Events
# ══════════════════════════════════════════════════════════
@sio.on('connect')
async def handle_connect(sid, environ):
    connected_clients.add(sid)
    print(f"[+] Client connected: {sid} (Total: {len(connected_clients)})")
    if price_cache:
        enriched = {}
        for sym, data in price_cache.items():
            enriched[sym] = data.copy()
            enriched[sym]["sparkline"] = list(price_history.get(sym, []))
        await sio.emit('initial_prices', enriched, room=sid)

@sio.on('disconnect')
async def handle_disconnect(sid):
    connected_clients.discard(sid)
    print(f"[-] Client disconnected: {sid} (Total: {len(connected_clients)})")

# ══════════════════════════════════════════════════════════
# Combined ASGI Application
# ══════════════════════════════════════════════════════════
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)

if __name__ == "__main__":
    import uvicorn
    print(f"""
╔══════════════════════════════════════════════════╗
║          Hassan Charges - Live Forex Server      ║
║──────────────────────────────────────────────────║
║  Local:   http://localhost:{PORT}                 ║
║  Network: http://<your-ip>:{PORT}                 ║
║  Mode:    {'DEMO (simulated data)' if DEMO_MODE else 'LIVE (Twelve Data)'}          ║
║  Pairs:   {len(FOREX_PAIRS)} currency pairs                  ║
╚══════════════════════════════════════════════════╝
    """)
    uvicorn.run("main:socket_app", host=HOST, port=PORT, reload=False, log_level="info")
