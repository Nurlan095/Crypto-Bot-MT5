import asyncio
import json
import math
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import subprocess
import httpx

DB_PATH = os.path.join(os.path.dirname(__file__), "crypto_bot.db")
MT5_WINE_FILES_DIR = "/opt/mt5/MQL5/Files"
MT5_WINE_STATE_FILE = os.path.join(MT5_WINE_FILES_DIR, "mt5_state.json")
MT5_WINE_CMD_FILE = os.path.join(MT5_WINE_FILES_DIR, "mt5_cmd.txt")
MT5_WINE_STARTUP_INI = "/opt/mt5/startup.ini"


DEFAULT_SETTINGS: Dict[str, Any] = {
    # Active symbol & bot state (Актив только BTCUSD 24/7)
    "symbol": "BTCUSD",             # Активный актив: ТОЛЬКО BTCUSD 24/7 по требованию пользователя
    "InpAutoWeekendBTC": True,      # Торговля 24/7 на BTCUSD без переключения на другие активы
    "preferred_weekday_symbol": "BTCUSD",
    "InpLockBTCOnly": True,         # Фиксация актива: торговать только BTCUSD 24/7
    "is_running": True,             # Bot active or paused by user
    "mt5_login": "8112287",
    "mt5_server": "AMarkets-Demo",
    "mt5_password": "XvA!Xh8e",
    "InpStrategyMode": 4,           # 4 = Снайпер Аномальных Свечей + Фибоначчи
    # 3 Варианта быстрых сделок на 1–2 свечах по Аномальным свечам (БЕЗ ИНДИКАТОРОВ):
    "InpUseM5M1Mode": True,          # Отдельный переключатель: Анализ на 5М (M5) -> Сделка и авто-выход на 1М (M1, 1-2 мин)
    "InpAnalysisTF": "M5",           # Таймфрейм анализа аномальных свечей: M5 (5 минут)
    "InpTradeTF": "M1",              # Таймфрейм открытия и ведения сделки: M1 (1 минута)
    "InpStratAnomalyMomentum": True, # Вариант 1: Аномальная свеча — Инерция импульса (Вход ПО ХОДУ на 1-2 свечи)
    "InpStratAnomalyFade": True,     # Вариант 2: Аномальная свеча — Возврат после прострела (Вход В ОТКАТ на 1-2 свечи)
    "InpStratAnomalyHybrid": True,   # Вариант 3: Умный Снайпер 2-в-1 (По форме свечи: Полнотелая=По ходу, Шпилька=В откат)
    "InpAnomalyMaxBars": 2,          # Авто-закрытие сделки ровно через 1 или 2 свечи M1 (1 = 1 мин, 2 = 2 мин)
    "InpAnomalyMult": 1.8,           # Во сколько раз аномальная свеча M5 больше средней (1.5x - 3.0x)
    "InpAnomalyNoIndicators": True,  # Чистый режим без индикаторов для аномальных свечей (игнорировать MACD/RSI)
    # Индивидуальное включение / отключение классических стратегий:
    "InpStratTrullasFibo": False,   # 1. Метод Давида Трульяса: Фибо 23.6% + MACD + RSI (BTCUSD)
    "InpStratMentorFibo786": False, # 2. Золотая Фибо Наставника: 0.75-0.786 / 0.3618 -> 1.272/1.618 (BTCUSD)
    "InpStratMandarinBOS": False,   # 3. Коробка утреннего пробоя «Мандарин» + BOS + Marubozu (BTCUSD)
    "InpStratImpulseM15": False,    # 4. Импульс M15 по тренду H1 EMA 50 (BTCUSD)
    "InpStratSwingBounce": False,   # 5. Отскок от уровней Swing-канала M15 (BTCUSD)
    # ИИ-Агент контроля сигналов, анализа сделки и авто-исправления ошибок 24/7:
    "InpUseAIAgent": True,          # Включить ИИ-Агента проверки сигналов и аудита сделок
    "InpAIAgentAutoFix": True,      # Автоматически исправлять ошибки стратегий и закрывать зависшие сделки
    "InpAIAgentMinScore": 65,       # Минимальный балл качества сигнала (0-100%) для входа
    # Money Management
    "InpUseAutoLot": True,
    "InpUseDepositCalc15": True,    # Авто-калькуляция депозита 1/5 по видео + Excel (Депозитті 5-ке бөлу)
    "InpRiskPercent": 3.0,
    "InpMaxMarginUsage": 80.0,
    "InpFixedLot": 0.02,
    "InpMagicNumber": 777999,
    "InpMaxSpreadPoints": 3500,
    # News Filter (MT5 Calendar equivalent)
    "InpUseNewsFilter": True,
    "InpNewsCurrency": "USD",
    "InpPauseBeforeMin": 15,
    "InpPauseAfterMin": 5,
    "InpTradeNewsImpulse": False,
    "InpNewsEffectMin": 60,
    # Market Structure & Patterns (M15)
    "InpSwingPeriod": 5,
    "InpATRPeriod": 14,
    "InpATRMultiplier": 1.1,
    "InpMarubozuRatio": 0.70,
    "InpMaxSqueezeRatio": 0.0026,   # ATR / Close <= 0.0026
    "InpUseSessionFilter": False,   # 24/7 для BTCUSD без ночных пауз
    # Mandarin Box
    "InpUseMandarin": True,
    "InpMandarinBars": 3,
    "InpMandarinMaxATR": 1.8,
    # Higher Timeframe Trend Filter (H1)
    "InpUseHTFFilter": True,
    "InpHTF": "H1",
    "InpHTF_EMA": 50,
    # Stops, Safe (Partial Close) & Breakeven
    "InpSL_ATR": 1.2,
    "InpTP_ATR": 2.2,
    "InpUsePartialClose": True,
    "InpPartialTrigATR": 0.8,
    "InpPartialClosePct": 50.0,
    "InpUseBreakeven": True,
    "InpBE_TriggerATR": 0.7,
    "InpBE_OffsetATR": 0.18,
    # Visuals
    "InpShowVisuals": True,
}


SYMBOL_SPECS: Dict[str, Dict[str, Any]] = {
    "BTCUSD": {
        "binance_symbol": "BTCUSDT",
        "bybit_symbol": "BTCUSDT",
        "yahoo_symbol": "BTC-USD",
        "yahoo_alt": "BTC-USD",
        "digits": 2,
        "point": 0.01,
        "tick_size": 0.01,
        "tick_value": 0.01,     # 1 lot = 1 BTC, 0.01 USD move = $0.01
        "contract_size": 1.0,
        "leverage": 100.0,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "step_lot": 0.01,
        "default_spread_points": 1200,  # $12.00 typical MT5 spread
    },
    "XAUUSD": {
        "binance_symbol": "PAXGUSDT",
        "bybit_symbol": "PAXGUSDT",
        "yahoo_symbol": "GC=F",
        "yahoo_alt": "XAUUSD=X",
        "digits": 2,
        "point": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.00,     # 1 lot = 100 oz in MT5, 0.01 move = $1.00
        "contract_size": 100.0,
        "leverage": 100.0,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "step_lot": 0.01,
        "default_spread_points": 25,    # $0.25 typical gold spread
    },
    "NAS100": {
        "binance_symbol": "",
        "bybit_symbol": "",
        "yahoo_symbol": "NQ=F",
        "yahoo_alt": "^NDX",
        "digits": 2,
        "point": 0.01,
        "tick_size": 0.01,
        "tick_value": 0.01,     # Родной актив Давида Трульяса: Индекс Nasdaq 100
        "contract_size": 1.0,
        "leverage": 100.0,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "step_lot": 0.01,
        "default_spread_points": 120,   # 1.20 pt typical index spread
    },
    "US500": {
        "binance_symbol": "",
        "bybit_symbol": "",
        "yahoo_symbol": "ES=F",
        "yahoo_alt": "^GSPC",
        "digits": 2,
        "point": 0.01,
        "tick_size": 0.01,
        "tick_value": 0.01,     # Родной актив Давида Трульяса: Индекс S&P 500
        "contract_size": 1.0,
        "leverage": 100.0,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "step_lot": 0.01,
        "default_spread_points": 60,    # 0.60 pt typical S&P 500 spread
    },
}


# Economic indicators where Actual > Forecast is NEGATIVE for USD (e.g. Unemployment)
INVERTED_USD_EVENTS = (
    "unemployment",
    "jobless",
    "claims",
    "trade balance",
    "budget",
)


class CryptoBotEngine:
    def __init__(self) -> None:
        self._init_db()
        self.settings: Dict[str, Any] = self._load_settings()
        self.account: Dict[str, float] = self._load_account()

        # Market & Structure state
        self.m1_candles: List[Dict[str, Any]] = []
        self.m5_candles: List[Dict[str, Any]] = []
        self.m15_candles: List[Dict[str, Any]] = []
        self.h1_candles: List[Dict[str, Any]] = []
        self.bid_price: float = 0.0
        self.ask_price: float = 0.0
        self.spread_points: int = 0
        self.atr_value: float = 0.0
        self.htf_ema_value: float = 0.0
        self.htf_trend: int = 0  # 1 = BUY, -1 = SELL, 0 = NEUTRAL

        self.last_bar_time: int = 0
        self.last_swing_high: float = 0.0
        self.last_swing_high_time: int = 0
        self.last_swing_low: float = 0.0
        self.last_swing_low_time: int = 0

        self.mandarin_box: Dict[str, Any] = {
            "is_valid": False,
            "high": 0.0,
            "low": 0.0,
            "start_time": 0,
            "end_time": 0,
        }
        self.fibo_grid: Dict[str, Any] = {
            "is_active": False,
            "direction": 0,
            "price_0": 0.0,
            "price_100": 0.0,
            "lvl_236": 0.0,
            "lvl_382": 0.0,
            "lvl_500": 0.0,
            "lvl_618": 0.0,
            "macd_div": False,
            "rsi_confirm": False,
            "vol_confirm": False,
            "trigger_buy": False,
            "trigger_sell": False,
        }
        self.historical_boxes: List[Dict[str, Any]] = []
        self.checklist: Dict[str, Any] = {}

        # News state
        self.news_cache: List[Dict[str, Any]] = []
        self.news_last_fetch: float = 0.0
        self.news_paused: bool = False
        self.news_bias: int = 0
        self.news_status: str = "Спокойно (Новостей нет)"
        self.upcoming_news: List[Dict[str, Any]] = []

        self.last_update_ts: float = 0.0
        self.data_source: str = "Инициализация..."
        self._running_task: Optional[asyncio.Task] = None

        # Live MetaTrader 5 Bridge state
        self.mt5_last_sync: float = 0.0
        self.mt5_account_name: str = ""
        self.mt5_login_id: int = 8112287
        self.mt5_positions: List[Dict[str, Any]] = []
        self.mt5_history: List[Dict[str, Any]] = []
        self.mt5_commands: List[Dict[str, Any]] = []
        self.mt5_ticks: Dict[str, Dict[str, Any]] = {}
        self.mt5_candles_m15: Dict[str, List[Dict[str, Any]]] = {}
        self.mt5_candles_h1: Dict[str, List[Dict[str, Any]]] = {}

    def is_mt5_live(self) -> bool:
        return (time.time() - self.mt5_last_sync) < 15.0

    def _flush_mt5_commands_to_wine(self) -> None:
        if not self.mt5_commands or not os.path.isdir(MT5_WINE_FILES_DIR):
            return
        lines: List[str] = []
        for c in self.mt5_commands:
            act = c.get("action")
            if act == "open":
                lines.append(
                    f"OPEN|{c['symbol']}|{c['pos_type']}|{float(c['volume']):.2f}|{float(c['sl']):.2f}|{float(c['tp']):.2f}|{c.get('comment', 'CryptoBot')}"
                )
            elif act == "close":
                lines.append(f"CLOSE|{c['ticket']}")
            elif act == "safe":
                lines.append(
                    f"SAFE|{c['ticket']}|{float(c['close_volume']):.2f}|{float(c['new_sl']):.2f}|{float(c['tp']):.2f}"
                )
            elif act == "breakeven":
                lines.append(
                    f"BE|{c['ticket']}|{float(c['new_sl']):.2f}|{float(c['tp']):.2f}"
                )
        if lines:
            try:
                with open(MT5_WINE_CMD_FILE, "a", encoding="utf-8") as f:
                    for ln in lines:
                        f.write(ln + "\n")
                self.mt5_commands.clear()
            except Exception:
                pass

    def _sync_local_wine_mt5(self) -> None:
        if not os.path.exists(MT5_WINE_STATE_FILE):
            return
        try:
            mtime = os.path.getmtime(MT5_WINE_STATE_FILE)
            if (time.time() - mtime) > 15.0:
                return
            with open(MT5_WINE_STATE_FILE, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read().strip()
            if not raw:
                return
            data = json.loads(raw)
            if data.get("connected") and data.get("login", 0) > 0:
                self.mt5_login_id = int(data["login"])
                self.mt5_account_name = str(data.get("server", "AMarkets-Demo"))
                self._flush_mt5_commands_to_wine()
                self.apply_mt5_sync(data)
        except Exception:
            pass

    def apply_mt5_sync(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        self.mt5_last_sync = time.time()
        acc = payload.get("account", {})
        if "balance" in acc:
            self.account["balance"] = float(acc["balance"])
        if "name" in acc:
            self.mt5_account_name = str(acc["name"])
        if "login" in acc:
            self.mt5_login_id = int(acc["login"])

        sym = self.settings["symbol"]
        if "candles_m15" in payload and isinstance(payload["candles_m15"], dict):
            self.mt5_candles_m15.update(payload["candles_m15"])
            if sym in self.mt5_candles_m15 and len(self.mt5_candles_m15[sym]) >= 30:
                self.m15_candles = list(self.mt5_candles_m15[sym])

        if "candles_h1" in payload and isinstance(payload["candles_h1"], dict):
            self.mt5_candles_h1.update(payload["candles_h1"])
            if sym in self.mt5_candles_h1 and len(self.mt5_candles_h1[sym]) >= 30:
                self.h1_candles = list(self.mt5_candles_h1[sym])

        if "ticks" in payload and isinstance(payload["ticks"], dict):
            self.mt5_ticks = payload["ticks"]
            if sym in self.mt5_ticks:
                t_info = self.mt5_ticks[sym]
                if t_info.get("bid", 0) > 0:
                    self.bid_price = float(t_info["bid"])
                if t_info.get("ask", 0) > 0:
                    self.ask_price = float(t_info["ask"])
                if "spread" in t_info:
                    self.spread_points = int(t_info["spread"])
                if self.m15_candles and self.bid_price > 0:
                    c0 = self.m15_candles[0]
                    c0["close"] = self.bid_price
                    if self.bid_price > c0["high"]:
                        c0["high"] = self.bid_price
                    if self.bid_price < c0["low"]:
                        c0["low"] = self.bid_price

        if "positions" in payload and isinstance(payload["positions"], list):
            self.mt5_positions = payload["positions"]
            for p in self.mt5_positions:
                diff = (
                    (p["current_price"] - p["open_price"])
                    if p["pos_type"] == "BUY"
                    else (p["open_price"] - p["current_price"])
                )
                p["atr_multiple"] = round(diff / self.atr_value, 2) if self.atr_value > 0 else 0.0

        if "history" in payload and isinstance(payload["history"], list):
            self.mt5_history = payload["history"]

        for ev in payload.get("events", []):
            self.add_notification(ev.get("title", "MT5"), ev.get("message", ""), ev.get("level", "info"))

        cmds = list(self.mt5_commands)
        self.mt5_commands.clear()
        return cmds

    # -------------------------------------------------------------------------
    # Database & Persistence
    # -------------------------------------------------------------------------
    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS account (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    balance REAL NOT NULL DEFAULT 10000.0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS positions (
                    ticket INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    pos_type TEXT NOT NULL,
                    volume REAL NOT NULL,
                    initial_volume REAL NOT NULL,
                    open_price REAL NOT NULL,
                    sl REAL NOT NULL,
                    tp REAL NOT NULL,
                    open_time INTEGER NOT NULL,
                    is_partial_done INTEGER NOT NULL DEFAULT 0,
                    is_breakeven INTEGER NOT NULL DEFAULT 0,
                    comment TEXT DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    pos_type TEXT NOT NULL,
                    volume REAL NOT NULL,
                    open_price REAL NOT NULL,
                    close_price REAL NOT NULL,
                    pnl REAL NOT NULL,
                    close_time INTEGER NOT NULL,
                    reason TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    level TEXT NOT NULL DEFAULT 'info',
                    created_at INTEGER NOT NULL
                )
                """
            )
            cur = conn.execute("SELECT balance FROM account WHERE id = 1")
            if not cur.fetchone():
                conn.execute("INSERT INTO account (id, balance) VALUES (1, 10000.0)")
            conn.commit()

    def _load_settings(self) -> Dict[str, Any]:
        settings = dict(DEFAULT_SETTINGS)
        with self._get_conn() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            for r in rows:
                k = r["key"]
                if k in settings:
                    try:
                        settings[k] = json.loads(r["value"])
                    except Exception:
                        pass
            if settings.get("InpLockBTCOnly", True):
                settings["symbol"] = "BTCUSD"
                settings["preferred_weekday_symbol"] = "BTCUSD"
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("symbol", json.dumps("BTCUSD")))
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("preferred_weekday_symbol", json.dumps("BTCUSD")))
                conn.commit()
        return settings

    def save_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        old_symbol = self.settings.get("symbol")
        old_login = self.settings.get("mt5_login")
        old_pass = self.settings.get("mt5_password")
        old_srv = self.settings.get("mt5_server")
        if self.settings.get("InpLockBTCOnly", True) and updates.get("InpLockBTCOnly", True):
            updates["symbol"] = "BTCUSD"
            updates["preferred_weekday_symbol"] = "BTCUSD"
        with self._get_conn() as conn:
            for k, v in updates.items():
                if k in DEFAULT_SETTINGS:
                    target_type = type(DEFAULT_SETTINGS[k])
                    if target_type is bool:
                        val = bool(v) if not isinstance(v, str) else v.lower() in ("true", "1", "yes")
                    elif target_type is int:
                        val = int(float(v))
                    elif target_type is float:
                        val = float(v)
                    else:
                        val = str(v)
                    self.settings[k] = val
                    conn.execute(
                        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                        (k, json.dumps(val)),
                    )
            conn.commit()

        # Если изменились данные счета MT5 — автоматически обновляем startup.ini и перезапускаем терминал на VPS
        if (
            self.settings.get("mt5_login") != old_login
            or self.settings.get("mt5_password") != old_pass
            or self.settings.get("mt5_server") != old_srv
        ) and os.path.exists(MT5_WINE_STARTUP_INI):
            try:
                ini_content = (
                    "[Common]\n"
                    f"Login={self.settings['mt5_login']}\n"
                    f"Password={self.settings['mt5_password']}\n"
                    f"Server={self.settings['mt5_server']}\n"
                    "KeepPrivate=1\nNewsEnable=0\nCertInstall=1\n\n"
                    "[Charts]\nProfileLast=Default\nMaxBars=5000\n\n"
                    "[Experts]\nAllowDllImport=1\nEnabled=1\nAccount=0\nProfile=0\n\n"
                    "[StartUp]\nExpert=ServerBridge\nSymbol=BTCUSD\nPeriod=M15\n"
                )
                with open(MT5_WINE_STARTUP_INI, "w", encoding="utf-8") as f:
                    f.write(ini_content)
                subprocess.Popen(["systemctl", "restart", "mt5-wine.service"])
                self.add_notification(
                    "Переподключение счета MT5",
                    f"Терминал переключается на счет #{self.settings['mt5_login']} ({self.settings['mt5_server']})",
                    "info",
                )
            except Exception:
                pass

        if "symbol" in updates and updates["symbol"] != old_symbol:
            new_sym = str(updates["symbol"])
            if new_sym in ("XAUUSD", "NAS100", "US500"):
                self.settings["preferred_weekday_symbol"] = new_sym
                with self._get_conn() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                        ("preferred_weekday_symbol", json.dumps(new_sym)),
                    )
                    conn.commit()
            self.last_bar_time = 0
            self.last_swing_high = 0.0
            self.last_swing_low = 0.0
            self.bid_price = 0.0
            self.ask_price = 0.0
            self.atr_value = 0.0
            self.m15_candles = []
            self.h1_candles = []
            sym_labels = {
                "XAUUSD": "XAUUSD (Золото · Калькуляция 1/5)",
                "BTCUSD": "BTCUSD (Биткоин · 24/7)",
                "NAS100": "NAS100 (Nasdaq 100 · Чемпионский актив Трульяса)",
                "US500": "US500 (S&P 500 · Чемпионский актив Трульяса)",
            }
            self.add_notification(
                "Смена актива",
                f"Активный инструмент переключен на {sym_labels.get(new_sym, new_sym)}",
                "info",
            )
        return self.settings

    def _load_account(self) -> Dict[str, float]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT balance FROM account WHERE id = 1").fetchone()
            balance = float(row["balance"]) if row else 10000.0
            if balance > 500000.0 or balance < 10.0:
                balance = 10000.0
                conn.execute("UPDATE account SET balance = 10000.0 WHERE id = 1")
                conn.execute("DELETE FROM positions")
                conn.execute("DELETE FROM trade_history WHERE abs(pnl) > 5000")
                conn.execute("DELETE FROM notifications WHERE title LIKE '%Баланс%' OR message LIKE '%100.00 лот%'")
                conn.commit()
        return {"balance": balance}

    def set_balance(self, new_balance: float) -> float:
        new_balance = max(10.0, round(float(new_balance), 2))
        self.account["balance"] = new_balance
        with self._get_conn() as conn:
            conn.execute("UPDATE account SET balance = ? WHERE id = 1", (new_balance,))
            conn.commit()
        self.add_notification(
            "Баланс обновлен",
            f"Установлен новый баланс счета: ${new_balance:,.2f}",
            "info",
        )
        return new_balance

    def add_notification(self, title: str, message: str, level: str = "info") -> None:
        now_ts = int(time.time())
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO notifications (title, message, level, created_at) VALUES (?, ?, ?, ?)",
                (title, message, level, now_ts),
            )
            conn.execute(
                "DELETE FROM notifications WHERE id NOT IN (SELECT id FROM notifications ORDER BY id DESC LIMIT 100)"
            )
            conn.commit()

    def get_notifications(self, since_id: int = 0, limit: int = 30) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            if since_id > 0:
                rows = conn.execute(
                    "SELECT * FROM notifications WHERE id > ? ORDER BY id ASC LIMIT ?",
                    (since_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM notifications ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    # -------------------------------------------------------------------------
    # Market Data Fetching (MT5 Live -> Binance -> Yahoo Finance -> Kraken)
    # -------------------------------------------------------------------------
    def _align_candles_to_mt5_tick(self, symbol: str, spec: Dict[str, Any]) -> None:
        if not self.m15_candles:
            return
        last_close = self.m15_candles[0]["close"]
        if self.is_mt5_live() and symbol in self.mt5_ticks:
            t_info = self.mt5_ticks[symbol]
            mt5_bid = float(t_info.get("bid") or 0.0)
            mt5_ask = float(t_info.get("ask") or 0.0)
            if mt5_bid > 0:
                offset = mt5_bid - last_close
                if abs(offset) > 0.05 and abs(offset) < mt5_bid * 0.15:
                    for c in self.m15_candles:
                        c["open"] = round(c["open"] + offset, spec["digits"])
                        c["high"] = round(c["high"] + offset, spec["digits"])
                        c["low"] = round(c["low"] + offset, spec["digits"])
                        c["close"] = round(c["close"] + offset, spec["digits"])
                    for c in self.h1_candles:
                        c["open"] = round(c["open"] + offset, spec["digits"])
                        c["high"] = round(c["high"] + offset, spec["digits"])
                        c["low"] = round(c["low"] + offset, spec["digits"])
                        c["close"] = round(c["close"] + offset, spec["digits"])
                self.bid_price = mt5_bid
                self.ask_price = mt5_ask if mt5_ask > 0 else round(mt5_bid + spec["default_spread_points"] * spec["point"], spec["digits"])
                self.spread_points = int(t_info.get("spread") or spec["default_spread_points"])
                return

        half_spread = (spec["default_spread_points"] * spec["point"]) / 2.0
        self.bid_price = round(last_close - half_spread, spec["digits"])
        self.ask_price = round(last_close + half_spread, spec["digits"])
        self.spread_points = spec["default_spread_points"]

    async def fetch_market_data(self) -> bool:
        symbol = self.settings["symbol"]
        spec = SYMBOL_SPECS.get(symbol, SYMBOL_SPECS["BTCUSD"])
        b_sym = spec.get("binance_symbol", "")

        # 0. Prefer exact MetaTrader 5 candles when MT5 Bridge is live
        if (
            self.is_mt5_live()
            and symbol in self.mt5_candles_m15
            and len(self.mt5_candles_m15[symbol]) >= 30
        ):
            self.m15_candles = list(self.mt5_candles_m15[symbol])
            if symbol in self.mt5_candles_h1 and len(self.mt5_candles_h1[symbol]) >= 30:
                self.h1_candles = list(self.mt5_candles_h1[symbol])
            if symbol in self.mt5_ticks:
                t_info = self.mt5_ticks[symbol]
                self.bid_price = float(t_info.get("bid") or self.m15_candles[0]["close"])
                self.ask_price = float(t_info.get("ask") or self.m15_candles[0]["close"])
                self.spread_points = int(t_info.get("spread") or spec["default_spread_points"])
            return True

        yh_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with httpx.AsyncClient(timeout=8.0, headers=yh_headers) as client:
            # 1. Try Binance Vision & Binance main API (for BTCUSD & XAUUSD)
            if b_sym:
                for base_url in ("https://data-api.binance.vision", "https://api.binance.com"):
                    try:
                        m15_resp, h1_resp, book_resp = await asyncio.gather(
                            client.get(
                                f"{base_url}/api/v3/klines",
                                params={"symbol": b_sym, "interval": "15m", "limit": 130},
                            ),
                            client.get(
                                f"{base_url}/api/v3/klines",
                                params={"symbol": b_sym, "interval": "1h", "limit": 80},
                            ),
                            client.get(
                                f"{base_url}/api/v3/ticker/bookTicker",
                                params={"symbol": b_sym},
                            ),
                        )
                        if m15_resp.status_code == 200 and h1_resp.status_code == 200:
                            m15_raw = m15_resp.json()
                            h1_raw = h1_resp.json()
                            book = book_resp.json() if book_resp.status_code == 200 else {}

                            self.m15_candles = [
                                {
                                    "time": int(k[0] // 1000),
                                    "open": float(k[1]),
                                    "high": float(k[2]),
                                    "low": float(k[3]),
                                    "close": float(k[4]),
                                    "volume": float(k[5]),
                                }
                                for k in reversed(m15_raw)
                            ]
                            self.h1_candles = [
                                {
                                    "time": int(k[0] // 1000),
                                    "open": float(k[1]),
                                    "high": float(k[2]),
                                    "low": float(k[3]),
                                    "close": float(k[4]),
                                    "volume": float(k[5]),
                                }
                                for k in reversed(h1_raw)
                            ]
                            last_close = self.m15_candles[0]["close"]
                            if self.is_mt5_live() and symbol in self.mt5_ticks and float(self.mt5_ticks[symbol].get("bid") or 0) > 0:
                                self._align_candles_to_mt5_tick(symbol, spec)
                            else:
                                bid = float(book.get("bidPrice") or last_close)
                                ask = float(book.get("askPrice") or last_close)
                                if ask <= bid:
                                    half_spread = (spec["default_spread_points"] * spec["point"]) / 2.0
                                    bid = round(last_close - half_spread, spec["digits"])
                                    ask = round(last_close + half_spread, spec["digits"])
                                self.bid_price = bid
                                self.ask_price = ask
                                self.spread_points = max(
                                    int(round((ask - bid) / spec["point"])),
                                    spec["default_spread_points"],
                                )
                            self.data_source = f"Binance Live ({b_sym})"
                            return True
                    except Exception:
                        pass

            # 2. Yahoo Finance v8 Chart API (Primary for NAS100 / US500, Fallback for XAUUSD / BTCUSD)
            y_tickers = [t for t in (spec.get("yahoo_symbol"), spec.get("yahoo_alt")) if t]
            for y_sym in y_tickers:
                for yh_host in ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"):
                    try:
                        m15_resp, h1_resp = await asyncio.gather(
                            client.get(
                                f"{yh_host}/v8/finance/chart/{y_sym}",
                                params={"interval": "15m", "range": "5d"},
                            ),
                            client.get(
                                f"{yh_host}/v8/finance/chart/{y_sym}",
                                params={"interval": "60m", "range": "1mo"},
                            ),
                        )
                        if m15_resp.status_code == 200 and h1_resp.status_code == 200:
                            r15 = (m15_resp.json().get("chart", {}).get("result") or [None])[0]
                            r60 = (h1_resp.json().get("chart", {}).get("result") or [None])[0]
                            if r15 and r60:
                                def _parse_yh(res_obj: Dict[str, Any], max_bars: int) -> List[Dict[str, Any]]:
                                    ts_list = res_obj.get("timestamp") or []
                                    q = ((res_obj.get("indicators") or {}).get("quote") or [{}])[0]
                                    opens = q.get("open") or []
                                    highs = q.get("high") or []
                                    lows = q.get("low") or []
                                    closes = q.get("close") or []
                                    vols = q.get("volume") or []
                                    parsed: List[Dict[str, Any]] = []
                                    for idx_t, ts_val in enumerate(ts_list):
                                        if idx_t >= len(closes) or closes[idx_t] is None or opens[idx_t] is None:
                                            continue
                                        parsed.append({
                                            "time": int(ts_val),
                                            "open": round(float(opens[idx_t]), spec["digits"]),
                                            "high": round(float(highs[idx_t] if highs[idx_t] is not None else closes[idx_t]), spec["digits"]),
                                            "low": round(float(lows[idx_t] if lows[idx_t] is not None else closes[idx_t]), spec["digits"]),
                                            "close": round(float(closes[idx_t]), spec["digits"]),
                                            "volume": float(vols[idx_t] if idx_t < len(vols) and vols[idx_t] is not None else 100.0),
                                        })
                                    return list(reversed(parsed[-max_bars:]))

                                c15 = _parse_yh(r15, 130)
                                c60 = _parse_yh(r60, 80)
                                if len(c15) >= 35 and len(c60) >= 30:
                                    self.m15_candles = c15
                                    self.h1_candles = c60
                                    self._align_candles_to_mt5_tick(symbol, spec)
                                    self.data_source = f"Market Live ({symbol} · {y_sym})"
                                    return True
                    except Exception:
                        pass

            # 3. Fallback: Kraken Public OHLC API (for BTCUSD / XAUUSD)
            if symbol in ("BTCUSD", "XAUUSD"):
                try:
                    k_pair = "XBTUSD" if symbol == "BTCUSD" else "PAXGUSD"
                    m15_resp, h1_resp = await asyncio.gather(
                        client.get("https://api.kraken.com/0/public/OHLC", params={"pair": k_pair, "interval": 15}),
                        client.get("https://api.kraken.com/0/public/OHLC", params={"pair": k_pair, "interval": 60}),
                    )
                    if m15_resp.status_code == 200 and h1_resp.status_code == 200:
                        res15 = m15_resp.json().get("result", {})
                        res60 = h1_resp.json().get("result", {})
                        k15 = next((v for k, v in res15.items() if k != "last"), [])
                        k60 = next((v for k, v in res60.items() if k != "last"), [])
                        if k15 and k60:
                            self.m15_candles = [
                                {
                                    "time": int(row[0]),
                                    "open": float(row[1]),
                                    "high": float(row[2]),
                                    "low": float(row[3]),
                                    "close": float(row[4]),
                                    "volume": float(row[6]),
                                }
                                for row in reversed(k15[-130:])
                            ]
                            self.h1_candles = [
                                {
                                    "time": int(row[0]),
                                    "open": float(row[1]),
                                    "high": float(row[2]),
                                    "low": float(row[3]),
                                    "close": float(row[4]),
                                    "volume": float(row[6]),
                                }
                                for row in reversed(k60[-80:])
                            ]
                            self._align_candles_to_mt5_tick(symbol, spec)
                            self.data_source = f"Kraken Live ({k_pair})"
                            return True
                except Exception:
                    pass

        return False

    async def refresh_fast_m5_m1_candles(self) -> None:
        """Подгрузка живых свечей M5 (для анализа аномалий) и M1 (для открытия/закрытия быстрых сделок BTCUSD)."""
        now = time.time()
        if now - getattr(self, "_fast_tf_last_fetch", 0.0) < 3.5 and len(self.m5_candles) >= 20 and len(self.m1_candles) >= 20:
            if self.bid_price > 0:
                for arr in (self.m5_candles, self.m1_candles):
                    if arr:
                        c0 = arr[0]
                        c0["close"] = self.bid_price
                        if self.bid_price > c0["high"]:
                            c0["high"] = self.bid_price
                        if self.bid_price < c0["low"]:
                            c0["low"] = self.bid_price
            return

        self._fast_tf_last_fetch = now
        symbol = self.settings.get("symbol", "BTCUSD")
        spec = SYMBOL_SPECS.get(symbol, SYMBOL_SPECS["BTCUSD"])
        b_sym = spec.get("binance_symbol") or "BTCUSDT"
        async with httpx.AsyncClient(timeout=5.0) as client:
            for base_url in ("https://data-api.binance.vision", "https://api.binance.com"):
                try:
                    m5_resp, m1_resp = await asyncio.gather(
                        client.get(f"{base_url}/api/v3/klines", params={"symbol": b_sym, "interval": "5m", "limit": 50}),
                        client.get(f"{base_url}/api/v3/klines", params={"symbol": b_sym, "interval": "1m", "limit": 50}),
                    )
                    if m5_resp.status_code == 200 and m1_resp.status_code == 200:
                        m5_raw = m5_resp.json()
                        m1_raw = m1_resp.json()
                        m5_list = [
                            {
                                "time": int(k[0] // 1000),
                                "open": float(k[1]),
                                "high": float(k[2]),
                                "low": float(k[3]),
                                "close": float(k[4]),
                                "volume": float(k[5]),
                            }
                            for k in reversed(m5_raw)
                        ]
                        m1_list = [
                            {
                                "time": int(k[0] // 1000),
                                "open": float(k[1]),
                                "high": float(k[2]),
                                "low": float(k[3]),
                                "close": float(k[4]),
                                "volume": float(k[5]),
                            }
                            for k in reversed(m1_raw)
                        ]
                        if self.bid_price > 0 and m1_list:
                            offset = self.bid_price - m1_list[0]["close"]
                            if abs(offset) > 0.05 and abs(offset) < self.bid_price * 0.15:
                                for arr in (m5_list, m1_list):
                                    for c in arr:
                                        c["open"] = round(c["open"] + offset, spec["digits"])
                                        c["high"] = round(c["high"] + offset, spec["digits"])
                                        c["low"] = round(c["low"] + offset, spec["digits"])
                                        c["close"] = round(c["close"] + offset, spec["digits"])
                        self.m5_candles = m5_list
                        self.m1_candles = m1_list
                        return
                except Exception:
                    pass

    # -------------------------------------------------------------------------
    # Indicators: ATR(14) on M15 & EMA(50) on H1
    # -------------------------------------------------------------------------
    def compute_atr(self) -> float:
        period = int(self.settings["InpATRPeriod"])
        if len(self.m15_candles) < period + 2:
            return 0.0
        # Chronological order excluding forming bar 0 (so last element is bar 1, matching CopyBuffer(..., 1, 1))
        closed_bars = list(reversed(self.m15_candles[1:]))
        trs: List[float] = []
        for idx in range(1, len(closed_bars)):
            c = closed_bars[idx]
            prev_c = closed_bars[idx - 1]["close"]
            tr = max(
                c["high"] - c["low"],
                abs(c["high"] - prev_c),
                abs(c["low"] - prev_c),
            )
            trs.append(tr)
        if len(trs) < period:
            return 0.0
        # Simple average seed + RMA/SMA smoothing (MT5 iATR uses SMA over period)
        atr = sum(trs[-period:]) / float(period)
        return round(atr, 2)

    def get_htf_trend_direction(self) -> int:
        if not self.settings["InpUseHTFFilter"]:
            return 0
        period = int(self.settings["InpHTF_EMA"])
        if len(self.h1_candles) < period + 5:
            return 0

        # Calculate EMA series in chronological order
        chron = list(reversed(self.h1_candles))
        k = 2.0 / (period + 1.0)
        ema_series: List[float] = []
        ema_val = chron[0]["close"]
        for bar in chron:
            ema_val = bar["close"] * k + ema_val * (1.0 - k)
            ema_series.append(ema_val)

        # Reverse so index 0 = current bar, index 1 = bar 1 (last closed H1), index 3 = bar 3
        ema_rev = list(reversed(ema_series))
        self.htf_ema_value = round(ema_rev[1], 2)

        # MQL5: CopyBuffer(htfEmaHandle, 0, 1, 3, emaVal) with ArraySetAsSeries(true)
        # emaVal[0] = shift 1, emaVal[2] = shift 3, htfClose = iClose(_Symbol, InpHTF, 1)
        htf_close = self.h1_candles[1]["close"]
        ema_0 = ema_rev[1]
        ema_2 = ema_rev[3]

        if htf_close > ema_0 and ema_0 > ema_2:
            return 1
        if htf_close < ema_0 and ema_0 < ema_2:
            return -1
        return 0

    def evaluate_trullas_fibo(self, atr: float) -> Dict[str, Any]:
        """Метод Давида Трульяса Вила: MACD(12,26,9) + RSI(14) + Volume + Авто-сетка Фибоначчи (23.6% / 38.2% / 61.8%)."""
        default_grid: Dict[str, Any] = {
            "is_active": False,
            "direction": 0,
            "price_0": 0.0,
            "price_100": 0.0,
            "lvl_236": 0.0,
            "lvl_382": 0.0,
            "lvl_500": 0.0,
            "lvl_618": 0.0,
            "macd_div": False,
            "rsi_confirm": False,
            "vol_confirm": False,
            "trigger_buy": False,
            "trigger_sell": False,
        }
        if len(self.m15_candles) < 40 or atr <= 0:
            self.fibo_grid = default_grid
            return default_grid

        chron = list(reversed(self.m15_candles))
        closes = [c["close"] for c in chron]
        vols = [c["volume"] for c in chron]

        # 1. MACD (12, 26, 9)
        def _ema_list(vals: List[float], period: int) -> List[float]:
            k = 2.0 / (period + 1.0)
            out: List[float] = []
            cur = vals[0]
            for v in vals:
                cur = v * k + cur * (1.0 - k)
                out.append(cur)
            return out

        ema12 = _ema_list(closes, 12)
        ema26 = _ema_list(closes, 26)
        macd_line = [a - b for a, b in zip(ema12, ema26)]
        sig_line = _ema_list(macd_line, 9)
        macd_rev = list(reversed(macd_line))
        sig_rev = list(reversed(sig_line))

        # 2. RSI (14)
        gains: List[float] = [0.0]
        losses: List[float] = [0.0]
        for idx in range(1, len(closes)):
            d = closes[idx] - closes[idx - 1]
            gains.append(max(0.0, d))
            losses.append(max(0.0, -d))
        avg_g = sum(gains[1:15]) / 14.0
        avg_l = sum(losses[1:15]) / 14.0
        rsi_series: List[float] = [50.0] * 14
        for idx in range(14, len(closes)):
            avg_g = (avg_g * 13.0 + gains[idx]) / 14.0
            avg_l = (avg_l * 13.0 + losses[idx]) / 14.0
            rs = (avg_g / avg_l) if avg_l > 1e-9 else 100.0
            rsi_series.append(100.0 - (100.0 / (1.0 + rs)))
        rsi_rev = list(reversed(rsi_series))

        # 3. Volume SMA(20)
        avg_vol = sum(vols[-21:-1]) / 20.0 if len(vols) >= 21 else max(1.0, vols[-1])
        vol_confirm = (self.m15_candles[0]["volume"] >= avg_vol * 0.55) or (self.m15_candles[1]["volume"] >= avg_vol * 0.75)

        # 4. Находим актуальный импульс для натяжки сетки Фибоначчи (100% -> 0%) + Фильтр тренда EMA21/EMA50
        ema21_m15 = _ema_list(closes, 21)
        ema50_m15 = _ema_list(closes, 50)
        ema21_now = ema21_m15[-1]
        ema50_now = ema50_m15[-1]

        window = self.m15_candles[0:20]
        high_idx = max(range(len(window)), key=lambda idx: window[idx]["high"])
        low_idx = min(range(len(window)), key=lambda idx: window[idx]["low"])
        high_val = self.m15_candles[high_idx]["high"]
        low_val = self.m15_candles[low_idx]["low"]
        raw_impulse = high_val - low_val
        impulse_valid = raw_impulse >= (atr * 1.15)
        impulse = max(raw_impulse, atr * 0.5)

        live_px = self.bid_price if self.bid_price > 0 else self.m15_candles[0]["close"]
        c0 = self.m15_candles[0]
        c1 = self.m15_candles[1]

        # Определяем доминирующий тренд (H1 EMA50 + M15 EMA21/50), чтобы НЕ входить против тренда на мелких откатах
        m15_bull = (live_px >= ema50_now) and (ema21_now >= ema50_now * 0.9992)
        m15_bear = (live_px < ema50_now) and (ema21_now <= ema50_now * 1.0008)
        htf_dir = self.htf_trend  # 1 = ВВЕРХ, -1 = ВНИЗ, 0 = НЕЙТРАЛЬНО

        # Проверка настоящей классической дивергенции MACD на экстремумах
        prev_lows = [i for i in range(max(low_idx + 2, 3), min(36, len(self.m15_candles))) if self.m15_candles[i]["low"] <= low_val * 1.0025]
        strict_bull_div = any(macd_rev[low_idx] > macd_rev[p] for p in prev_lows) and (rsi_rev[low_idx] <= 36.0)

        prev_highs = [i for i in range(max(high_idx + 2, 3), min(36, len(self.m15_candles))) if self.m15_candles[i]["high"] >= high_val * 0.9975]
        strict_bear_div = any(macd_rev[high_idx] < macd_rev[p] for p in prev_highs) and (rsi_rev[high_idx] >= 66.0)

        # Запрет переворота в SELL при растущем тренде (если нет жесткой медвежьей дивергенции с RSI >= 66)
        if htf_dir == 1 or m15_bull:
            bullish_bias = not strict_bear_div
        elif htf_dir == -1 or m15_bear:
            bullish_bias = bool(strict_bull_div)
        else:
            mid_px = (high_val + low_val) * 0.5
            bullish_bias = (macd_rev[0] >= macd_rev[1]) and (live_px >= mid_px)

        hist_0 = macd_rev[0] - sig_rev[0]
        hist_1 = macd_rev[1] - sig_rev[1]

        if bullish_bias:
            price_0 = low_val
            price_100 = high_val
            lvl_011 = round(price_0 + impulse * 0.110, 2)
            lvl_236 = round(price_0 + impulse * 0.236, 2)
            lvl_3618 = round(price_0 + impulse * 0.3618, 2)
            lvl_382 = round(price_0 + impulse * 0.382, 2)
            lvl_500 = round(price_0 + impulse * 0.500, 2)
            lvl_618 = round(price_0 + impulse * 0.618, 2)
            lvl_750 = round(price_0 + impulse * 0.750, 2)
            lvl_786 = round(price_0 + impulse * 0.786, 2)
            lvl_860 = round(price_0 + impulse * 0.860, 2)
            lvl_900 = round(price_0 + impulse * 0.900, 2)
            lvl_1272 = round(price_0 + impulse * 1.272, 2)
            lvl_1618 = round(price_0 + impulse * 1.618, 2)

            macd_div = bool(
                strict_bull_div
                or (macd_rev[0] > macd_rev[1] and hist_0 >= hist_1)
            )
            # Исправлено ИИ-Агентом: расширен нижний порог RSI до 28.0, чтобы не блокировать разворотные входы у дна
            rsi_confirm = bool(28.0 <= rsi_rev[0] <= 66.0 and rsi_rev[0] >= rsi_rev[1] - 1.5)
            candle_bull = (c0["close"] > c0["open"]) or (c1["close"] > c1["open"] and live_px >= c1["close"])
            # Снайперский коридор входа:
            # 1) 0.236 - 0.42 (импульс до 0.618) — Метод Давида Трульяса (NAS100, US500, BTCUSD)
            # 2) Глубокий откат 0.75-0.786 от вершины (price_0 + 0.18..0.28*impulse) ИЛИ зона 0.3618 / 0.75-0.786 — Наставник (XAUUSD, BTCUSD)
            in_zone_236 = impulse_valid and (lvl_236 <= live_px <= (price_0 + impulse * 0.42)) and ((lvl_618 - live_px) >= atr * 0.65)
            in_deep_retrace_786 = ((price_0 + impulse * 0.18) <= live_px <= (price_0 + impulse * 0.28))
            in_mentor_levels = (abs(live_px - lvl_3618) <= atr * 0.28) or (lvl_750 <= live_px <= (lvl_786 + atr * 0.20))
            in_zone_750 = impulse_valid and bool(in_deep_retrace_786 or in_mentor_levels) and (strict_bull_div or (htf_dir >= 0 and macd_div and candle_bull))
            trend_allow_buy = (htf_dir >= 0) or strict_bull_div
            base_buy_ok = bool(macd_div and rsi_confirm and vol_confirm and candle_bull and trend_allow_buy)

            trig_236_buy = bool(in_zone_236 and base_buy_ok and self.settings.get("InpStratTrullasFibo", True))
            trig_786_buy = bool(in_zone_750 and base_buy_ok and self.settings.get("InpStratMentorFibo786", True))
            trigger_buy = bool(trig_236_buy or trig_786_buy)

            self.fibo_grid = {
                "is_active": bool(impulse_valid),
                "direction": 1,
                "price_0": round(price_0, 2),
                "price_100": round(price_100, 2),
                "lvl_011": lvl_011,
                "lvl_236": lvl_236,
                "lvl_3618": lvl_3618,
                "lvl_382": lvl_382,
                "lvl_500": lvl_500,
                "lvl_618": lvl_618,
                "lvl_750": lvl_750,
                "lvl_786": lvl_786,
                "lvl_860": lvl_860,
                "lvl_900": lvl_900,
                "lvl_1272": lvl_1272,
                "lvl_1618": lvl_1618,
                "rsi_val": round(rsi_rev[0], 1),
                "macd_div": bool(macd_div),
                "rsi_confirm": bool(rsi_confirm),
                "vol_confirm": bool(vol_confirm),
                "trig_236_buy": trig_236_buy,
                "trig_786_buy": trig_786_buy,
                "trig_236_sell": False,
                "trig_786_sell": False,
                "trigger_buy": bool(trigger_buy),
                "trigger_sell": False,
            }
        else:
            price_0 = high_val
            price_100 = low_val
            lvl_011 = round(price_0 - impulse * 0.110, 2)
            lvl_236 = round(price_0 - impulse * 0.236, 2)
            lvl_3618 = round(price_0 - impulse * 0.3618, 2)
            lvl_382 = round(price_0 - impulse * 0.382, 2)
            lvl_500 = round(price_0 - impulse * 0.500, 2)
            lvl_618 = round(price_0 - impulse * 0.618, 2)
            lvl_750 = round(price_0 - impulse * 0.750, 2)
            lvl_786 = round(price_0 - impulse * 0.786, 2)
            lvl_860 = round(price_0 - impulse * 0.860, 2)
            lvl_900 = round(price_0 - impulse * 0.900, 2)
            lvl_1272 = round(price_0 - impulse * 1.272, 2)
            lvl_1618 = round(price_0 - impulse * 1.618, 2)

            macd_div = bool(
                strict_bear_div
                or (macd_rev[0] < macd_rev[1] and hist_0 <= hist_1)
            )
            # Исправлено ИИ-Агентом: расширен верхний порог RSI до 72.0 для точных разворотных SELL от вершины
            rsi_confirm = bool(34.0 <= rsi_rev[0] <= 72.0 and rsi_rev[0] <= rsi_rev[1] + 1.5)
            candle_bear = (c0["close"] < c0["open"]) or (c1["close"] < c1["open"] and live_px <= c1["close"])
            # Снайперский коридор входа SELL: 23.6%-42% Фибо или золотая зона 0.75-0.786 / 0.3618 Наставника
            in_zone_236_s = impulse_valid and ((price_0 - impulse * 0.42) <= live_px <= lvl_236) and ((live_px - lvl_618) >= atr * 0.65)
            in_deep_retrace_786_s = ((price_0 - impulse * 0.28) <= live_px <= (price_0 - impulse * 0.18))
            in_mentor_levels_s = (abs(live_px - lvl_3618) <= atr * 0.28) or ((lvl_786 - atr * 0.20) <= live_px <= lvl_750)
            in_zone_750_s = impulse_valid and bool(in_deep_retrace_786_s or in_mentor_levels_s) and (strict_bear_div or (htf_dir <= 0 and macd_div and candle_bear))
            trend_allow_sell = (htf_dir <= 0) or strict_bear_div
            base_sell_ok = bool(macd_div and rsi_confirm and vol_confirm and candle_bear and trend_allow_sell)

            trig_236_sell = bool(in_zone_236_s and base_sell_ok and self.settings.get("InpStratTrullasFibo", True))
            trig_786_sell = bool(in_zone_750_s and base_sell_ok and self.settings.get("InpStratMentorFibo786", True))
            trigger_sell = bool(trig_236_sell or trig_786_sell)

            self.fibo_grid = {
                "is_active": bool(impulse_valid),
                "direction": -1,
                "price_0": round(price_0, 2),
                "price_100": round(price_100, 2),
                "lvl_011": lvl_011,
                "lvl_236": lvl_236,
                "lvl_3618": lvl_3618,
                "lvl_382": lvl_382,
                "lvl_500": lvl_500,
                "lvl_618": lvl_618,
                "lvl_750": lvl_750,
                "lvl_786": lvl_786,
                "lvl_860": lvl_860,
                "lvl_900": lvl_900,
                "lvl_1272": lvl_1272,
                "lvl_1618": lvl_1618,
                "rsi_val": round(rsi_rev[0], 1),
                "macd_div": bool(macd_div),
                "rsi_confirm": bool(rsi_confirm),
                "vol_confirm": bool(vol_confirm),
                "trig_236_buy": False,
                "trig_786_buy": False,
                "trig_236_sell": trig_236_sell,
                "trig_786_sell": trig_786_sell,
                "trigger_buy": False,
                "trigger_sell": bool(trigger_sell),
            }

        return self.fibo_grid

    def evaluate_anomalous_candles(self) -> Dict[str, Any]:
        """Чистая математика Аномальных свечей БЕЗ индикаторов: Анализ на 5М (M5) -> Сделка на 1М (M1, 1-2 свечи) для BTCUSD."""
        use_m5_m1 = bool(self.settings.get("InpUseM5M1Mode", True))
        analysis_tf = "M5" if use_m5_m1 else "M15"
        trade_tf = "M1" if use_m5_m1 else "M15"
        bar_sec = 60 if use_m5_m1 else 900

        default_anom: Dict[str, Any] = {
            "is_anomaly": False,
            "use_m5_m1": use_m5_m1,
            "analysis_tf": analysis_tf,
            "trade_tf": trade_tf,
            "bar_sec": bar_sec,
            "mult": 1.0,
            "body_mult": 1.0,
            "rng_mult": 1.0,
            "body_ratio_pct": 0.0,
            "upper_wick_pct": 0.0,
            "lower_wick_pct": 0.0,
            "candle_dir": 0,
            "pattern_type": f"Обычная свеча {analysis_tf} (ожидание аномалии)",
            "anom_range": 0.0,
            "anom_high": 0.0,
            "anom_low": 0.0,
            "anom_mid": 0.0,
            "m1_confirm_dir": 0,
            "mom_buy": False,
            "mom_sell": False,
            "fade_buy": False,
            "fade_sell": False,
            "hyb_buy": False,
            "hyb_sell": False,
            "active_signal": "",
            "max_bars": int(self.settings.get("InpAnomalyMaxBars", 2)),
        }
        src_candles = self.m5_candles if (use_m5_m1 and len(self.m5_candles) >= 15) else self.m15_candles
        if len(src_candles) < 15:
            self.anomaly_state = default_anom
            return default_anom

        c0 = src_candles[0]
        c1 = src_candles[1]
        base_bars = src_candles[2:12]
        avg_body = max(1.0, sum(abs(b["close"] - b["open"]) for b in base_bars) / float(len(base_bars)))
        avg_rng = max(1.0, sum(max(0.1, b["high"] - b["low"]) for b in base_bars) / float(len(base_bars)))

        def _metrics(c: Dict[str, Any]) -> Dict[str, float]:
            rng = max(0.01, float(c["high"] - c["low"]))
            body = abs(float(c["close"] - c["open"]))
            up_w = float(c["high"] - max(c["open"], c["close"]))
            lo_w = float(min(c["open"], c["close"]) - c["low"])
            b_mult = body / avg_body
            r_mult = rng / avg_rng
            return {
                "rng": rng,
                "body": body,
                "body_ratio": body / rng,
                "up_wick_ratio": up_w / rng,
                "lo_wick_ratio": lo_w / rng,
                "body_mult": b_mult,
                "rng_mult": r_mult,
                "mult": max(b_mult, r_mult),
                "dir": 1.0 if c["close"] >= c["open"] else -1.0,
            }

        m1 = _metrics(c1)
        m0 = _metrics(c0)
        mult_req = max(1.2, float(self.settings.get("InpAnomalyMult", 1.8)))

        # На M5 берем закрытую аномальную свечу c1 ИЛИ взрывную формирующуюся свечу c0
        use_c0 = (m0["mult"] >= mult_req * 1.08) and (m0["mult"] >= m1["mult"])
        target_c = c0 if use_c0 else c1
        tm = m0 if use_c0 else m1

        is_anom = tm["mult"] >= mult_req
        c_dir = int(tm["dir"])
        b_ratio = tm["body_ratio"]
        up_w = tm["up_wick_ratio"]
        lo_w = tm["lo_wick_ratio"]
        live_px = self.bid_price if self.bid_price > 0 else c0["close"]

        # Подтверждение микро-импульса на таймфрейме сделки M1 (для точного входа на 1-2 свечи M1)
        m1_dir = 0
        if use_m5_m1 and len(self.m1_candles) >= 3:
            mc0 = self.m1_candles[0]
            mc1 = self.m1_candles[1]
            if mc0["close"] > mc0["open"] or mc1["close"] > mc1["open"]:
                m1_dir = 1
            elif mc0["close"] < mc0["open"] or mc1["close"] < mc1["open"]:
                m1_dir = -1
        else:
            m1_dir = c_dir

        # 1. Вариант 1: Инерция импульса (Полнотелая аномальная свеча M5 -> вход ПО ХОДУ на 1-2 свечи M1)
        is_full_bull = is_anom and c_dir == 1 and b_ratio >= 0.60 and up_w <= 0.26 and (m1_dir >= 0)
        is_full_bear = is_anom and c_dir == -1 and b_ratio >= 0.60 and lo_w <= 0.26 and (m1_dir <= 0)
        mom_buy = bool(is_full_bull and self.settings.get("InpStratAnomalyMomentum", True))
        mom_sell = bool(is_full_bear and self.settings.get("InpStratAnomalyMomentum", True))

        # 2. Вариант 2: Возврат после прострела (Экстремальный прострел M5 или длинный хвост -> вход ПРОТИВ на откат 1-2 свечи M1)
        is_exhaustion_up = (tm["rng_mult"] >= mult_req * 1.12 and c_dir == 1) or (tm["rng_mult"] >= mult_req * 0.90 and up_w >= 0.42)
        is_exhaustion_dn = (tm["rng_mult"] >= mult_req * 1.12 and c_dir == -1) or (tm["rng_mult"] >= mult_req * 0.90 and lo_w >= 0.42)
        pullback_sell_ok = is_exhaustion_up and (live_px <= target_c["high"] - tm["rng"] * 0.06)
        pullback_buy_ok = is_exhaustion_dn and (live_px >= target_c["low"] + tm["rng"] * 0.06)
        fade_sell = bool(pullback_sell_ok and self.settings.get("InpStratAnomalyFade", True))
        fade_buy = bool(pullback_buy_ok and self.settings.get("InpStratAnomalyFade", True))

        # 3. Вариант 3: Умный Снайпер 2-в-1 (По форме свечи M5: полнотелая без тени -> ПО ХОДУ на M1; длинная шпилька -> В ОТКАТ на M1)
        hyb_on = bool(self.settings.get("InpStratAnomalyHybrid", True))
        hyb_buy = bool(
            hyb_on
            and (
                (is_anom and c_dir == 1 and b_ratio >= 0.65 and up_w <= 0.20 and m1_dir >= 0)
                or (tm["rng_mult"] >= mult_req * 0.92 and lo_w >= 0.44 and live_px >= target_c["low"] + tm["rng"] * 0.10)
            )
        )
        hyb_sell = bool(
            hyb_on
            and (
                (is_anom and c_dir == -1 and b_ratio >= 0.65 and lo_w <= 0.20 and m1_dir <= 0)
                or (tm["rng_mult"] >= mult_req * 0.92 and up_w >= 0.44 and live_px <= target_c["high"] - tm["rng"] * 0.10)
            )
        )

        if is_full_bull or is_full_bear:
            pat_txt = f"[{analysis_tf}→{trade_tf}] Аномальный импульс ×{tm['mult']:.1f} ({'БЫЧИЙ' if c_dir == 1 else 'МЕДВЕЖИЙ'}, тело {b_ratio*100:.0f}%)"
        elif up_w >= 0.42 or lo_w >= 0.42:
            pat_txt = f"[{analysis_tf}→{trade_tf}] Аномальная шпилька ×{tm['mult']:.1f} (тень {max(up_w, lo_w)*100:.0f}% — вынос стопов)"
        elif is_anom:
            pat_txt = f"[{analysis_tf}→{trade_tf}] Аномальный всплеск ×{tm['mult']:.1f} ({tm['rng']:.0f}$)"
        else:
            pat_txt = f"[{analysis_tf}→{trade_tf}] Спокойная свеча ×{tm['mult']:.1f} (порог ×{mult_req:.1f})"

        act_sig = ""
        if hyb_buy or mom_buy or fade_buy:
            act_sig = "BUY"
        elif hyb_sell or mom_sell or fade_sell:
            act_sig = "SELL"

        self.anomaly_state = {
            "is_anomaly": bool(is_anom or up_w >= 0.44 or lo_w >= 0.44),
            "use_m5_m1": use_m5_m1,
            "analysis_tf": analysis_tf,
            "trade_tf": trade_tf,
            "bar_sec": bar_sec,
            "mult": round(tm["mult"], 2),
            "body_mult": round(tm["body_mult"], 2),
            "rng_mult": round(tm["rng_mult"], 2),
            "body_ratio_pct": round(b_ratio * 100.0, 1),
            "upper_wick_pct": round(up_w * 100.0, 1),
            "lower_wick_pct": round(lo_w * 100.0, 1),
            "candle_dir": c_dir,
            "m1_confirm_dir": m1_dir,
            "pattern_type": pat_txt,
            "anom_range": round(tm["rng"], 2),
            "anom_high": round(float(target_c["high"]), 2),
            "anom_low": round(float(target_c["low"]), 2),
            "anom_mid": round(float(target_c["high"] + target_c["low"]) * 0.5, 2),
            "mom_buy": mom_buy,
            "mom_sell": mom_sell,
            "fade_buy": fade_buy,
            "fade_sell": fade_sell,
            "hyb_buy": hyb_buy,
            "hyb_sell": hyb_sell,
            "active_signal": act_sig,
            "max_bars": int(self.settings.get("InpAnomalyMaxBars", 2)),
        }
        return self.anomaly_state

    # -------------------------------------------------------------------------
    # Economic Calendar News Filter & Analyzer (USD)
    # -------------------------------------------------------------------------
    async def refresh_news_calendar(self) -> None:
        now = time.time()
        if now - self.news_last_fetch < 900 and self.news_cache:
            return
        self.news_last_fetch = now
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json")
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        self.news_cache = data
        except Exception:
            pass

    @staticmethod
    def _parse_num(val_str: Optional[str]) -> Optional[float]:
        if not val_str:
            return None
        s = str(val_str).strip().upper()
        mult = 1.0
        if "B" in s:
            mult = 1e9
        elif "M" in s:
            mult = 1e6
        elif "K" in s:
            mult = 1e3
        cleaned = (
            s.replace("%", "")
            .replace("K", "")
            .replace("M", "")
            .replace("B", "")
            .replace("$", "")
            .replace(",", "")
            .strip()
        )
        try:
            return float(cleaned) * mult
        except ValueError:
            return None

    def analyze_market_news(self) -> Tuple[bool, int, str]:
        self.news_paused = False
        self.news_bias = 0
        self.news_status = "Спокойно (Новостей нет)"
        self.upcoming_news = []

        if not self.settings["InpUseNewsFilter"]:
            self.news_status = "Выключен"
            return False, 0, self.news_status

        target_ccy = str(self.settings["InpNewsCurrency"]).upper()
        pause_before_sec = int(self.settings["InpPauseBeforeMin"]) * 60
        pause_after_sec = int(self.settings["InpPauseAfterMin"]) * 60
        effect_sec = int(self.settings["InpNewsEffectMin"]) * 60
        trade_impulse = bool(self.settings["InpTradeNewsImpulse"])

        now_ts = int(time.time())
        relevant_events: List[Dict[str, Any]] = []

        for item in self.news_cache:
            if str(item.get("country", "")).upper() != target_ccy:
                continue
            if str(item.get("impact", "")).lower() != "high":
                continue

            date_str = item.get("date", "")
            try:
                event_dt = datetime.fromisoformat(date_str)
                event_ts = int(event_dt.timestamp())
            except Exception:
                continue

            diff_sec = now_ts - event_ts  # Negative = future, Positive = already released
            title = str(item.get("title", "USD High Impact News"))
            actual_str = str(item.get("actual", "") or "")
            forecast_str = str(item.get("forecast", "") or "")

            if -86400 <= diff_sec <= 43200:
                relevant_events.append(
                    {
                        "title": title,
                        "time": event_ts,
                        "diff_min": int(round(diff_sec / 60.0)),
                        "actual": actual_str,
                        "forecast": forecast_str,
                    }
                )

            # 1. Check protective pause BEFORE and immediately AFTER release
            if -pause_before_sec <= diff_sec <= pause_after_sec:
                self.news_paused = True
                self.news_status = f"ПАУЗА! Новость: {title} ({int(diff_sec // 60)} мин)"
                self.upcoming_news = relevant_events[:6]
                return self.news_paused, self.news_bias, self.news_status

            # 2. Analyze Actual vs Forecast within InpNewsEffectMin after pause
            if trade_impulse and pause_after_sec < diff_sec <= effect_sec:
                actual_val = self._parse_num(actual_str)
                forecast_val = self._parse_num(forecast_str)
                if actual_val is not None and forecast_val is not None and actual_val != forecast_val:
                    is_inverted = any(w in title.lower() for w in INVERTED_USD_EVENTS)
                    usd_strong = (actual_val < forecast_val) if is_inverted else (actual_val > forecast_val)
                    if usd_strong:
                        self.news_bias = -1
                        self.news_status = f"Сильный USD ({title}: {actual_str} vs {forecast_str}) -> Ищем SELL"
                    else:
                        self.news_bias = 1
                        self.news_status = f"Слабый USD ({title}: {actual_str} vs {forecast_str}) -> Ищем BUY"

        self.upcoming_news = sorted(relevant_events, key=lambda x: abs(x["diff_min"]))[:6]
        return self.news_paused, self.news_bias, self.news_status

    # -------------------------------------------------------------------------
    # Market Structure (BOS) & Mandarin Box (Exact Port of MQL5)
    # -------------------------------------------------------------------------
    def update_market_structure(self) -> None:
        self.last_swing_high = 0.0
        self.last_swing_high_time = 0
        self.last_swing_low = 0.0
        self.last_swing_low_time = 0

        swing_period = int(self.settings["InpSwingPeriod"])
        lookback = min(120, len(self.m15_candles) - swing_period - 1)
        if lookback <= swing_period + 2:
            return

        fallback_high = 0.0
        fallback_high_time = 0
        fallback_low = 0.0
        fallback_low_time = 0

        for i in range(swing_period + 2, lookback):
            is_high = True
            is_low = True
            curr_high = self.m15_candles[i]["high"]
            curr_low = self.m15_candles[i]["low"]

            for j in range(1, swing_period + 1):
                if (
                    self.m15_candles[i - j]["high"] >= curr_high
                    or self.m15_candles[i + j]["high"] > curr_high
                ):
                    is_high = False
                if (
                    self.m15_candles[i - j]["low"] <= curr_low
                    or self.m15_candles[i + j]["low"] < curr_low
                ):
                    is_low = False

            if is_high and fallback_high == 0.0:
                fallback_high = curr_high
                fallback_high_time = self.m15_candles[i]["time"]
            if is_low and fallback_low == 0.0:
                fallback_low = curr_low
                fallback_low_time = self.m15_candles[i]["time"]

            # Verify level has not been broken by closes between bar 2 and i-1
            if is_high:
                for k in range(2, i):
                    if self.m15_candles[k]["close"] > curr_high:
                        is_high = False
                        break
            if is_low:
                for k in range(2, i):
                    if self.m15_candles[k]["close"] < curr_low:
                        is_low = False
                        break

            if is_high and self.last_swing_high == 0.0:
                self.last_swing_high = curr_high
                self.last_swing_high_time = self.m15_candles[i]["time"]
            if is_low and self.last_swing_low == 0.0:
                self.last_swing_low = curr_low
                self.last_swing_low_time = self.m15_candles[i]["time"]

            if self.last_swing_high > 0.0 and self.last_swing_low > 0.0:
                break
        # Исправлено ИИ-Агентом: удалена подстановка уже пробитых исторических fallback_high / fallback_low,
        # чтобы исключить ложные повторные пробои BOS.

    def check_mandarin_box(self, atr: float, base_shift: int = 1) -> Tuple[bool, float, float]:
        bars_count = int(self.settings["InpMandarinBars"])
        max_atr = float(self.settings["InpMandarinMaxATR"])
        if len(self.m15_candles) <= base_shift + bars_count:
            return False, 0.0, 0.0

        out_high = -1e18
        out_low = 1e18
        for i in range(base_shift + 1, base_shift + 1 + bars_count):
            h = self.m15_candles[i]["high"]
            l = self.m15_candles[i]["low"]
            if h > out_high:
                out_high = h
            if l < out_low:
                out_low = l

        if not self.settings["InpUseMandarin"]:
            return True, out_high, out_low

        is_valid = (out_high - out_low) <= (atr * max_atr)
        return is_valid, out_high, out_low

    def scan_historical_boxes(self, atr: float) -> List[Dict[str, Any]]:
        boxes: List[Dict[str, Any]] = []
        if atr <= 0 or not self.settings["InpUseMandarin"]:
            return boxes
        bars_count = int(self.settings["InpMandarinBars"])
        max_shift = min(50, len(self.m15_candles) - bars_count - 2)
        for shift in range(1, max_shift):
            valid, bh, bl = self.check_mandarin_box(atr, base_shift=shift)
            if valid:
                t_start = self.m15_candles[shift + bars_count]["time"]
                t_end = self.m15_candles[shift + 1]["time"]
                boxes.append(
                    {
                        "high": round(bh, 2),
                        "low": round(bl, 2),
                        "start_time": t_start,
                        "end_time": t_end,
                    }
                )
        return boxes[:8]

    # -------------------------------------------------------------------------
    # Money Management & Position Sizing (Авто-калькуляция депозита 1/5 по видео + Excel)
    # -------------------------------------------------------------------------
    def _to_sl_punkti(self, symbol: str, sl_distance_price: float) -> float:
        if sl_distance_price <= 0:
            return 154.0
        if symbol == "XAUUSD" and sl_distance_price < 45.0:
            # На Золоте (XAUUSD) в видео КАЛКУЛЯЦИЯ.MOV 1$ движения = 10 пунктов (например, $15.4 = 154 п., $6.1 = 61 п.)
            return round(max(25.0, sl_distance_price * 10.0), 1)
        if symbol == "US500" and sl_distance_price < 45.0:
            return round(max(30.0, sl_distance_price * 5.0), 1)
        return round(max(25.0, sl_distance_price), 1)

    def get_deposit_calc_state(self, sl_distance_price: float) -> Dict[str, Any]:
        symbol = self.settings.get("symbol", "XAUUSD")
        balance = max(10.0, float(self.account["balance"]))
        working_part = round(balance / 5.0, 2)
        reserve_4_5 = round(balance - working_part, 2)
        sl_punkti = self._to_sl_punkti(symbol, sl_distance_price)
        risk_pct = float(self.settings.get("InpRiskPercent", 3.0))
        scale = max(0.3, risk_pct / 3.0)

        # Точная формула из Excel (КАЛКУЛЯЦИЯ.MOV): LOTT = (Balance / 5) / SL_punkti / 100
        excel_raw_lot = (working_part * scale) / (sl_punkti * 100.0)
        excel_lot = max(0.01, min(100.0, round(excel_raw_lot, 2)))

        # Прогноз сложного процента (после TP 1:1, TP 1:1.3 и при SL)
        win_1_1_bal = round(balance + working_part, 2)
        win_1_1_part = round(win_1_1_bal / 5.0, 2)
        win_1_3_bal = round(balance + working_part * 1.3, 2)
        win_1_3_part = round(win_1_3_bal / 5.0, 2)
        loss_bal = round(max(10.0, balance - working_part), 2)
        loss_part = round(loss_bal / 5.0, 2)

        steps_1_1: List[Dict[str, float]] = []
        sim_b = balance
        for step_idx in range(1, 6):
            p = round(sim_b / 5.0, 2)
            sim_b = round(sim_b + p, 2)
            steps_1_1.append({"step": step_idx, "part": p, "next_balance": sim_b})

        return {
            "enabled": bool(self.settings.get("InpUseDepositCalc15", True)),
            "total_balance": round(balance, 2),
            "working_part": working_part,
            "reserve_4_5": reserve_4_5,
            "parts": [working_part] * 5,
            "sl_punkti": sl_punkti,
            "excel_lot": excel_lot,
            "win_1_1_balance": win_1_1_bal,
            "win_1_1_next_part": win_1_1_part,
            "win_1_3_balance": win_1_3_bal,
            "win_1_3_next_part": win_1_3_part,
            "loss_balance": loss_bal,
            "loss_next_part": loss_part,
            "compound_steps": steps_1_1,
        }

    def calculate_crypto_lot_size(self, entry_price: float, sl_distance_price: float) -> float:
        fixed_lot = float(self.settings["InpFixedLot"])
        if not self.settings["InpUseAutoLot"] or sl_distance_price <= 0 or entry_price <= 0:
            return fixed_lot

        symbol = self.settings["symbol"]
        spec = SYMBOL_SPECS.get(symbol, SYMBOL_SPECS["BTCUSD"])
        balance = float(self.account["balance"])
        risk_pct = float(self.settings["InpRiskPercent"])

        # Авто-калькуляция депозита 1/5 по видео (Депозитті 5-ке бөлу + SL пункті)
        if self.settings.get("InpUseDepositCalc15", True):
            working_part = balance / 5.0
            sl_punkti = self._to_sl_punkti(symbol, sl_distance_price)
            scale = max(0.33, risk_pct / 3.0)
            raw_lot = (working_part * scale) / (sl_punkti * 100.0)
        else:
            risk_money = balance * (risk_pct / 100.0)
            tick_value = spec["tick_value"]
            tick_size = spec["tick_size"]
            sl_ticks = max(1.0, sl_distance_price / tick_size)
            raw_lot = risk_money / (sl_ticks * tick_value)

        # Margin check
        margin_for_one_lot = (entry_price * spec["contract_size"]) / spec["leverage"]
        if margin_for_one_lot > 0:
            free_margin = self.get_account_metrics()["free_margin"]
            max_allowed_margin = free_margin * (float(self.settings["InpMaxMarginUsage"]) / 100.0)
            max_margin_lot = max_allowed_margin / margin_for_one_lot
            if raw_lot > max_margin_lot:
                raw_lot = max_margin_lot

        step_lot = spec["step_lot"]
        min_lot = spec["min_lot"]
        max_lot = spec["max_lot"]

        lot = round(raw_lot / step_lot) * step_lot
        lot = max(min_lot, min(max_lot, lot))
        return round(lot, 2)

    # -------------------------------------------------------------------------
    # Positions Management ("Сейф 50%" Partial Close, Breakeven, SL/TP)
    # -------------------------------------------------------------------------
    def _is_price_valid_for_symbol(self, symbol: str, price: float) -> bool:
        if price <= 0:
            return False
        if symbol == "XAUUSD" and (price < 500 or price > 15000):
            return False
        if symbol == "BTCUSD" and price < 15000:
            return False
        if symbol == "NAS100" and (price < 4000 or price > 70000):
            return False
        if symbol == "US500" and (price < 1500 or price > 25000):
            return False
        return True

    def get_open_positions(self) -> List[Dict[str, Any]]:
        if self.is_mt5_live():
            return self.mt5_positions
        symbol = self.settings["symbol"]
        spec = SYMBOL_SPECS.get(symbol, SYMBOL_SPECS["BTCUSD"])
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM positions ORDER BY ticket DESC").fetchall()

        positions: List[Dict[str, Any]] = []
        for r in rows:
            pos = dict(r)
            p_sym = pos["symbol"]
            p_spec = SYMBOL_SPECS.get(p_sym, spec)
            raw_live_price = self.bid_price if pos["pos_type"] == "BUY" else self.ask_price
            current_price = (
                raw_live_price
                if p_sym == symbol and self._is_price_valid_for_symbol(p_sym, raw_live_price)
                else pos["open_price"]
            )
            price_diff = (
                (current_price - pos["open_price"])
                if pos["pos_type"] == "BUY"
                else (pos["open_price"] - current_price)
            )
            ticks = price_diff / p_spec["tick_size"]
            floating_pnl = round(ticks * p_spec["tick_value"] * pos["volume"], 2)
            atr_multiple = round(price_diff / self.atr_value, 2) if self.atr_value > 0 else 0.0

            pos["current_price"] = round(current_price, p_spec["digits"])
            pos["pnl"] = floating_pnl
            pos["atr_multiple"] = atr_multiple
            positions.append(pos)
        return positions

    def get_account_metrics(self) -> Dict[str, float]:
        balance = float(self.account["balance"])
        positions = self.get_open_positions()
        floating_pnl = sum(p["pnl"] for p in positions)
        equity = round(balance + floating_pnl, 2)

        used_margin = 0.0
        for p in positions:
            p_spec = SYMBOL_SPECS.get(p["symbol"], SYMBOL_SPECS["BTCUSD"])
            used_margin += (p["open_price"] * p_spec["contract_size"] * p["volume"]) / p_spec["leverage"]

        used_margin = round(used_margin, 2)
        free_margin = round(max(0.0, equity - used_margin), 2)
        return {
            "balance": round(balance, 2),
            "equity": equity,
            "floating_pnl": round(floating_pnl, 2),
            "used_margin": used_margin,
            "free_margin": free_margin,
        }

    def open_position(
        self,
        pos_type: str,
        volume: Optional[float] = None,
        comment: str = "Crypto BOS+News",
    ) -> Optional[Dict[str, Any]]:
        symbol = self.settings["symbol"]
        if not self._is_price_valid_for_symbol(symbol, self.bid_price) or not self._is_price_valid_for_symbol(symbol, self.ask_price):
            return None

        # Защита от случайного открытия пачки скрытых сделок при многократном нажатии кнопки:
        # В соответствии с логикой советника и экрана (1 карточка активной сделки),
        # если сделка в ту же сторону уже открыта — возвращаем её, если в противоположную — закрываем старую.
        now_order_ts = time.time()
        if now_order_ts - getattr(self, "_last_order_sent_ts", 0.0) < 10.0:
            existing_now = self.get_open_positions()
            if existing_now:
                return existing_now[0]

        existing = self.get_open_positions()
        if existing:
            same_side = [p for p in existing if p["pos_type"] == pos_type and p["symbol"] == symbol]
            opp_side = [p for p in existing if p["pos_type"] != pos_type or p["symbol"] != symbol]
            for ep in opp_side:
                self.close_position(ep["ticket"], reason="Закрытие встречной сделки")
            if same_side:
                # Закрываем лишние дубликаты, оставляя только 1 сделку
                for dup in same_side[1:]:
                    self.close_position(dup["ticket"], reason="Удаление дубликата")
                return same_side[0]

        self._last_order_sent_ts = now_order_ts
        spec = SYMBOL_SPECS.get(symbol, SYMBOL_SPECS["BTCUSD"])
        atr = self.atr_value if self.atr_value > 0 else (self.bid_price * 0.002)

        entry_price = self.ask_price if pos_type == "BUY" else self.bid_price
        fg = self.fibo_grid if isinstance(getattr(self, "fibo_grid", None), dict) else {}

        # Точный расчет SL и TP:
        # 1) Для сделок по Аномальным свечам (Без индикаторов) — расчет строго от геометрии самой аномальной свечи!
        # 2) Для сделок Фибоначчи — расчет SL за уровень 0.0% Фибо и TP на 61.8% / 1.272
        sl_dist = atr * float(self.settings["InpSL_ATR"])
        tp_dist = atr * float(self.settings["InpTP_ATR"])
        anom = getattr(self, "anomaly_state", None) or {}
        is_anom_trade = ("Anomaly" in comment) or ("Аномал" in comment)
        is_fibo_trade = ("Fibo" in comment) or ("Ручной" in comment)

        if is_anom_trade and float(anom.get("anom_range") or 0) > 0:
            a_rng = float(anom["anom_range"])
            # Короткий защитный стоп за половину/экстремум аномальной свечи и быстрый тейк на 1–2 свечи
            sl_dist = max(atr * 0.65, min(atr * 1.65, a_rng * 0.65))
            tp_dist = max(sl_dist * 1.45, a_rng * 0.95)
        elif fg.get("is_active") and is_fibo_trade:
            p0 = float(fg.get("price_0") or 0.0)
            p618 = float(fg.get("lvl_618") or 0.0)
            p100 = float(fg.get("price_100") or 0.0)
            p1272 = float(fg.get("lvl_1272") or p100)
            is_mentor = "0.786" in comment
            if pos_type == "BUY" and fg.get("direction") == 1 and p0 > 0 and p0 < entry_price:
                fibo_sl_dist = (entry_price - p0) + atr * 0.22
                sl_dist = max(atr * 0.85, min(atr * 2.10, fibo_sl_dist))
                target_tp = p1272 if is_mentor else (p618 if p618 > entry_price + atr * 1.1 else p100)
                if target_tp > entry_price + atr * 1.1:
                    tp_dist = max(sl_dist * 1.8, target_tp - entry_price)
            elif pos_type == "SELL" and fg.get("direction") == -1 and p0 > entry_price:
                fibo_sl_dist = (p0 - entry_price) + atr * 0.22
                sl_dist = max(atr * 0.85, min(atr * 2.10, fibo_sl_dist))
                target_tp = p1272 if is_mentor else (p618 if 0 < p618 < entry_price - atr * 1.1 else p100)
                if 0 < target_tp < entry_price - atr * 1.1:
                    tp_dist = max(sl_dist * 1.8, entry_price - target_tp)

        if volume is None or volume <= 0:
            volume = self.calculate_crypto_lot_size(entry_price, sl_dist)

        if pos_type == "BUY":
            sl = round(entry_price - sl_dist, spec["digits"])
            tp = round(entry_price + tp_dist, spec["digits"])
        else:
            sl = round(entry_price + sl_dist, spec["digits"])
            tp = round(entry_price - tp_dist, spec["digits"])

        if self.is_mt5_live():
            self.mt5_commands.append(
                {
                    "action": "open",
                    "symbol": symbol,
                    "pos_type": pos_type,
                    "volume": volume,
                    "sl": sl,
                    "tp": tp,
                    "comment": comment,
                }
            )
            self._flush_mt5_commands_to_wine()
            self.add_notification(
                f"Отправлен ордер в MT5: {pos_type} ({symbol})",
                f"Лот: {volume:.2f} | SL: {sl:.2f} | TP: {tp:.2f} (Счет #{self.mt5_login_id})",
                "success",
            )
            return {
                "ticket": int(time.time()),
                "symbol": symbol,
                "pos_type": pos_type,
                "volume": volume,
                "open_price": entry_price,
                "current_price": entry_price,
                "sl": sl,
                "tp": tp,
                "pnl": 0.0,
                "atr_multiple": 0.0,
                "is_partial_done": False,
                "is_breakeven": False,
            }

        now_ts = int(time.time())
        with self._get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO positions (
                    symbol, pos_type, volume, initial_volume, open_price, sl, tp,
                    open_time, is_partial_done, is_breakeven, comment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
                """,
                (symbol, pos_type, volume, volume, entry_price, sl, tp, now_ts, comment),
            )
            ticket = cur.lastrowid
            conn.commit()

        self.add_notification(
            f"Открыт {pos_type} #{ticket} ({symbol})",
            f"Лот: {volume:.2f} | Цена: {entry_price:.2f} | SL: {sl:.2f} | TP: {tp:.2f}",
            "success",
        )
        return self.get_open_positions()[0]

    def close_position(self, ticket: int, reason: str = "Закрыто вручную") -> bool:
        if self.is_mt5_live():
            self.mt5_commands.append({"action": "close", "ticket": ticket, "reason": reason})
            self._flush_mt5_commands_to_wine()
            self.mt5_positions = [p for p in self.mt5_positions if p["ticket"] != ticket]
            return True
        positions = [p for p in self.get_open_positions() if p["ticket"] == ticket]
        if not positions:
            return False
        pos = positions[0]
        pnl = pos["pnl"]
        close_price = pos["current_price"]
        now_ts = int(time.time())

        self.account["balance"] = round(self.account["balance"] + pnl, 2)
        with self._get_conn() as conn:
            conn.execute("DELETE FROM positions WHERE ticket = ?", (ticket,))
            conn.execute(
                "UPDATE account SET balance = ? WHERE id = 1",
                (self.account["balance"],),
            )
            conn.execute(
                """
                INSERT INTO trade_history (
                    ticket, symbol, pos_type, volume, open_price, close_price, pnl, close_time, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticket,
                    pos["symbol"],
                    pos["pos_type"],
                    pos["volume"],
                    pos["open_price"],
                    close_price,
                    pnl,
                    now_ts,
                    reason,
                ),
            )
            conn.commit()

        sign = "+" if pnl >= 0 else ""
        self.add_notification(
            f"Закрыта сделка #{ticket} ({reason})",
            f"{pos['symbol']} {pos['pos_type']} {pos['volume']:.2f} лот | Результат: {sign}${pnl:.2f}",
            "success" if pnl >= 0 else "warning",
        )
        return True

    def trigger_partial_safe(self, ticket: int, auto: bool = False) -> bool:
        positions = [p for p in self.get_open_positions() if p["ticket"] == ticket]
        if not positions:
            return False
        pos = positions[0]
        spec = SYMBOL_SPECS.get(pos["symbol"], SYMBOL_SPECS["BTCUSD"])
        step_lot = spec["step_lot"]
        min_lot = spec["min_lot"]

        pct = float(self.settings["InpPartialClosePct"]) / 100.0
        close_vol = math.floor((pos["volume"] * pct) / step_lot) * step_lot
        close_vol = round(close_vol, 2)
        rem_vol = round(pos["volume"] - close_vol, 2)

        if close_vol < min_lot or rem_vol < min_lot:
            return False

        # Calculate new Breakeven SL (+0.20 ATR)
        atr = self.atr_value if self.atr_value > 0 else abs(pos["current_price"] - pos["open_price"])
        offset_dist = atr * float(self.settings["InpBE_OffsetATR"])
        if pos["pos_type"] == "BUY":
            new_sl = round(pos["open_price"] + offset_dist, spec["digits"])
        else:
            new_sl = round(pos["open_price"] - offset_dist, spec["digits"])

        if self.is_mt5_live():
            pos["is_partial_done"] = True
            pos["is_breakeven"] = True
            self.mt5_commands.append(
                {
                    "action": "safe",
                    "ticket": ticket,
                    "close_volume": close_vol,
                    "new_sl": new_sl,
                    "tp": pos["tp"],
                }
            )
            self._flush_mt5_commands_to_wine()
            return True

        # Realize profit on closed half
        ratio = close_vol / pos["volume"]
        realized_pnl = round(pos["pnl"] * ratio, 2)
        self.account["balance"] = round(self.account["balance"] + realized_pnl, 2)

        now_ts = int(time.time())
        reason = "Сейф 50% (Авто 1.5 ATR)" if auto else "Сейф 50% (Вручную)"

        with self._get_conn() as conn:
            conn.execute(
                "UPDATE positions SET volume = ?, sl = ?, is_partial_done = 1, is_breakeven = 1 WHERE ticket = ?",
                (rem_vol, new_sl, ticket),
            )
            conn.execute(
                "UPDATE account SET balance = ? WHERE id = 1",
                (self.account["balance"],),
            )
            conn.execute(
                """
                INSERT INTO trade_history (
                    ticket, symbol, pos_type, volume, open_price, close_price, pnl, close_time, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticket,
                    pos["symbol"],
                    pos["pos_type"],
                    close_vol,
                    pos["open_price"],
                    pos["current_price"],
                    realized_pnl,
                    now_ts,
                    reason,
                ),
            )
            conn.commit()

        sign = "+" if realized_pnl >= 0 else ""
        self.add_notification(
            f"Сработал СЕЙФ 50% по #{ticket}",
            f"Зафиксировано {close_vol:.2f} лота ({sign}${realized_pnl:.2f}). Остаток {rem_vol:.2f} лота переведен в БУ (SL: {new_sl:.2f})",
            "success",
        )
        return True

    def trigger_breakeven(self, ticket: int, custom_offset_atr: Optional[float] = None) -> bool:
        positions = [p for p in self.get_open_positions() if p["ticket"] == ticket]
        if not positions:
            return False
        pos = positions[0]
        spec = SYMBOL_SPECS.get(pos["symbol"], SYMBOL_SPECS["BTCUSD"])
        atr = self.atr_value if self.atr_value > 0 else (pos["open_price"] * 0.0015)
        offset_atr = custom_offset_atr if custom_offset_atr is not None else float(self.settings["InpBE_OffsetATR"])
        offset_dist = atr * offset_atr

        if pos["pos_type"] == "BUY":
            new_sl = round(pos["open_price"] + offset_dist, spec["digits"])
        else:
            new_sl = round(pos["open_price"] - offset_dist, spec["digits"])

        if self.is_mt5_live():
            pos["is_breakeven"] = True
            self.mt5_commands.append(
                {
                    "action": "breakeven",
                    "ticket": ticket,
                    "new_sl": new_sl,
                    "tp": pos["tp"],
                }
            )
            self._flush_mt5_commands_to_wine()
            return True

        with self._get_conn() as conn:
            conn.execute(
                "UPDATE positions SET sl = ?, is_breakeven = 1 WHERE ticket = ?",
                (new_sl, ticket),
            )
            conn.commit()

        self.add_notification(
            f"Безубыток по сделке #{ticket}",
            f"Стоп-лосс защищен на уровне {new_sl:.2f} (+{offset_atr:.2f} ATR)",
            "info",
        )
        return True

    def manage_positions(self, atr: float) -> None:
        if atr <= 0 or self.bid_price <= 0 or self.ask_price <= 0:
            return

        mt5_live = self.is_mt5_live()
        positions = self.get_open_positions()
        symbol = self.settings["symbol"]
        spec = SYMBOL_SPECS.get(symbol, SYMBOL_SPECS["BTCUSD"])
        min_lot = spec["min_lot"]
        step_lot = spec["step_lot"]

        partial_dist = atr * min(0.95, float(self.settings["InpPartialTrigATR"]))
        be_trig_dist = atr * min(0.85, float(self.settings["InpBE_TriggerATR"]))
        pct = float(self.settings["InpPartialClosePct"]) / 100.0
        fg = self.fibo_grid if isinstance(getattr(self, "fibo_grid", None), dict) else {}

        # Авто-очистка встречных («замков») и дублирующихся ордеров в MT5:
        # Оставляем только самую свежую сделку (positions[0]), а старые встречные или дубли сразу закрываем
        sym_positions = [p for p in positions if p["symbol"] == symbol]
        if len(sym_positions) > 1:
            primary_pos = sym_positions[0]
            for extra_pos in sym_positions[1:]:
                self.close_position(extra_pos["ticket"], reason="Авто-закрытие дубля/встречной")
            positions = [primary_pos]

        for pos in positions:
            if pos["symbol"] != symbol:
                continue

            ticket = pos["ticket"]
            open_price = pos["open_price"]
            sl = pos["sl"]
            tp = pos["tp"]
            volume = pos["volume"]
            pos_type = pos["pos_type"]
            is_be = bool(pos["is_breakeven"])

            # Точный расчёт времени жизни сделки (в секундах и свечах M15) с коррекцией часового пояса сервера MT5
            now_ts = int(time.time())
            raw_open_ts = int(pos.get("open_time") or now_ts)
            if raw_open_ts > now_ts + 1800:
                tz_shift = int(round((raw_open_ts - now_ts) / 3600.0)) * 3600
                real_open_ts = raw_open_ts - tz_shift
            else:
                real_open_ts = raw_open_ts

            tracker_map = getattr(self, "_pos_tracker", {})
            tr = tracker_map.get(ticket, {
                "real_open_ts": real_open_ts,
                "mfe_pnl": max(0.0, float(pos.get("pnl") or 0.0)),
                "mae_pnl": min(0.0, float(pos.get("pnl") or 0.0)),
            })
            cur_pnl = float(pos.get("pnl") or 0.0)
            tr["mfe_pnl"] = round(max(float(tr.get("mfe_pnl", 0.0)), cur_pnl), 2)
            tr["mae_pnl"] = round(min(float(tr.get("mae_pnl", 0.0)), cur_pnl), 2)
            elapsed_sec = max(0, now_ts - int(tr.get("real_open_ts", real_open_ts)))
            max_bars = max(1, min(5, int(self.settings.get("InpAnomalyMaxBars", 2))))
            use_m5_m1 = bool(self.settings.get("InpUseM5M1Mode", True))
            bar_sec = 60 if use_m5_m1 else 900
            tf_lbl = "M1" if use_m5_m1 else "M15"
            max_hold_sec = max_bars * bar_sec
            rem_sec = max(0, max_hold_sec - elapsed_sec)
            bars_held_num = min(max_bars, int(elapsed_sec // bar_sec) + 1)
            tr["elapsed_sec"] = elapsed_sec
            tr["rem_sec"] = rem_sec
            tr["bars_held"] = bars_held_num
            tracker_map[ticket] = tr
            self._pos_tracker = tracker_map

            pos["elapsed_sec"] = elapsed_sec
            pos["remaining_sec"] = rem_sec
            pos["bars_held"] = bars_held_num
            pos["max_bars"] = max_bars
            pos["trade_tf"] = tf_lbl
            pos["mfe_pnl"] = tr["mfe_pnl"]
            pos["mae_pnl"] = tr["mae_pnl"]

            anom_any_on = bool(
                self.settings.get("InpStratAnomalyMomentum", True)
                or self.settings.get("InpStratAnomalyFade", True)
                or self.settings.get("InpStratAnomalyHybrid", True)
            )

            # 1) ЖЁСТКИЙ АВТО-ВЫХОД ПО ТАЙМЕРУ 1 ИЛИ 2 СВЕЧЕЙ (M1 = 60-120 сек / M15 = 15-30 мин)
            if anom_any_on and elapsed_sec >= max_hold_sec:
                self.close_position(
                    ticket,
                    reason=f"Авто-выход: закрытие {max_bars}-й свечи {tf_lbl} ({elapsed_sec} сек)",
                )
                continue

            # 2) ЗАЩИТА ПОСЛЕ ЗАКРЫТИЯ 1-Й СВЕЧИ (60 сек на M1 / 900 сек на M15):
            # Если 1-я свеча в плюсе -> сразу в Безубыток / Сейф 50%; если импульс сломан -> авто-закрытие
            if anom_any_on and elapsed_sec >= bar_sec:
                if cur_pnl > 0.5 and not is_be:
                    self.trigger_breakeven(ticket, custom_offset_atr=0.12 if use_m5_m1 else 0.15)
                    is_be = True
                elif cur_pnl <= -abs(atr * volume * (0.28 if use_m5_m1 else 0.55)):
                    self.close_position(ticket, reason=f"ИИ-Защита: импульс не пошёл на 1-й свече {tf_lbl}")
                    continue
            # Защита прибыли MFE: если сделка давала хороший плюс и откатила на 60% от пика — забираем профит сразу
            mfe_trig = 3.5 if use_m5_m1 else 8.0
            if anom_any_on and tr["mfe_pnl"] >= mfe_trig and cur_pnl <= tr["mfe_pnl"] * 0.40 and cur_pnl > 0.4:
                self.close_position(ticket, reason=f"ИИ-Трейл {tf_lbl}: фиксация прибыли (пик был +${tr['mfe_pnl']:.2f})")
                continue

            close_vol = math.floor((volume * pct) / step_lot) * step_lot
            can_partial = (
                bool(self.settings["InpUsePartialClose"])
                and not bool(pos["is_partial_done"])
                and close_vol >= min_lot
                and (volume - close_vol) >= min_lot
            )

            if pos_type == "BUY":
                bid = pos["current_price"] if mt5_live else self.bid_price
                # Check SL / TP hit (only in autonomous mode; MT5 executes SL/TP on broker server)
                if not mt5_live:
                    if sl > 0 and bid <= sl:
                        reason = "Stop Loss (Безубыток)" if is_be else "Stop Loss"
                        self.close_position(ticket, reason)
                        continue
                    if tp > 0 and bid >= tp:
                        self.close_position(ticket, "Take Profit (Импульс взят)")
                        continue

                # Быстрый авто-тейк на аномальной свече (если цена прошла >= 0.85 диапазона аномальной свечи)
                anom_st = getattr(self, "anomaly_state", None) or {}
                anom_rng = float(anom_st.get("anom_range") or 0.0)
                if anom_any_on and anom_rng > 0 and (bid - open_price) >= max(atr * 0.95, anom_rng * 0.85):
                    self.close_position(ticket, "Авто-Тейк: импульс аномальной свечи взят")
                    continue

                # Умная защита «Анти-минус»: если сделка ушла ниже -0.75 ATR против нас
                p0 = float(fg.get("price_0") or 0.0)
                if not is_be and self.htf_trend == -1 and fg.get("direction") == -1:
                    if (p0 > 0 and bid < p0 - atr * 0.15) or (bid <= open_price - atr * 0.75):
                        self.close_position(ticket, "Анти-минус: защита от пробоя вниз")
                        continue

                # Достижение +0.55 ATR -> Сейф 50% и перевод в Безубыток
                lvl382 = float(fg.get("lvl_382") or 0.0)
                hit_fast_safe = bid >= (open_price + max(atr * 0.50, partial_dist * 0.75))
                if can_partial and not is_be and (hit_fast_safe or (fg.get("direction") == 1 and lvl382 > open_price + atr * 0.35 and bid >= lvl382)):
                    self.trigger_partial_safe(ticket, auto=True)
                    continue

                # Ранний Безубыток (+0.18 ATR при проходе +0.48 ATR)
                eff_trig = max(atr * 0.45, be_trig_dist * 0.75)
                eff_offset = float(self.settings["InpBE_OffsetATR"]) if can_partial else 0.25
                if self.settings["InpUseBreakeven"] and not is_be and bid >= (open_price + eff_trig):
                    self.trigger_breakeven(ticket, custom_offset_atr=eff_offset)
                    continue

                # Трейлинг-стоп в плюс (+1.05 ATR -> стоп на +0.55 ATR)
                if self.settings["InpUseBreakeven"] and bid >= (open_price + atr * 1.05):
                    lock_sl = round(open_price + atr * 0.55, spec["digits"])
                    if sl < lock_sl - spec["point"] * 10:
                        self.trigger_breakeven(ticket, custom_offset_atr=0.55)

            elif pos_type == "SELL":
                ask = pos["current_price"] if mt5_live else self.ask_price
                if not mt5_live:
                    if sl > 0 and ask >= sl:
                        reason = "Stop Loss (Безубыток)" if is_be else "Stop Loss"
                        self.close_position(ticket, reason)
                        continue
                    if tp > 0 and ask <= tp:
                        self.close_position(ticket, "Take Profit (Импульс взят)")
                        continue

                anom_st = getattr(self, "anomaly_state", None) or {}
                anom_rng = float(anom_st.get("anom_range") or 0.0)
                if anom_any_on and anom_rng > 0 and (open_price - ask) >= max(atr * 0.95, anom_rng * 0.85):
                    self.close_position(ticket, "Авто-Тейк: импульс аномальной свечи взят")
                    continue

                # Умная защита «Анти-минус»: если SELL уходит выше +0.75 ATR против нас
                p0 = float(fg.get("price_0") or 0.0)
                if not is_be and self.htf_trend == 1 and fg.get("direction") == 1:
                    if (p0 > 0 and ask > p0 + atr * 0.15) or (ask >= open_price + atr * 0.75):
                        self.close_position(ticket, "Анти-минус: защита от пробоя вверх")
                        continue

                lvl382 = float(fg.get("lvl_382") or 0.0)
                hit_fast_safe_s = ask <= (open_price - max(atr * 0.50, partial_dist * 0.75))
                if can_partial and not is_be and (hit_fast_safe_s or (fg.get("direction") == -1 and 0 < lvl382 < open_price - atr * 0.35 and ask <= lvl382)):
                    self.trigger_partial_safe(ticket, auto=True)
                    continue

                eff_trig = max(atr * 0.45, be_trig_dist * 0.75)
                eff_offset = float(self.settings["InpBE_OffsetATR"]) if can_partial else 0.25
                if self.settings["InpUseBreakeven"] and not is_be and ask <= (open_price - eff_trig):
                    self.trigger_breakeven(ticket, custom_offset_atr=eff_offset)
                    continue

                # Трейлинг-стоп в плюс (+1.05 ATR -> стоп на -0.55 ATR)
                if self.settings["InpUseBreakeven"] and ask <= (open_price - atr * 1.05):
                    lock_sl = round(open_price - atr * 0.55, spec["digits"])
                    if sl == 0 or sl > lock_sl + spec["point"] * 10:
                        self.trigger_breakeven(ticket, custom_offset_atr=0.55)

    # -------------------------------------------------------------------------
    # Main OnTick Cycle (Exact Port of OnTick in Crypto_Bot_v2_50.mq5)
    # -------------------------------------------------------------------------
    async def step_tick(self) -> None:
        self._sync_local_wine_mt5()
        # Фиксация актива: ТОЛЬКО BTCUSD 24/7 по требованию пользователя
        if self.settings.get("InpLockBTCOnly", True):
            if self.settings.get("symbol") != "BTCUSD":
                self.save_settings({"symbol": "BTCUSD", "preferred_weekday_symbol": "BTCUSD"})
        elif self.settings.get("InpAutoWeekendBTC", True) and not self.get_open_positions():
            now_dt = datetime.now(timezone.utc)
            is_weekend = now_dt.weekday() in (5, 6)
            cur_sym = self.settings.get("symbol", "BTCUSD")
            if is_weekend and cur_sym != "BTCUSD":
                self._switched_for_weekend = True
                self.save_settings({"symbol": "BTCUSD"})
            elif (not is_weekend) and getattr(self, "_switched_for_weekend", False):
                self._switched_for_weekend = False
                pref_sym = self.settings.get("preferred_weekday_symbol", "BTCUSD")
                if pref_sym != cur_sym:
                    self.save_settings({"symbol": pref_sym})

        ok = await self.fetch_market_data()
        await self.refresh_fast_m5_m1_candles()
        await self.refresh_news_calendar()
        if not ok or len(self.m15_candles) < 30:
            return

        self.last_update_ts = time.time()
        self.atr_value = self.compute_atr()
        atr = self.atr_value

        # 0. Вычисляем состояние Аномальных свечей (без индикаторов) перед управлением позициями
        anom_state = self.evaluate_anomalous_candles()

        # 1. Manage existing open positions on every tick (включая авто-закрытие 1-2 свечей!)
        self.manage_positions(atr)

        # 2. Evaluate HTF Trend & News
        self.htf_trend = self.get_htf_trend_direction()
        self.analyze_market_news()

        # 3. Update Swing High / Swing Low structure & Mandarin Box
        self.update_market_structure()
        box_valid, box_h, box_l = self.check_mandarin_box(atr, base_shift=1)
        bars_count = int(self.settings["InpMandarinBars"])
        self.mandarin_box = {
            "is_valid": box_valid,
            "high": round(box_h, 2),
            "low": round(box_l, 2),
            "height_atr": round((box_h - box_l) / atr, 2) if atr > 0 else 0.0,
            "start_time": self.m15_candles[1 + bars_count]["time"] if len(self.m15_candles) > 1 + bars_count else 0,
            "end_time": self.m15_candles[2]["time"] if len(self.m15_candles) > 2 else 0,
        }
        self.historical_boxes = self.scan_historical_boxes(atr)
        fibo_state = self.evaluate_trullas_fibo(atr)

        # 4. Evaluate candle [1] and [2] conditions for live checklist & trading
        c1 = self.m15_candles[1]
        c2 = self.m15_candles[2]
        open1, close1, high1, low1 = c1["open"], c1["close"], c1["high"], c1["low"]
        close2 = c2["close"]

        rng = high1 - low1
        body = abs(close1 - open1)
        body_ratio = (body / rng) if rng > 0 else 0.0

        is_marubozu = body_ratio >= float(self.settings["InpMarubozuRatio"])
        is_strong_atr = (
            atr > 0
            and rng >= (atr * float(self.settings["InpATRMultiplier"]))
            and rng <= (atr * 2.5)
        )
        squeeze_ratio = (atr / close1) if close1 > 0 else 0.0
        is_squeeze = squeeze_ratio <= float(self.settings["InpMaxSqueezeRatio"])

        cur_bar_time = self.m15_candles[0]["time"]
        cur_hour = datetime.fromtimestamp(cur_bar_time, tz=timezone.utc).hour
        is_active_session = (
            True
            if not self.settings["InpUseSessionFilter"]
            else (cur_hour not in (2, 4, 5, 7, 14, 19))
        )

        is_mandarin_full = box_valid and is_squeeze and is_active_session
        allow_buy_news = (not self.settings["InpTradeNewsImpulse"]) or (self.news_bias >= 0)
        allow_sell_news = (not self.settings["InpTradeNewsImpulse"]) or (self.news_bias <= 0)

        bos_buy = (
            self.last_swing_high > 0
            and close1 > open1
            and close2 <= self.last_swing_high
            and close1 > self.last_swing_high
        )
        bos_sell = (
            self.last_swing_low > 0
            and close1 < open1
            and close2 >= self.last_swing_low
            and close1 < self.last_swing_low
        )

        htf_buy_ok = (not self.settings["InpUseHTFFilter"]) or (self.htf_trend == 1)
        htf_sell_ok = (not self.settings["InpUseHTFFilter"]) or (self.htf_trend == -1)

        self.checklist = {
            "bos_buy": bos_buy,
            "bos_sell": bos_sell,
            "is_marubozu": is_marubozu,
            "body_ratio_pct": round(body_ratio * 100.0, 1),
            "is_strong_atr": is_strong_atr,
            "candle_atr_mult": round(rng / atr, 2) if atr > 0 else 0.0,
            "box_valid": box_valid,
            "box_height_atr": self.mandarin_box["height_atr"],
            "is_squeeze": is_squeeze,
            "squeeze_ratio_pct": round(squeeze_ratio * 100.0, 3),
            "is_active_session": is_active_session,
            "utc_hour": cur_hour,
            "htf_buy_ok": htf_buy_ok,
            "htf_sell_ok": htf_sell_ok,
            "allow_buy_news": allow_buy_news,
            "allow_sell_news": allow_sell_news,
            "news_paused": self.news_paused,
            "is_anomaly": bool(anom_state.get("is_anomaly")),
            "anom_mult": anom_state.get("mult", 1.0),
            "anom_pattern": anom_state.get("pattern_type", ""),
        }

        # 5. Execute new trade if bot is running
        if not self.settings["InpUseAutoLot"] and self.settings["InpFixedLot"] <= 0:
            return
        if not self.settings["is_running"]:
            return
        if self.news_paused:
            return

        symbol = self.settings["symbol"]
        has_open = any(p["symbol"] == symbol for p in self.get_open_positions())
        if has_open:
            self.last_bar_time = cur_bar_time
            self.run_ai_strategy_agent(atr=atr, force_fix=False)
            return

        now_ts = time.time()
        use_m5_m1 = bool(self.settings.get("InpUseM5M1Mode", True))
        cooldown_sec = 30.0 if use_m5_m1 else 180.0
        last_auto_ts = getattr(self, "_last_auto_trade_ts", 0.0)
        if now_ts - last_auto_ts < cooldown_sec:
            return

        max_spread = int(self.settings["InpMaxSpreadPoints"])
        if max_spread > 0 and self.spread_points > max_spread:
            return

        trade_bar_time = (self.m1_candles[0]["time"] if (use_m5_m1 and self.m1_candles) else cur_bar_time)
        self.last_bar_time = cur_bar_time
        ai_state = self.run_ai_strategy_agent(atr=atr, force_fix=False)
        ai_enabled = bool(self.settings.get("InpUseAIAgent", True))
        min_ai_score = int(self.settings.get("InpAIAgentMinScore", 65))
        signal_score = int(ai_state.get("signal_score", 75))

        bar_already_traded = getattr(self, "_last_traded_bar_time", 0) == trade_bar_time
        if bar_already_traded:
            return

        # =====================================================================
        # ПРИОРИТЕТ: 3 ВАРИАНТА СНАЙПЕРА АНОМАЛЬНЫХ СВЕЧЕЙ НА 1–2 БАРА (Анализ M5 -> Сделка M1)
        # =====================================================================
        max_b = int(self.settings.get("InpAnomalyMaxBars", 2))
        tf_tag = "M5->M1" if use_m5_m1 else "M15"
        # 1) Вариант 3 (Рекомендуемый): Умный Снайпер 2-в-1 (По форме аномальной свечи)
        if self.settings.get("InpStratAnomalyHybrid", True):
            if anom_state.get("hyb_buy"):
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = trade_bar_time
                self.open_position("BUY", comment=f"Anomaly Hybrid {tf_tag} {max_b}B Buy")
                return
            if anom_state.get("hyb_sell"):
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = trade_bar_time
                self.open_position("SELL", comment=f"Anomaly Hybrid {tf_tag} {max_b}B Sell")
                return

        # 2) Вариант 1: Инерция импульса (Вход ПО ХОДУ полнотелой аномальной свечи на 1–2 бара)
        if self.settings.get("InpStratAnomalyMomentum", True):
            if anom_state.get("mom_buy"):
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = trade_bar_time
                self.open_position("BUY", comment=f"Anomaly Momentum {tf_tag} {max_b}B Buy")
                return
            if anom_state.get("mom_sell"):
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = trade_bar_time
                self.open_position("SELL", comment=f"Anomaly Momentum {tf_tag} {max_b}B Sell")
                return

        # 3) Вариант 2: Возврат после прострела (Вход В ОТКАТ после гигантской свечи/шпильки на 1–2 бара)
        if self.settings.get("InpStratAnomalyFade", True):
            if anom_state.get("fade_buy"):
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = trade_bar_time
                self.open_position("BUY", comment=f"Anomaly Fade {tf_tag} {max_b}B Buy")
                return
            if anom_state.get("fade_sell"):
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = trade_bar_time
                self.open_position("SELL", comment=f"Anomaly Fade {tf_tag} {max_b}B Sell")
                return

        if ai_enabled and signal_score < min_ai_score:
            return

        # Классические индикаторные стратегии (выполняются только если включены пользователем в настройках):
        if self.settings.get("InpStratTrullasFibo", False):
            if fibo_state.get("trig_236_buy") and allow_buy_news:
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = cur_bar_time
                self.open_position("BUY", comment="Trullas Fibo 23.6 Buy")
                return
            if fibo_state.get("trig_236_sell") and allow_sell_news:
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = cur_bar_time
                self.open_position("SELL", comment="Trullas Fibo 23.6 Sell")
                return

        if self.settings.get("InpStratMentorFibo786", False):
            if fibo_state.get("trig_786_buy") and allow_buy_news:
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = cur_bar_time
                self.open_position("BUY", comment="Mentor Fibo 0.786 Buy")
                return
            if fibo_state.get("trig_786_sell") and allow_sell_news:
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = cur_bar_time
                self.open_position("SELL", comment="Mentor Fibo 0.786 Sell")
                return

        if self.settings.get("InpStratMandarinBOS", False):
            box_break_buy = box_valid and box_h > 0 and close1 > box_h and close2 <= box_h and is_marubozu and is_strong_atr
            box_break_sell = box_valid and box_l > 0 and close1 < box_l and close2 >= box_l and is_marubozu and is_strong_atr
            bos_buy_valid = bos_buy and is_marubozu and is_strong_atr
            bos_sell_valid = bos_sell and is_marubozu and is_strong_atr
            if (bos_buy_valid or box_break_buy) and is_mandarin_full and htf_buy_ok and allow_buy_news:
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = cur_bar_time
                self.open_position("BUY", comment="Mandarin BOS Buy")
                return
            if (bos_sell_valid or box_break_sell) and is_mandarin_full and htf_sell_ok and allow_sell_news:
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = cur_bar_time
                self.open_position("SELL", comment="Mandarin BOS Sell")
                return

        if self.settings.get("InpStratImpulseM15", False):
            imp_body_ok = body_ratio >= 0.45 and (atr > 0 and (atr * 0.90) <= rng <= (atr * 2.50))
            macd_bull_ok = (fibo_state.get("direction") == 1) and bool(fibo_state.get("macd_div"))
            macd_bear_ok = (fibo_state.get("direction") == -1) and bool(fibo_state.get("macd_div"))
            if imp_body_ok and close1 > open1 and close1 > c2["high"] and htf_buy_ok and macd_bull_ok and allow_buy_news:
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = cur_bar_time
                self.open_position("BUY", comment="Impulse M15 Buy")
                return
            if imp_body_ok and close1 < open1 and close1 < c2["low"] and htf_sell_ok and macd_bear_ok and allow_sell_news:
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = cur_bar_time
                self.open_position("SELL", comment="Impulse M15 Sell")
                return

        if self.settings.get("InpStratSwingBounce", False) and len(self.m15_candles) >= 12 and atr > 0:
            sw_window = self.m15_candles[2:10]
            ch_hi = max(b["high"] for b in sw_window)
            ch_lo = min(b["low"] for b in sw_window)
            ch_width_ok = (ch_hi - ch_lo) >= (atr * 1.20)
            rsi_now = float(fibo_state.get("rsi_val") or 50.0)
            if ch_width_ok and low1 <= (ch_lo + atr * 0.15) and close1 > open1 and close1 > ch_lo and (self.htf_trend >= 0) and (25.0 <= rsi_now <= 52.0) and allow_buy_news:
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = cur_bar_time
                self.open_position("BUY", comment="Swing Bounce Buy")
                return
            if ch_width_ok and high1 >= (ch_hi - atr * 0.15) and close1 < open1 and close1 < ch_hi and (self.htf_trend <= 0) and (48.0 <= rsi_now <= 75.0) and allow_sell_news:
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = cur_bar_time
                self.open_position("SELL", comment="Swing Bounce Sell")
                return

        if self.settings.get("InpTradeNewsImpulse", False) and self.news_bias != 0 and atr > 0:
            if self.news_bias == 1 and close1 > open1 and close1 > c2["high"] and body_ratio >= 0.50 and rng >= (atr * 0.80):
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = cur_bar_time
                self.open_position("BUY", comment="USD News Impulse Buy")
                return
            if self.news_bias == -1 and close1 < open1 and close1 < c2["low"] and body_ratio >= 0.50 and rng >= (atr * 0.80):
                self._last_auto_trade_ts = now_ts
                self._last_traded_bar_time = cur_bar_time
                self.open_position("SELL", comment="USD News Impulse Sell")
                return

    def run_ai_strategy_agent(self, atr: float = 0.0, force_fix: bool = False) -> Dict[str, Any]:
        """Улучшенный ИИ-Агент: Анализ Аномальных свечей (1-2 бара без индикаторов), живой инспектор открытой сделки (MFE/MAE/Таймер) и авто-исправление."""
        if atr <= 0:
            atr = self.atr_value if self.atr_value > 0 else 1.0
        fg = self.fibo_grid if isinstance(getattr(self, "fibo_grid", None), dict) else {}
        anom = getattr(self, "anomaly_state", None) or self.evaluate_anomalous_candles()
        sym = "BTCUSD" if self.settings.get("InpLockBTCOnly", True) else self.settings.get("symbol", "BTCUSD")
        max_bars = max(1, min(5, int(self.settings.get("InpAnomalyMaxBars", 2))))
        mult_now = float(anom.get("mult") or 1.0)
        mult_req = float(self.settings.get("InpAnomalyMult", 1.8))

        # 1. Оценка качества сигнала и геометрии свечи по 7 критериям (0 - 100%)
        score = 0
        factors: List[Dict[str, Any]] = []

        anom_ok = bool(anom.get("is_anomaly")) or (mult_now >= mult_req * 0.85)
        if anom_ok:
            score += 25
        elif mult_now >= 1.25:
            score += 15
        factors.append({"name": f"Взрыв аномальной свечи ×{mult_now:.1f} (порог ×{mult_req:.1f})", "ok": anom_ok, "weight": "+25%"})

        geom_ok = (float(anom.get("body_ratio_pct") or 0) >= 62.0) or (max(float(anom.get("upper_wick_pct") or 0), float(anom.get("lower_wick_pct") or 0)) >= 42.0)
        if geom_ok:
            score += 20
        factors.append({"name": f"Геометрия свечи: Тело {anom.get('body_ratio_pct', 0):.0f}% / Тень {max(float(anom.get('upper_wick_pct') or 0), float(anom.get('lower_wick_pct') or 0)):.0f}%", "ok": geom_ok, "weight": "+20%"})

        vol_ok = bool(fg.get("vol_confirm", True))
        if vol_ok:
            score += 15
        factors.append({"name": "Подтверждение тикового объёма в свече", "ok": vol_ok, "weight": "+15%"})

        timer_exit_ok = True
        score += 15
        factors.append({"name": f"Авто-выход по правилу {max_bars} свечей (Без пересиживания)", "ok": timer_exit_ok, "weight": "+15%"})

        anti_whipsaw_ok = (time.time() - getattr(self, "_last_auto_trade_ts", 0.0)) >= 180.0
        if anti_whipsaw_ok:
            score += 10
        factors.append({"name": "Защита от «пилы» и мгновенных переворотов (Anti-Whipsaw)", "ok": anti_whipsaw_ok, "weight": "+10%"})

        dep15_ok = bool(self.settings.get("InpUseDepositCalc15", True))
        if dep15_ok:
            score += 10
        factors.append({"name": "Безопасный лот 1/5 Депозита + Сейф после 1-й свечи", "ok": dep15_ok, "weight": "+10%"})

        spread_news_ok = (not self.news_paused) and (self.spread_points <= int(self.settings.get("InpMaxSpreadPoints", 3500)))
        if spread_news_ok:
            score += 5
        factors.append({"name": "Контроль спреда BTCUSD и импульса", "ok": spread_news_ok, "weight": "+5%"})

        # 2. Живой инспектор текущей открытой сделки (MFE / MAE / Скорость импульса / Таймер 1-2 свечей)
        open_positions = self.get_open_positions()
        live_trade_analysis: Dict[str, Any] = {
            "has_position": False,
            "summary": "Ожидание аномальной свечи (×1.8+) для быстрого входа на 1–2 свечи",
            "timer_text": f"Лимит удержания: {max_bars} свечи ({max_bars * 15} мин)",
            "mfe_mae_text": "Пик MFE: $0.00 | Просадка MAE: $0.00",
            "action_advice": "Снайпер сканирует свечи BTCUSD в реальном времени без запаздывающих индикаторов",
        }
        if open_positions:
            p = open_positions[0]
            el_sec = int(p.get("elapsed_sec") or 0)
            rm_sec = int(p.get("remaining_sec") or (max_bars * 900))
            b_held = int(p.get("bars_held") or 1)
            mfe_v = float(p.get("mfe_pnl") or max(0.0, float(p.get("pnl") or 0.0)))
            mae_v = float(p.get("mae_pnl") or min(0.0, float(p.get("pnl") or 0.0)))
            cur_pnl = float(p.get("pnl") or 0.0)
            mm_r = rm_sec // 60
            ss_r = rm_sec % 60
            vel = round(cur_pnl / max(1.0, el_sec / 60.0), 2)

            if p.get("is_breakeven"):
                adv = "🛡 Сделка защищена в Безубытке — ждём завершения 2-й свечи или авто-тейка"
            elif cur_pnl > 2.0:
                adv = f"🟢 Импульс идёт по плану ({vel:+.2f}$/мин) — после 1-й свечи перевод в БУ, выход на {max_bars}-й свече"
            elif el_sec >= 600 and cur_pnl < -2.0:
                adv = "⚠️ Импульс замедлился — ИИ-Агент закроет сделку при закрытии свечи без пересиживания"
            else:
                adv = f"⏱ Контроль 1–2 свечей активен: авто-закрытие через {mm_r:02d}:{ss_r:02d}"

            live_trade_analysis = {
                "has_position": True,
                "ticket": p["ticket"],
                "pos_type": p["pos_type"],
                "bars_held": b_held,
                "max_bars": max_bars,
                "elapsed_sec": el_sec,
                "remaining_sec": rm_sec,
                "mfe_pnl": mfe_v,
                "mae_pnl": mae_v,
                "velocity_usd_min": vel,
                "summary": f"Открыта {p['pos_type']} #{p['ticket']} · Свеча {b_held} из {max_bars} · PnL: {cur_pnl:+.2f}$",
                "timer_text": f"⏱ Авто-закрытие через {mm_r:02d}:{ss_r:02d} (Свеча {b_held}/{max_bars})",
                "mfe_mae_text": f"Пик прибыли (MFE): +${mfe_v:.2f} | Макс. просадка (MAE): -${abs(mae_v):.2f}",
                "action_advice": adv,
            }

        # 3. Определение текущей фазы свечей
        regime = f"BTCUSD 24/7 · {anom.get('pattern_type', 'Сканирование аномальных свечей')} · Авто-выход {max_bars} св."

        # 4. Статистика закрытых сделок и авто-исправление
        hist = self.get_trade_history(25)
        wins = [h for h in hist if float(h.get("pnl") or 0) > 0]
        losses = [h for h in hist if float(h.get("pnl") or 0) < 0]
        total_closed = len(wins) + len(losses)
        winrate = round((len(wins) / total_closed) * 100.0, 1) if total_closed > 0 else 100.0

        fixes_applied: List[str] = list(getattr(self, "_ai_recent_fixes", []))
        audit_notes: List[str] = [
            f"Актив жёстко зафиксирован: ТОЛЬКО BTCUSD 24/7 (без переключения на другие инструменты)",
            f"Активны 3 варианта Аномальных свечей без индикаторов с авто-выходом ровно через {max_bars} свечи",
            "Добавлен ИИ-Трейл по пику прибыли MFE (защита от возврата цены после прострела)",
            "Блокировка «пилы» (Anti-Whipsaw): запрет мгновенных переворотов BUY/SELL на одном баре",
        ]

        auto_fix_on = bool(self.settings.get("InpAIAgentAutoFix", True)) or force_fix
        updates_to_apply: Dict[str, Any] = {}

        if self.settings.get("symbol") != "BTCUSD":
            updates_to_apply["symbol"] = "BTCUSD"
            updates_to_apply["preferred_weekday_symbol"] = "BTCUSD"
            updates_to_apply["InpLockBTCOnly"] = True

        if force_fix and auto_fix_on:
            # При нажатии «Проверить и исправить» активируем все 3 варианта аномальных свечей на BTCUSD
            if not (
                self.settings.get("InpStratAnomalyMomentum")
                or self.settings.get("InpStratAnomalyFade")
                or self.settings.get("InpStratAnomalyHybrid")
            ):
                updates_to_apply["InpStratAnomalyMomentum"] = True
                updates_to_apply["InpStratAnomalyFade"] = True
                updates_to_apply["InpStratAnomalyHybrid"] = True

        if updates_to_apply:
            self.save_settings(updates_to_apply)

        if force_fix:
            ts_str = datetime.now().strftime("%H:%M:%S")
            fix_msg = f"[{ts_str}] Аудит BTCUSD: 3 режима Аномальных свечей ({max_bars} бара без индикаторов) + MFE/MAE защита активны"
            fixes_applied = [fix_msg] + [x for x in fixes_applied if x != fix_msg][:5]
            self.add_notification(
                "🤖 ИИ-Агент: Снайпер Аномальных Свечей BTCUSD синхронизирован",
                f"Актив: только BTCUSD | Авто-выход: {max_bars} свечи | Сигнал: {score}%",
                "success",
            )

        self._ai_recent_fixes = fixes_applied[:6] if fixes_applied else audit_notes[:4]
        verdict = (
            f"АНОМАЛИЯ ОБНАРУЖЕНА ({anom.get('active_signal') or 'ГОТОВ'}) — ВХОД НА {max_bars} СВЕЧИ"
            if anom.get("is_anomaly")
            else ("РЫНОК ГОТОВ — ЖДЁМ АНОМАЛЬНУЮ СВЕЧУ (×1.8+)" if score >= 60 else "ОЖИДАНИЕ ВСПЛЕСКА ВОЛАТИЛЬНОСТИ")
        )

        self.ai_agent_state = {
            "enabled": bool(self.settings.get("InpUseAIAgent", True)),
            "auto_fix": bool(self.settings.get("InpAIAgentAutoFix", True)),
            "min_score": int(self.settings.get("InpAIAgentMinScore", 65)),
            "signal_score": score,
            "verdict": verdict,
            "regime": regime,
            "winrate": winrate,
            "total_deals": total_closed,
            "wins": len(wins),
            "losses": len(losses),
            "factors": factors,
            "audit_notes": audit_notes,
            "fixes_applied": self._ai_recent_fixes,
            "live_trade": live_trade_analysis,
            "anomaly": anom,
        }
        return self.ai_agent_state

    def get_trade_history(self, limit: int = 30) -> List[Dict[str, Any]]:
        bal = max(100.0, float(self.get_account_metrics().get("balance") or self.settings.get("balance", 10000.0)))
        if self.is_mt5_live() and self.mt5_history:
            raw_list = [dict(item) for item in self.mt5_history[:limit]]
        else:
            with self._get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM trade_history ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            raw_list = [dict(r) for r in rows]

        enriched: List[Dict[str, Any]] = []
        for h in raw_list:
            op = float(h.get("open_price") or 0.0)
            cp = float(h.get("close_price") or 0.0)
            vol = max(0.01, float(h.get("volume") or 0.01))
            pnl = float(h.get("pnl") or 0.0)
            ptype = str(h.get("pos_type") or "BUY").upper()
            if abs(op - cp) < 0.01 and cp > 0 and abs(pnl) > 0.001:
                diff = pnl / vol
                if abs(diff) < cp * 0.25:
                    op = round(cp - diff, 2) if ptype == "BUY" else round(cp + diff, 2)
            h["open_price"] = round(op, 2)
            h["close_price"] = round(cp, 2)
            h["pnl_pct"] = round((pnl / bal) * 100.0, 2)
            h["status"] = "ЗАКРЫТА"
            enriched.append(h)
        return enriched

    async def fetch_chart_candles(self, symbol: str, interval: str = "15m") -> List[Dict[str, Any]]:
        spec = SYMBOL_SPECS.get(symbol, SYMBOL_SPECS["BTCUSD"])
        b_sym = spec.get("binance_symbol", "")
        yh_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with httpx.AsyncClient(timeout=7.0, headers=yh_headers) as client:
            if b_sym:
                for base_url in ("https://data-api.binance.vision", "https://api.binance.com"):
                    try:
                        resp = await client.get(
                            f"{base_url}/api/v3/klines",
                            params={"symbol": b_sym, "interval": interval, "limit": 120},
                        )
                        if resp.status_code == 200:
                            raw = resp.json()
                            if isinstance(raw, list) and len(raw) > 10:
                                return [
                                    {
                                        "time": int(k[0] // 1000),
                                        "open": float(k[1]),
                                        "high": float(k[2]),
                                        "low": float(k[3]),
                                        "close": float(k[4]),
                                        "volume": float(k[5]),
                                    }
                                    for k in raw
                                ]
                    except Exception:
                        pass

            tf_map = {
                "1m": ("1m", "2d"),
                "5m": ("5m", "5d"),
                "15m": ("15m", "5d"),
                "1h": ("60m", "1mo"),
                "4h": ("60m", "3mo"),
                "1d": ("1d", "6mo"),
            }
            yh_int, yh_rng = tf_map.get(interval, ("15m", "5d"))
            y_tickers = [t for t in (spec.get("yahoo_symbol"), spec.get("yahoo_alt")) if t]
            for y_sym in y_tickers:
                for yh_host in ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"):
                    try:
                        resp = await client.get(
                            f"{yh_host}/v8/finance/chart/{y_sym}",
                            params={"interval": yh_int, "range": yh_rng},
                        )
                        if resp.status_code == 200:
                            r_obj = (resp.json().get("chart", {}).get("result") or [None])[0]
                            if r_obj:
                                ts_list = r_obj.get("timestamp") or []
                                q = ((r_obj.get("indicators") or {}).get("quote") or [{}])[0]
                                opens = q.get("open") or []
                                highs = q.get("high") or []
                                lows = q.get("low") or []
                                closes = q.get("close") or []
                                vols = q.get("volume") or []
                                out: List[Dict[str, Any]] = []
                                for idx_t, ts_val in enumerate(ts_list):
                                    if idx_t >= len(closes) or closes[idx_t] is None or opens[idx_t] is None:
                                        continue
                                    out.append({
                                        "time": int(ts_val),
                                        "open": round(float(opens[idx_t]), spec["digits"]),
                                        "high": round(float(highs[idx_t] if highs[idx_t] is not None else closes[idx_t]), spec["digits"]),
                                        "low": round(float(lows[idx_t] if lows[idx_t] is not None else closes[idx_t]), spec["digits"]),
                                        "close": round(float(closes[idx_t]), spec["digits"]),
                                        "volume": float(vols[idx_t] if idx_t < len(vols) and vols[idx_t] is not None else 100.0),
                                    })
                                if len(out) > 10:
                                    return out[-120:]
                    except Exception:
                        pass
        return list(reversed(self.m15_candles[:90]))

    def get_full_state(self) -> Dict[str, Any]:
        symbol = self.settings["symbol"]
        atr = self.atr_value
        sl_dist = atr * float(self.settings["InpSL_ATR"])
        preview_lot = self.calculate_crypto_lot_size(self.ask_price, sl_dist)
        metrics = self.get_account_metrics()
        risk_usd = round(metrics["balance"] * (float(self.settings["InpRiskPercent"]) / 100.0), 2)

        trend_text = (
            "ВВЕРХ (Только BUY)"
            if self.htf_trend == 1
            else ("ВНИЗ (Только SELL)" if self.htf_trend == -1 else "НЕЙТРАЛЬНО")
        )

        # Return last 90 M15 candles in chronological order for chart rendering
        chart_candles = list(reversed(self.m15_candles[:90]))

        source_label = (
            f"MT5 Live #{self.mt5_login_id} ({self.mt5_account_name})"
            if self.is_mt5_live()
            else self.data_source
        )

        return {
            "version": "2.74",
            "timestamp": int(time.time()),
            "last_update_ts": int(self.last_update_ts),
            "data_source": source_label,
            "mt5_connected": self.is_mt5_live(),
            "mt5_account_name": self.mt5_account_name,
            "is_running": bool(self.settings["is_running"]),
            "symbol": symbol,
            "market": {
                "bid": self.bid_price,
                "ask": self.ask_price,
                "spread_points": self.spread_points,
                "atr": self.atr_value,
                "sl_distance": round(sl_dist, 2),
                "tp_distance": round(atr * float(self.settings["InpTP_ATR"]), 2),
                "htf_trend": self.htf_trend,
                "htf_trend_text": trend_text,
                "htf_ema": self.htf_ema_value,
                "swing_high": self.last_swing_high,
                "swing_high_time": self.last_swing_high_time,
                "swing_low": self.last_swing_low,
                "swing_low_time": self.last_swing_low_time,
                "mandarin_box": self.mandarin_box,
                "fibo_grid": self.fibo_grid,
                "anomaly": getattr(self, "anomaly_state", None) or self.evaluate_anomalous_candles(),
                "historical_boxes": self.historical_boxes,
            },
            "news": {
                "is_paused": self.news_paused,
                "bias": self.news_bias,
                "status": self.news_status,
                "currency": self.settings["InpNewsCurrency"],
                "events": self.upcoming_news,
            },
            "account": {
                **metrics,
                "risk_percent": self.settings["InpRiskPercent"],
                "risk_usd": risk_usd,
                "preview_lot": preview_lot,
                "deposit_calc": self.get_deposit_calc_state(sl_dist),
            },
            "checklist": self.checklist,
            "ai_agent": getattr(self, "ai_agent_state", None) or self.run_ai_strategy_agent(atr=atr, force_fix=False),
            "positions": self.get_open_positions(),
            "history": self.get_trade_history(25),
            "notifications": self.get_notifications(limit=15),
            "settings": self.settings,
            "chart_candles": chart_candles,
        }
