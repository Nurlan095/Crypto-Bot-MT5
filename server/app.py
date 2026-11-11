import asyncio
import json
import os
import re
import shutil
import subprocess
import zipfile
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
from fastapi import FastAPI, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from bot_engine import CryptoBotEngine

engine = CryptoBotEngine()


def sync_server_artifacts_on_startup() -> None:
    app_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = "/opt/cryptobot-repo"
    ver_path = os.path.join(app_dir, "version.json")
    repo_ver_path = os.path.join(repo_dir, "server", "version.json")
    base_apk = os.path.join(app_dir, "base_template.apk")
    live_apk = os.path.join(app_dir, "Crypto_Bot_v2_50.apk")
    keystore = os.path.join(app_dir, "release-key.jks")
    dash_path = os.path.join(app_dir, "dashboard.html")

    # 1. Sync github_auto_sync.py & ServerBridge.ex5 if repo exists
    try:
        repo_sync = os.path.join(repo_dir, "server", "github_auto_sync.py")
        if os.path.exists(repo_sync):
            shutil.copy2(repo_sync, os.path.join(app_dir, "github_auto_sync.py"))
        repo_ex5 = os.path.join(repo_dir, "server", "ServerBridge.ex5")
        mt5_ex5 = "/opt/mt5/MQL5/Experts/ServerBridge.ex5"
        if os.path.exists(repo_ex5) and os.path.exists(os.path.dirname(mt5_ex5)):
            shutil.copy2(repo_ex5, mt5_ex5)
    except Exception as exc:
        print(f"[StartupSync] Aux copy warning: {exc}")

    # 2. Determine target version
    cur_info = {"version_code": 267, "version_name": "2.67"}
    if os.path.exists(ver_path):
        try:
            with open(ver_path, "r", encoding="utf-8") as f:
                cur_info = json.load(f)
        except Exception:
            pass

    repo_info = {}
    if os.path.exists(repo_ver_path):
        try:
            with open(repo_ver_path, "r", encoding="utf-8") as f:
                repo_info = json.load(f)
        except Exception:
            pass

    target_code = max(int(cur_info.get("version_code", 267)), int(repo_info.get("version_code", 269)), 269)
    target_name = f"{target_code / 100.0:.2f}"
    target_changelog = repo_info.get("changelog") or cur_info.get("changelog") or f"Обновление v{target_name}"

    if not os.path.exists(base_apk) or not os.path.exists(keystore) or not os.path.exists(dash_path):
        return

    # 3. Check if live_apk already has patched AndroidManifest.xml with target_name
    need_apk_patch = (int(cur_info.get("version_code", 0)) < target_code) or (not os.path.exists(live_apk))
    if not need_apk_patch and os.path.exists(live_apk):
        try:
            with zipfile.ZipFile(live_apk, "r") as zchk:
                m_bytes = zchk.read("AndroidManifest.xml")
                expected_str = b"\x04\x00" + target_name.encode("utf-16le") + b"\x00\x00"
                if len(target_name) == 4 and expected_str not in m_bytes:
                    need_apk_patch = True
        except Exception:
            need_apk_patch = True

    if not need_apk_patch:
        return

    try:
        with open(dash_path, "r", encoding="utf-8") as df:
            html_text = df.read()
        html_text = re.sub(r"let\s+localCode\s*=\s*\d+\s*;", f"let localCode = {target_code};", html_text)
        html_bytes = html_text.encode("utf-8")
        with open(dash_path, "wb") as df:
            df.write(html_bytes)

        raw_apk = "/tmp/cb_app_raw.apk"
        aligned_apk = "/tmp/cb_app_aligned.apk"
        signed_apk = "/tmp/cb_app_signed.apk"

        with zipfile.ZipFile(base_apk, "r") as zin:
            with zipfile.ZipFile(raw_apk, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename.startswith("META-INF/") or item.filename == "assets/index.html":
                        continue
                    data = zin.read(item.filename)
                    if item.filename == "AndroidManifest.xml":
                        if len(target_name) == 4:
                            old_str = b"\x04\x00" + "2.67".encode("utf-16le") + b"\x00\x00"
                            new_str = b"\x04\x00" + target_name.encode("utf-16le") + b"\x00\x00"
                            data = data.replace(old_str, new_str, 1)
                        old_vc = b"\xff\xff\xff\xff\x08\x00\x00\x10" + (267).to_bytes(4, "little")
                        new_vc = b"\xff\xff\xff\xff\x08\x00\x00\x10" + int(target_code).to_bytes(4, "little")
                        data = data.replace(old_vc, new_vc, 1)
                        zout.writestr("AndroidManifest.xml", data)
                        continue
                    zout.writestr(item, data)
                zout.writestr("assets/index.html", html_bytes)

        r1 = subprocess.run(["zipalign", "-f", "-p", "4", raw_apk, aligned_apk], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r1.returncode == 0:
            r2 = subprocess.run([
                "apksigner", "sign",
                "--ks", keystore,
                "--ks-pass", "pass:android",
                "--key-pass", "pass:android",
                "--out", signed_apk,
                aligned_apk,
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if r2.returncode == 0:
                shutil.move(signed_apk, live_apk)
                os.chmod(live_apk, 0o644)
                new_ver_obj = {
                    "version_code": target_code,
                    "version_name": target_name,
                    "apk_url": "https://webrelax.pro/cryptobot/Crypto_Bot_v2_50.apk",
                    "changelog": target_changelog,
                }
                with open(ver_path, "w", encoding="utf-8") as vf:
                    json.dump(new_ver_obj, vf, ensure_ascii=False, indent=2)
                print(f"[StartupSync] Rebuilt APK with patched AndroidManifest v{target_name} (#{target_code})")
    except Exception as exc:
        print(f"[StartupSync] APK patch error: {exc}")


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
    sync_server_artifacts_on_startup()
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
