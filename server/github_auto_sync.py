import json
import os
import re
import shutil
import subprocess
import time
import zipfile

REPO_URL = "https://github.com/Nurlan095/Crypto-Bot-MT5.git"
REPO_DIR = "/opt/cryptobot-repo"
APP_DIR = "/opt/cryptobot"
SHA_FILE = os.path.join(APP_DIR, ".last_github_sha")
BASE_APK = os.path.join(APP_DIR, "base_template.apk")
LIVE_APK = os.path.join(APP_DIR, "Crypto_Bot_v2_50.apk")
KEYSTORE = os.path.join(APP_DIR, "release-key.jks")
VERSION_FILE = os.path.join(APP_DIR, "version.json")


def run_cmd(cmd, cwd=None):
    res = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def rebuild_and_sign_apk(html_bytes: bytes) -> bool:
    if not os.path.exists(BASE_APK) or not os.path.exists(KEYSTORE):
        print("[AutoSync] Missing base_template.apk or release-key.jks")
        return False

    raw_apk = "/tmp/cb_repack_raw.apk"
    aligned_apk = "/tmp/cb_repack_aligned.apk"
    signed_apk = "/tmp/cb_repack_signed.apk"

    try:
        with zipfile.ZipFile(BASE_APK, "r") as zin:
            with zipfile.ZipFile(raw_apk, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename.startswith("META-INF/"):
                        continue
                    if item.filename == "assets/index.html":
                        continue
                    data = zin.read(item.filename)
                    # Keep resources.arsc uncompressed if it was stored uncompressed
                    zout.writestr(item, data)
                zout.writestr("assets/index.html", html_bytes)

        code, out, err = run_cmd(["zipalign", "-f", "-p", "4", raw_apk, aligned_apk])
        if code != 0:
            print(f"[AutoSync] zipalign failed: {err}")
            return False

        code, out, err = run_cmd([
            "apksigner", "sign",
            "--ks", KEYSTORE,
            "--ks-pass", "pass:android",
            "--key-pass", "pass:android",
            "--out", signed_apk,
            aligned_apk,
        ])
        if code != 0:
            print(f"[AutoSync] apksigner failed: {err}")
            return False

        shutil.move(signed_apk, LIVE_APK)
        os.chmod(LIVE_APK, 0o644)
        print("[AutoSync] Successfully rebuilt and signed Crypto_Bot_v2_50.apk")
        return True
    except Exception as e:
        print(f"[AutoSync] Exception rebuilding APK: {e}")
        return False


def sync_once() -> None:
    if not os.path.exists( os.path.join(REPO_DIR, ".git") ):
        os.makedirs(REPO_DIR, exist_ok=True)
        run_cmd(["git", "clone", REPO_URL, REPO_DIR])

    code, _, err = run_cmd(["git", "fetch", "origin", "main"], cwd=REPO_DIR)
    if code != 0:
        return

    code, remote_sha, _ = run_cmd(["git", "rev-parse", "origin/main"], cwd=REPO_DIR)
    if code != 0 or not remote_sha:
        return

    last_sha = ""
    if os.path.exists(SHA_FILE):
        with open(SHA_FILE, "r", encoding="utf-8") as f:
            last_sha = f.read().strip()

    if not last_sha:
        with open(SHA_FILE, "w", encoding="utf-8") as f:
            f.write(remote_sha)
        return

    if remote_sha == last_sha:
        return

    print(f"[AutoSync] New GitHub commit detected: {last_sha[:7]} -> {remote_sha[:7]}")
    _, diff_out, _ = run_cmd(["git", "diff", "--name-only", last_sha, remote_sha], cwd=REPO_DIR)
    changed_files = set(diff_out.splitlines())
    _, commit_msg, _ = run_cmd(["git", "log", "-1", "--pretty=%s", remote_sha], cwd=REPO_DIR)

    run_cmd(["git", "reset", "--hard", "origin/main"], cwd=REPO_DIR)

    need_restart = False
    if "server/bot_engine.py" in changed_files:
        src = os.path.join(REPO_DIR, "server", "bot_engine.py")
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(APP_DIR, "bot_engine.py"))
            need_restart = True
            print("[AutoSync] Updated bot_engine.py")

    if "server/app.py" in changed_files:
        src = os.path.join(REPO_DIR, "server", "app.py")
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(APP_DIR, "app.py"))
            need_restart = True
            print("[AutoSync] Updated app.py")

    ui_changed = (
        "android/app/src/main/assets/index.html" in changed_files
        or "server/dashboard.html" in changed_files
        or "server/version.json" in changed_files
    )

    if ui_changed:
        idx_path = os.path.join(REPO_DIR, "android", "app", "src", "main", "assets", "index.html")
        dash_path = os.path.join(REPO_DIR, "server", "dashboard.html")
        chosen_html = idx_path if "android/app/src/main/assets/index.html" in changed_files else (dash_path if os.path.exists(dash_path) else idx_path)

        if os.path.exists(chosen_html):
            with open(chosen_html, "r", encoding="utf-8") as f:
                html_text = f.read()

            live_ver = {"version_code": 267, "version_name": "2.67"}
            if os.path.exists(VERSION_FILE):
                try:
                    with open(VERSION_FILE, "r", encoding="utf-8") as vf:
                        live_ver = json.load(vf)
                except Exception:
                    pass

            repo_ver_file = os.path.join(REPO_DIR, "server", "version.json")
            repo_code = 0
            if os.path.exists(repo_ver_file):
                try:
                    with open(repo_ver_file, "r", encoding="utf-8") as rvf:
                        repo_code = int(json.load(rvf).get("version_code", 0))
                except Exception:
                    pass

            cur_code = int(live_ver.get("version_code", 267))
            new_code = max(cur_code + 1, repo_code)
            new_name = f"{new_code / 100.0:.2f}"

            html_text = re.sub(
                r"let\s+localCode\s*=\s*\d+\s*;",
                f"let localCode = {new_code};",
                html_text,
            )
            html_bytes = html_text.encode("utf-8")

            with open(os.path.join(APP_DIR, "dashboard.html"), "wb") as df:
                df.write(html_bytes)

            if rebuild_and_sign_apk(html_bytes):
                new_ver_obj = {
                    "version_code": new_code,
                    "version_name": new_name,
                    "apk_url": "https://webrelax.pro/cryptobot/Crypto_Bot_v2_50.apk",
                    "changelog": commit_msg or f"Автообновление v{new_name}",
                }
                with open(VERSION_FILE, "w", encoding="utf-8") as vf:
                    json.dump(new_ver_obj, vf, ensure_ascii=False, indent=2)
                print(f"[AutoSync] Published new APK version v{new_name} (#{new_code})")

    if need_restart:
        run_cmd(["systemctl", "restart", "cryptobot.service"])
        print("[AutoSync] Restarted cryptobot.service")

    with open(SHA_FILE, "w", encoding="utf-8") as f:
        f.write(remote_sha)


def main():
    print("[AutoSync] Starting GitHub -> VPS & APK Auto-Sync daemon...")
    while True:
        try:
            sync_once()
        except Exception as e:
            print(f"[AutoSync] Loop error: {e}")
        time.sleep(15)


if __name__ == "__main__":
    main()
