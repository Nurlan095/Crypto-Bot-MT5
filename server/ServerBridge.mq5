//+------------------------------------------------------------------+
//|                                                 ServerBridge.mq5 |
//|                     24/7 Headless MT5 Bridge for Crypto Bot v2.6 |
//+------------------------------------------------------------------+
#property copyright "Nurik Crypto Bot"
#property version   "2.62"
#property strict

#include <Trade\Trade.mqh>

CTrade trade;

void SetSymbolFilling(string sym)
{
   uint filling = (uint)SymbolInfoInteger(sym, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_FOK) != 0)
      trade.SetTypeFilling(ORDER_FILLING_FOK);
   else if((filling & SYMBOL_FILLING_IOC) != 0)
      trade.SetTypeFilling(ORDER_FILLING_IOC);
   else
      trade.SetTypeFilling(ORDER_FILLING_RETURN);
}

string ResolveBrokerSymbol(string logicalSym)
{
   if(logicalSym == "BTCUSD")
   {
      string cands[] = {"BTCUSD", "BTCUSD.", "BTCUSDm", "#BTCUSD"};
      for(int i = 0; i < ArraySize(cands); i++)
         if(SymbolSelect(cands[i], true)) return cands[i];
   }
   else if(logicalSym == "XAUUSD")
   {
      string cands[] = {"XAUUSD", "XAUUSD.", "XAUUSDm", "GOLD"};
      for(int i = 0; i < ArraySize(cands); i++)
         if(SymbolSelect(cands[i], true)) return cands[i];
   }
   else if(logicalSym == "NAS100")
   {
      string cands[] = {"NAS100", "US100", "NDX", "USTEC", "#NDX", "NAS100.", "US100Roll", "NQ100"};
      for(int i = 0; i < ArraySize(cands); i++)
         if(SymbolSelect(cands[i], true)) return cands[i];
      int tot = SymbolsTotal(false);
      for(int s = 0; s < tot; s++)
      {
         string sn = SymbolName(s, false);
         if(StringFind(sn, "NAS") >= 0 || StringFind(sn, "NDX") >= 0 || StringFind(sn, "US100") >= 0 || StringFind(sn, "USTEC") >= 0)
            if(SymbolSelect(sn, true)) return sn;
      }
   }
   else if(logicalSym == "US500")
   {
      string cands[] = {"US500", "SPX500", "SP500", "SPX", "#SPX", "US500.", "US500Roll", "SPX500."};
      for(int i = 0; i < ArraySize(cands); i++)
         if(SymbolSelect(cands[i], true)) return cands[i];
      int tot = SymbolsTotal(false);
      for(int s = 0; s < tot; s++)
      {
         string sn = SymbolName(s, false);
         if(StringFind(sn, "US500") >= 0 || StringFind(sn, "SPX") >= 0 || StringFind(sn, "SP500") >= 0)
            if(SymbolSelect(sn, true)) return sn;
      }
   }
   SymbolSelect(logicalSym, true);
   return logicalSym;
}

string NormalizeLogicalSymbol(string brokerSym)
{
   if(StringFind(brokerSym, "BTC") >= 0) return "BTCUSD";
   if(StringFind(brokerSym, "XAU") >= 0 || StringFind(brokerSym, "GOLD") >= 0) return "XAUUSD";
   if(StringFind(brokerSym, "NAS") >= 0 || StringFind(brokerSym, "NDX") >= 0 || StringFind(brokerSym, "US100") >= 0 || StringFind(brokerSym, "USTEC") >= 0) return "NAS100";
   if(StringFind(brokerSym, "500") >= 0 || StringFind(brokerSym, "SPX") >= 0) return "US500";
   return brokerSym;
}

int OnInit()
{
   trade.SetExpertMagicNumber(202605);
   trade.SetDeviationInPoints(50);
   ResolveBrokerSymbol("BTCUSD");
   ResolveBrokerSymbol("XAUUSD");
   ResolveBrokerSymbol("NAS100");
   ResolveBrokerSymbol("US500");
   EventSetMillisecondTimer(500);
   OnTimer();
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void EnforceSinglePositionPerSymbol(string sym)
{
   int total = PositionsTotal();
   if(total <= 1) return;

   ulong newestTicket = 0;
   long  newestTime   = -1;

   for(int i = 0; i < total; i++)
   {
      ulong pt = PositionGetTicket(i);
      if(pt == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != sym) continue;
      long ptime = PositionGetInteger(POSITION_TIME_MSC);
      if(ptime > newestTime || (ptime == newestTime && pt > newestTicket))
      {
         newestTime   = ptime;
         newestTicket = pt;
      }
   }

   if(newestTicket == 0) return;

   for(int i = total - 1; i >= 0; i--)
   {
      ulong pt = PositionGetTicket(i);
      if(pt == 0 || pt == newestTicket) continue;
      if(PositionGetString(POSITION_SYMBOL) != sym) continue;
      SetSymbolFilling(sym);
      trade.PositionClose(pt);
   }
}

void ProcessCommands()
{
   if(!FileIsExist("mt5_cmd.txt"))
      return;

   if(!FileMove("mt5_cmd.txt", 0, "mt5_cmd_proc.txt", FILE_REWRITE))
      return;

   int h = FileOpen("mt5_cmd_proc.txt", FILE_READ|FILE_TXT|FILE_ANSI);
   if(h == INVALID_HANDLE)
      return;

   string lines[];
   int count = 0;
   while(!FileIsEnding(h))
   {
      string line = FileReadString(h);
      StringTrimLeft(line);
      StringTrimRight(line);
      if(StringLen(line) > 0)
      {
         ArrayResize(lines, count + 1);
         lines[count] = line;
         count++;
      }
   }
   FileClose(h);
   FileDelete("mt5_cmd_proc.txt");

   for(int i = 0; i < count; i++)
   {
      string parts[];
      int n = StringSplit(lines[i], '|', parts);
      if(n < 2) continue;
      string act = parts[0];

      if(act == "OPEN" && n >= 6)
      {
         string logicalSym = parts[1];
         string sym = ResolveBrokerSymbol(logicalSym);
         string ptype = parts[2];
         double vol = StringToDouble(parts[3]);
         double sl = StringToDouble(parts[4]);
         double tp = StringToDouble(parts[5]);
         string comment = (n >= 7) ? parts[6] : "CryptoBot";

         SymbolSelect(sym, true);
         SetSymbolFilling(sym);

         // Закрываем встречные сделки и блокируем дубликаты в том же направлении
         bool alreadySameSide = false;
         for(int p = PositionsTotal() - 1; p >= 0; p--)
         {
            ulong pticket = PositionGetTicket(p);
            if(pticket == 0) continue;
            if(PositionGetString(POSITION_SYMBOL) != sym) continue;
            long existingType = PositionGetInteger(POSITION_TYPE);
            bool existingIsBuy = (existingType == POSITION_TYPE_BUY);
            bool wantBuy = (ptype == "BUY");
            if(existingIsBuy != wantBuy)
            {
               trade.PositionClose(pticket);
            }
            else
            {
               alreadySameSide = true;
            }
         }
         if(alreadySameSide) continue;

         int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
         sl = NormalizeDouble(sl, digits);
         tp = NormalizeDouble(tp, digits);

         if(ptype == "BUY")
            trade.Buy(vol, sym, 0.0, sl, tp, comment);
         else
            trade.Sell(vol, sym, 0.0, sl, tp, comment);
      }
      else if(act == "CLOSE" && n >= 2)
      {
         ulong ticket = (ulong)StringToInteger(parts[1]);
         if(PositionSelectByTicket(ticket))
         {
            SetSymbolFilling(PositionGetString(POSITION_SYMBOL));
            trade.PositionClose(ticket);
         }
      }
      else if(act == "SAFE" && n >= 5)
      {
         ulong ticket = (ulong)StringToInteger(parts[1]);
         double closeVol = StringToDouble(parts[2]);
         double newSl = StringToDouble(parts[3]);
         double tp = StringToDouble(parts[4]);
         if(PositionSelectByTicket(ticket))
         {
            string sym = PositionGetString(POSITION_SYMBOL);
            SetSymbolFilling(sym);
            int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
            trade.PositionClosePartial(ticket, closeVol);
            if(PositionSelectByTicket(ticket))
               trade.PositionModify(ticket, NormalizeDouble(newSl, digits), NormalizeDouble(tp, digits));
         }
      }
      else if(act == "BE" && n >= 4)
      {
         ulong ticket = (ulong)StringToInteger(parts[1]);
         double newSl = StringToDouble(parts[2]);
         double tp = StringToDouble(parts[3]);
         if(PositionSelectByTicket(ticket))
         {
            string sym = PositionGetString(POSITION_SYMBOL);
            int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
            trade.PositionModify(ticket, NormalizeDouble(newSl, digits), NormalizeDouble(tp, digits));
         }
      }
   }
}

void WriteStateJson()
{
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   bool connected = (login > 0 && TerminalInfoInteger(TERMINAL_CONNECTED) != 0);
   string server = AccountInfoString(ACCOUNT_SERVER);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double profit = AccountInfoDouble(ACCOUNT_PROFIT);
   double margin = AccountInfoDouble(ACCOUNT_MARGIN);
   double free_margin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);

   string bSymBtc = ResolveBrokerSymbol("BTCUSD");
   double btcBid = SymbolInfoDouble(bSymBtc, SYMBOL_BID);
   double btcAsk = SymbolInfoDouble(bSymBtc, SYMBOL_ASK);
   long btcSpread = SymbolInfoInteger(bSymBtc, SYMBOL_SPREAD);

   string bSymXau = ResolveBrokerSymbol("XAUUSD");
   double xauBid = SymbolInfoDouble(bSymXau, SYMBOL_BID);
   double xauAsk = SymbolInfoDouble(bSymXau, SYMBOL_ASK);
   long xauSpread = SymbolInfoInteger(bSymXau, SYMBOL_SPREAD);

   string bSymNas = ResolveBrokerSymbol("NAS100");
   double nasBid = SymbolInfoDouble(bSymNas, SYMBOL_BID);
   double nasAsk = SymbolInfoDouble(bSymNas, SYMBOL_ASK);
   long nasSpread = SymbolInfoInteger(bSymNas, SYMBOL_SPREAD);

   string bSymSp = ResolveBrokerSymbol("US500");
   double spBid = SymbolInfoDouble(bSymSp, SYMBOL_BID);
   double spAsk = SymbolInfoDouble(bSymSp, SYMBOL_ASK);
   long spSpread = SymbolInfoInteger(bSymSp, SYMBOL_SPREAD);

   string json = "{";
   json += "\"connected\":" + (connected ? "true" : "false") + ",";
   json += "\"login\":" + IntegerToString(login) + ",";
   json += "\"server\":\"" + server + "\",";
   json += "\"account\":{";
   json += "\"balance\":" + DoubleToString(balance, 2) + ",";
   json += "\"equity\":" + DoubleToString(equity, 2) + ",";
   json += "\"floating_pnl\":" + DoubleToString(profit, 2) + ",";
   json += "\"used_margin\":" + DoubleToString(margin, 2) + ",";
   json += "\"free_margin\":" + DoubleToString(free_margin, 2);
   json += "},";

   json += "\"ticks\":{";
   json += "\"BTCUSD\":{\"bid\":" + DoubleToString(btcBid, 2) + ",\"ask\":" + DoubleToString(btcAsk, 2) + ",\"spread\":" + IntegerToString(btcSpread) + "},";
   json += "\"XAUUSD\":{\"bid\":" + DoubleToString(xauBid, 2) + ",\"ask\":" + DoubleToString(xauAsk, 2) + ",\"spread\":" + IntegerToString(xauSpread) + "},";
   json += "\"NAS100\":{\"bid\":" + DoubleToString(nasBid, 2) + ",\"ask\":" + DoubleToString(nasAsk, 2) + ",\"spread\":" + IntegerToString(nasSpread) + "},";
   json += "\"US500\":{\"bid\":" + DoubleToString(spBid, 2) + ",\"ask\":" + DoubleToString(spAsk, 2) + ",\"spread\":" + IntegerToString(spSpread) + "}";
   json += "},";

   // Open positions
   json += "\"positions\":[";
   int totalPos = PositionsTotal();
   bool firstPos = true;
   for(int i = 0; i < totalPos; i++)
   {
      ulong pticket = PositionGetTicket(i);
      if(pticket == 0) continue;
      string psym = NormalizeLogicalSymbol(PositionGetString(POSITION_SYMBOL));
      long ptype = PositionGetInteger(POSITION_TYPE);
      double pvol = PositionGetDouble(POSITION_VOLUME);
      double popen = PositionGetDouble(POSITION_PRICE_OPEN);
      double pcur = PositionGetDouble(POSITION_PRICE_CURRENT);
      double psl = PositionGetDouble(POSITION_SL);
      double ptp = PositionGetDouble(POSITION_TP);
      double ppnl = PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
      long ptime = PositionGetInteger(POSITION_TIME);

      bool isBuy = (ptype == POSITION_TYPE_BUY);
      bool isBe = isBuy ? (psl >= popen && psl > 0) : (psl <= popen && psl > 0);

      if(!firstPos) json += ",";
      firstPos = false;
      json += "{";
      json += "\"ticket\":" + IntegerToString((long)pticket) + ",";
      json += "\"symbol\":\"" + psym + "\",";
      json += "\"pos_type\":\"" + (isBuy ? "BUY" : "SELL") + "\",";
      json += "\"volume\":" + DoubleToString(pvol, 2) + ",";
      json += "\"initial_volume\":" + DoubleToString(pvol, 2) + ",";
      json += "\"open_price\":" + DoubleToString(popen, 2) + ",";
      json += "\"current_price\":" + DoubleToString(pcur, 2) + ",";
      json += "\"sl\":" + DoubleToString(psl, 2) + ",";
      json += "\"tp\":" + DoubleToString(ptp, 2) + ",";
      json += "\"pnl\":" + DoubleToString(ppnl, 2) + ",";
      json += "\"open_time\":" + IntegerToString(ptime) + ",";
      json += "\"is_partial_done\":false,";
      json += "\"is_breakeven\":" + (isBe ? "true" : "false");
      json += "}";
   }
   json += "],";

   // Closed deal history (last 14 days)
   json += "\"history\":[";
   if(HistorySelect(TimeCurrent() - 86400 * 14, TimeCurrent() + 3600))
   {
      int totalDeals = HistoryDealsTotal();
      int added = 0;
      for(int i = totalDeals - 1; i >= 0 && added < 15; i--)
      {
         ulong dticket = HistoryDealGetTicket(i);
         if(dticket == 0) continue;
         long dentry = HistoryDealGetInteger(dticket, DEAL_ENTRY);
         if(dentry != DEAL_ENTRY_OUT && dentry != DEAL_ENTRY_INOUT) continue;
         long dtype = HistoryDealGetInteger(dticket, DEAL_TYPE);
         if(dtype != DEAL_TYPE_BUY && dtype != DEAL_TYPE_SELL) continue;

         string dsym = NormalizeLogicalSymbol(HistoryDealGetString(dticket, DEAL_SYMBOL));
         double dvol = HistoryDealGetDouble(dticket, DEAL_VOLUME);
         double dprice = HistoryDealGetDouble(dticket, DEAL_PRICE);
         double dpnl = HistoryDealGetDouble(dticket, DEAL_PROFIT) + HistoryDealGetDouble(dticket, DEAL_SWAP) + HistoryDealGetDouble(dticket, DEAL_COMMISSION);
         long dtime = HistoryDealGetInteger(dticket, DEAL_TIME);
         // Closing a BUY position uses a SELL deal, so original position was opposite
         string origType = (dtype == DEAL_TYPE_SELL) ? "BUY" : "SELL";

         if(added > 0) json += ",";
         added++;
         json += "{";
         json += "\"ticket\":" + IntegerToString((long)dticket) + ",";
         json += "\"symbol\":\"" + dsym + "\",";
         json += "\"pos_type\":\"" + origType + "\",";
         json += "\"volume\":" + DoubleToString(dvol, 2) + ",";
         json += "\"open_price\":" + DoubleToString(dprice, 2) + ",";
         json += "\"close_price\":" + DoubleToString(dprice, 2) + ",";
         json += "\"pnl\":" + DoubleToString(dpnl, 2) + ",";
         json += "\"close_time\":" + IntegerToString(dtime) + ",";
         json += "\"reason\":\"MT5 Deal\"";
         json += "}";
      }
   }
   json += "]";
   json += "}";

   int h = FileOpen("mt5_state_tmp.json", FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(h != INVALID_HANDLE)
   {
      FileWriteString(h, json);
      FileClose(h);
      FileMove("mt5_state_tmp.json", 0, "mt5_state.json", FILE_REWRITE);
   }
}

void OnTimer()
{
   ProcessCommands();
   EnforceSinglePositionPerSymbol("BTCUSD");
   WriteStateJson();
}

void OnTick()
{
   ProcessCommands();
   WriteStateJson();
}
//+------------------------------------------------------------------+
