import subprocess
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Set
import httpx
import MetaTrader5 as mt5

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
MT5_INI = r"d:\Projects\Nurik\crypto_tester.ini"
MT5_LOGIN = 8112287
MT5_PASS = "XvA!Xh8e"
MT5_SERVER = "AMarkets-Demo"
SYNC_URL = "https://webrelax.pro/cryptobot/api/mt5-sync"
MAGIC_NUMBER = 777999

partial_done_tickets: Set[int] = set()
pending_events: List[Dict[str, str]] = []
_initialized: bool = False


def ensure_mt5_connected() -> bool:
    global _initialized
    if _initialized:
        term_info = mt5.terminal_info()
        acc_info = mt5.account_info()
        if term_info is not None and term_info.connected and acc_info is not None and acc_info.login == MT5_LOGIN:
            return True

    # Launch terminal with /config:crypto_tester.ini which sets Login=8112287, Enabled=1, Api=0
    try:
        subprocess.Popen([MT5_PATH, f"/config:{MT5_INI}"])
        time.sleep(5)
    except Exception as e:
        print(f"[MT5 Bridge] Launch error: {e}")

    if mt5.initialize(path=MT5_PATH, timeout=15000):
        _initialized = True
        for sym in ("BTCUSD", "XAUUSD"):
            mt5.symbol_select(sym, True)
        term_info = mt5.terminal_info()
        acc_info = mt5.account_info()
        print(
            f"[MT5 Bridge] Connected={term_info.connected if term_info else None} "
            f"TradeAllowed={term_info.trade_allowed if term_info else None} "
            f"Login={acc_info.login if acc_info else None}"
        )
        return bool(term_info and term_info.connected and acc_info and acc_info.login == MT5_LOGIN)
    return False


def get_filling_mode(symbol: str) -> int:
    s_info = mt5.symbol_info(symbol)
    if s_info is None:
        return mt5.ORDER_FILLING_IOC
    fm = s_info.filling_mode
    if fm & 2:
        return mt5.ORDER_FILLING_IOC
    if fm & 1:
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN


def execute_open(cmd: Dict[str, Any]) -> None:
    symbol = str(cmd.get("symbol", "BTCUSD"))
    pos_type = str(cmd.get("pos_type", "BUY")).upper()
    volume = float(cmd.get("volume", 0.01))
    sl = float(cmd.get("sl", 0.0))
    tp = float(cmd.get("tp", 0.0))
    comment = str(cmd.get("comment", "Crypto Bot v2.50"))

    mt5.symbol_select(symbol, True)
    tick = mt5.symbol_info_tick(symbol)
    s_info = mt5.symbol_info(symbol)
    if tick is None or s_info is None:
        pending_events.append(
            {
                "title": f"Ошибка MT5 ({symbol})",
                "message": "Не удалось получить котировку символа в MT5",
                "level": "danger",
            }
        )
        return

    order_type = mt5.ORDER_TYPE_BUY if pos_type == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if pos_type == "BUY" else tick.bid
    digits = s_info.digits

    # Recalculate SL/TP relative to actual MT5 execution price if needed
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": round(volume, 2),
        "type": order_type,
        "price": round(price, digits),
        "sl": round(sl, digits) if sl > 0 else 0.0,
        "tp": round(tp, digits) if tp > 0 else 0.0,
        "deviation": 50,
        "magic": MAGIC_NUMBER,
        "comment": comment[:31],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_mode(symbol),
    }
    res = mt5.order_send(req)
    if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
        pending_events.append(
            {
                "title": f"MT5: Открыт {pos_type} #{res.order} ({symbol})",
                "message": f"Лот: {volume:.2f} | Цена: {res.price:.2f} | SL: {sl:.2f} | TP: {tp:.2f}",
                "level": "success",
            }
        )
    else:
        code = res.retcode if res else -1
        comm = res.comment if res else str(mt5.last_error())
        pending_events.append(
            {
                "title": f"MT5 Ошибка открытия ({symbol})",
                "message": f"Код: {code} ({comm})",
                "level": "danger",
            }
        )


def execute_close(ticket: int, volume_override: float = 0.0, reason: str = "Закрыто") -> bool:
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return False
    p = positions[0]
    symbol = p.symbol
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return False

    close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = tick.bid if p.type == mt5.POSITION_TYPE_BUY else tick.ask
    vol = round(volume_override if volume_override > 0 else p.volume, 2)

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": vol,
        "type": close_type,
        "position": int(ticket),
        "price": price,
        "deviation": 50,
        "magic": MAGIC_NUMBER,
        "comment": reason[:31],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_mode(symbol),
    }
    res = mt5.order_send(req)
    if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
        pending_events.append(
            {
                "title": f"MT5: Закрыта сделка #{ticket}",
                "message": f"{symbol} {vol:.2f} лот по цене {res.price:.2f} ({reason})",
                "level": "info",
            }
        )
        return True
    return False


def execute_modify_sltp(ticket: int, new_sl: float, new_tp: float, label: str = "Безубыток") -> bool:
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return False
    p = positions[0]
    s_info = mt5.symbol_info(p.symbol)
    digits = s_info.digits if s_info else 2

    req = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": int(ticket),
        "symbol": p.symbol,
        "sl": round(new_sl, digits),
        "tp": round(new_tp if new_tp > 0 else p.tp, digits),
    }
    res = mt5.order_send(req)
    if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
        pending_events.append(
            {
                "title": f"MT5: {label} #{ticket}",
                "message": f"Стоп-лосс перенесен на {new_sl:.2f}",
                "level": "success",
            }
        )
        return True
    return False


def collect_mt5_payload() -> Dict[str, Any]:
    acc = mt5.account_info()
    account_data = {
        "login": acc.login if acc else MT5_LOGIN,
        "name": acc.name if acc else "НҰРКЕЛДІ ШӘКІРОВ",
        "server": acc.server if acc else "AMarkets-Demo",
        "balance": round(acc.balance, 2) if acc else 10000.0,
        "equity": round(acc.equity, 2) if acc else 10000.0,
    }

    ticks_data: Dict[str, Dict[str, Any]] = {}
    candles_m15: Dict[str, List[Dict[str, Any]]] = {}
    candles_h1: Dict[str, List[Dict[str, Any]]] = {}

    for sym in ("BTCUSD", "XAUUSD"):
        t = mt5.symbol_info_tick(sym)
        s = mt5.symbol_info(sym)
        if t and s and t.bid > 0:
            ticks_data[sym] = {
                "bid": round(t.bid, s.digits),
                "ask": round(t.ask, s.digits),
                "spread": int(s.spread),
            }
        r15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 90)
        if r15 is not None and len(r15) >= 30:
            candles_m15[sym] = [
                {
                    "time": int(row["time"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["tick_volume"]),
                }
                for row in reversed(r15)
            ]
        r60 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 65)
        if r60 is not None and len(r60) >= 30:
            candles_h1[sym] = [
                {
                    "time": int(row["time"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["tick_volume"]),
                }
                for row in reversed(r60)
            ]

    raw_positions = mt5.positions_get() or []
    positions_list: List[Dict[str, Any]] = []
    for p in raw_positions:
        pos_type = "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL"
        is_be = False
        if p.sl > 0:
            if pos_type == "BUY" and p.sl >= p.price_open:
                is_be = True
            elif pos_type == "SELL" and p.sl <= p.price_open:
                is_be = True

        positions_list.append(
            {
                "ticket": int(p.ticket),
                "symbol": p.symbol,
                "pos_type": pos_type,
                "volume": round(p.volume, 2),
                "initial_volume": round(p.volume, 2),
                "open_price": round(p.price_open, 2),
                "current_price": round(p.price_current, 2),
                "sl": round(p.sl, 2),
                "tp": round(p.tp, 2),
                "pnl": round(p.profit + getattr(p, "swap", 0.0), 2),
                "open_time": int(p.time),
                "is_partial_done": (int(p.ticket) in partial_done_tickets) or is_be,
                "is_breakeven": is_be,
                "comment": p.comment or "",
            }
        )

    # Fetch closed deals history
    now_dt = datetime.now(timezone.utc) + timedelta(days=1)
    from_dt = now_dt - timedelta(days=30)
    deals = mt5.history_deals_get(from_dt, now_dt) or []
    in_prices: Dict[int, float] = {}
    for d in deals:
        if d.entry == mt5.DEAL_ENTRY_IN:
            in_prices[int(d.position_id)] = float(d.price)

    history_list: List[Dict[str, Any]] = []
    for d in reversed(deals):
        if d.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT) and d.symbol:
            pos_type = "BUY" if d.type == mt5.DEAL_TYPE_SELL else "SELL"
            open_p = in_prices.get(int(d.position_id), float(d.price))
            pnl = round(float(d.profit) + float(d.swap) + float(d.commission), 2)
            history_list.append(
                {
                    "ticket": int(d.position_id or d.ticket),
                    "symbol": d.symbol,
                    "pos_type": pos_type,
                    "volume": round(float(d.volume), 2),
                    "open_price": round(open_p, 2),
                    "close_price": round(float(d.price), 2),
                    "pnl": pnl,
                    "close_time": int(d.time),
                    "reason": d.comment or "MetaTrader 5",
                }
            )
            if len(history_list) >= 35:
                break

    events_copy = list(pending_events)
    pending_events.clear()

    return {
        "account": account_data,
        "ticks": ticks_data,
        "candles_m15": candles_m15,
        "candles_h1": candles_h1,
        "positions": positions_list,
        "history": history_list,
        "events": events_copy,
    }


def main() -> None:
    print(f"[MT5 Bridge] Starting bridge for Account #{MT5_LOGIN}...")
    client = httpx.Client(timeout=8.0)
    while True:
        try:
            if ensure_mt5_connected():
                payload = collect_mt5_payload()
                resp = client.post(SYNC_URL, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    for cmd in data.get("commands", []):
                        action = cmd.get("action")
                        print(f"[MT5 Bridge] Executing command: {cmd}")
                        if action == "open":
                            execute_open(cmd)
                        elif action == "close":
                            execute_close(int(cmd["ticket"]), reason=cmd.get("reason", "Закрыто"))
                        elif action == "safe":
                            t = int(cmd["ticket"])
                            c_vol = float(cmd["close_volume"])
                            if execute_close(t, volume_override=c_vol, reason="Safe 50%"):
                                partial_done_tickets.add(t)
                                execute_modify_sltp(t, float(cmd["new_sl"]), float(cmd.get("tp", 0.0)), "Сейф 50% + БУ")
                        elif action == "breakeven":
                            t = int(cmd["ticket"])
                            execute_modify_sltp(t, float(cmd["new_sl"]), float(cmd.get("tp", 0.0)), "Безубыток")
        except Exception as exc:
            print(f"[MT5 Bridge] Loop error: {exc}")
        time.sleep(1.5)


if __name__ == "__main__":
    main()
