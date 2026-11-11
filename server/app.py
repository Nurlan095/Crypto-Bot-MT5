import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
from fastapi import FastAPI, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from bot_engine import CryptoBotEngine

engine = CryptoBotEngine()


def load_version_info() -> Dict[str, Any]:
    ver_path = os.path.join(os.path.dirname(__file__), "version.json")
    if os.path.exists(ver_path):
        try:
            with open(ver_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "version_code": 251,
        "version_name": "2.51",
        "apk_url": "https://webrelax.pro/cryptobot/Crypto_Bot_v2_50.apk",
        "changelog": "Актуальная версия Crypto Bot",
    }


async def bot_background_loop() -> None:
    while True:
        try:
            await engine.step_tick()
        except Exception as exc:
            print(f"[BotLoop Error] {exc}")
        await asyncio.sleep(1.5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await engine.step_tick()
    task = asyncio.create_task(bot_background_loop())
    yield
    task.cancel()


app = FastAPI(
    title="Crypto Bot v2.50 Server API",
    version="2.51",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard() -> HTMLResponse:
    html_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.api_route("/Crypto_Bot_v2_50.apk", methods=["GET", "HEAD"])
async def download_apk(request: Request):
    ua = request.headers.get("user-agent", "")
    if request.method == "GET" and "; wv)" in ua and "raw" not in request.query_params:
        return HTMLResponse(
            content="""<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>body{background:#080d16;color:#f1f5f9;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;padding:20px;text-align:center;}
.box{background:#101826;border:1px solid #10b981;border-radius:16px;padding:24px;max-width:340px;width:100%;}</style></head>
<body><div class="box">
<div style="font-size:18px;font-weight:800;color:#34d399;margin-bottom:10px;">⏳ Установка обновления...</div>
<div id="st" style="font-size:13px;color:#cbd5e1;line-height:1.4;">Скачивание новой версии приложения, пожалуйста подождите несколько секунд...</div>
</div>
<script>
window.onApkUpdateStatus = function(msg) { document.getElementById('st').textContent = msg; };
if (window.AndroidBridge && window.AndroidBridge.downloadAndInstallUpdate) {
  window.AndroidBridge.downloadAndInstallUpdate("https://webrelax.pro/cryptobot/Crypto_Bot_v2_50.apk?raw=1");
} else if (window.AndroidBridge && window.AndroidBridge.downloadAndInstallApk) {
  window.AndroidBridge.downloadAndInstallApk("https://webrelax.pro/cryptobot/Crypto_Bot_v2_50.apk?raw=1");
}
</script></body></html>"""
        )

    apk_path = os.path.join(os.path.dirname(__file__), "Crypto_Bot_v2_50.apk")
    if os.path.exists(apk_path):
        return FileResponse(
            apk_path,
            media_type="application/vnd.android.package-archive",
            filename="Crypto_Bot_v2_50.apk",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    return JSONResponse(status_code=404, content={"error": "APK not found"})


@app.get("/api/app-version")
async def get_app_version() -> JSONResponse:
    return JSONResponse(
        content=load_version_info(),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/api/status")
async def get_status() -> JSONResponse:
    state = engine.get_full_state()
    state["app_update"] = load_version_info()
    return JSONResponse(content=state)


@app.get("/api/notifications")
async def get_notifications(since_id: int = 0) -> JSONResponse:
    return JSONResponse(content={"notifications": engine.get_notifications(since_id=since_id)})


@app.post("/api/settings")
async def update_settings(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    updated = engine.save_settings(payload)
    await engine.step_tick()
    return JSONResponse(content={"ok": True, "settings": updated})


@app.post("/api/mt5-sync")
async def mt5_sync(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    cmds = engine.apply_mt5_sync(payload)
    return JSONResponse(
        content={
            "ok": True,
            "commands": cmds,
            "settings": engine.settings,
        }
    )


@app.post("/api/control")
async def control_bot(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    action = str(payload.get("action", "")).lower()
    if action == "start":
        engine.save_settings({"is_running": True})
        engine.add_notification("Бот запущен", "Автоматическая торговля M15 активирована", "success")
    elif action == "pause":
        engine.save_settings({"is_running": False})
        engine.add_notification("Бот на паузе", "Открытие новых позиций приостановлено", "warning")
    elif action == "open":
        pos_type = str(payload.get("pos_type", "BUY")).upper()
        vol: Optional[float] = payload.get("volume")
        pos = engine.open_position(pos_type, volume=float(vol) if vol else None, comment="Ручной вход из приложения")
        return JSONResponse(content={"ok": pos is not None, "position": pos})
    elif action == "close":
        ticket = int(payload.get("ticket", 0))
        ok = engine.close_position(ticket, reason="Закрыто из Android-приложения")
        return JSONResponse(content={"ok": ok})
    elif action == "safe":
        ticket = int(payload.get("ticket", 0))
        ok = engine.trigger_partial_safe(ticket, auto=False)
        return JSONResponse(content={"ok": ok})
    elif action == "breakeven":
        ticket = int(payload.get("ticket", 0))
        ok = engine.trigger_breakeven(ticket)
        return JSONResponse(content={"ok": ok})
    elif action == "set_balance":
        bal = float(payload.get("balance", 10000.0))
        new_bal = engine.set_balance(bal)
        return JSONResponse(content={"ok": True, "balance": new_bal})

    return JSONResponse(content={"ok": True, "state": engine.get_full_state()})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8799, reload=False)
