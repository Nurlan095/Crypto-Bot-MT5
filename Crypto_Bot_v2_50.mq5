//+------------------------------------------------------------------+
//|                                            Crypto_Bot_v2_50.mq5 |
//|   Custom Crypto Bot v2.5 for AMarkets (News Analyzer + 10% Risk) |
//+------------------------------------------------------------------+
#property copyright "Custom Crypto Bot v2.5 for AMarkets (News Analyzer + 10% Risk)"
#property version   "2.50"

#include <Trade\Trade.mqh>
CTrade trade;

// --- Входные параметры ---
input group "=== Управление капиталом (Крипто + 10% Риск) ==="
input bool   InpUseAutoLot        = true;      // Авто-расчет лота от баланса
input double InpRiskPercent       = 3.0;       // Риск на сделку в % от баланса
input double InpMaxMarginUsage    = 80.0;      // Макс. загрузка свободной маржи (%)
input double InpFixedLot          = 0.02;      // Фиксированный лот (если Авто-лот = false)
input ulong  InpMagicNumber       = 777999;    // Magic Number (Крипто)
input int    InpMaxSpreadPoints   = 3500;      // Макс. спред в пунктах (для BTCUSD ~35$, 0 = выкл)

input group "=== Фильтр и Анализ Новостей (Календарь MT5) ==="
input bool   InpUseNewsFilter     = true;      // Включить защиту и анализ новостей
input string InpNewsCurrency      = "USD";     // Валюта новостей (USD влияет на BTC и XAU)
input int    InpPauseBeforeMin    = 15;        // Пауза ДО важной новости (минут)
input int    InpPauseAfterMin     = 5;         // Пауза ПОСЛЕ выхода новости (минут)
input bool   InpTradeNewsImpulse  = true;      // Фильтровать направление по Факту vs Прогнозу
input int    InpNewsEffectMin     = 60;        // Время действия новостного импульса (минут)

input group "=== Структура и паттерны (M15) ==="
input int    InpSwingPeriod       = 5;         // Период поиска свингов (фракталов)
input int    InpATRPeriod         = 14;        // Период ATR
input double InpATRMultiplier     = 1.1;       // Множитель ATR для импульсной свечи
input double InpMarubozuRatio     = 0.70;      // Мин. доля тела свечи Марубозу (0.7 = 70%)

input group "=== Коробка Мандарин ==="
input bool   InpUseMandarin       = true;      // Использовать фильтр «Мандарин»
input int    InpMandarinBars      = 3;         // Количество свечей консолидации
input double InpMandarinMaxATR    = 1.8;       // Макс. высота коробки в ATR

input group "=== Фильтр старшего тренда (H1) ==="
input bool            InpUseHTFFilter = true;      // Фильтровать сделки по тренду H1
input ENUM_TIMEFRAMES InpHTF          = PERIOD_H1; // Старший таймфрейм
input int             InpHTF_EMA      = 50;        // Период EMA на старшем ТФ

input group "=== Стопы, Сейф (Частичное закрытие) и Безубыток ==="
input double InpSL_ATR            = 1.5;       // Стоп-лосс в ATR
input double InpTP_ATR            = 3.0;       // Основной Тейк-профит в ATR
input bool   InpUsePartialClose   = true;      // Включить частичное закрытие (Сейф)
input double InpPartialTrigATR    = 1.5;       // На каком профите в ATR закрывать часть (1.5 ATR)
input double InpPartialClosePct   = 50.0;      // Какой % лота закрывать (50%)
input bool   InpUseBreakeven      = true;      // Автоперевод в безубыток
input double InpBE_TriggerATR     = 1.5;       // Триггер безубытка в ATR
input double InpBE_OffsetATR      = 0.20;      // Защитный отступ безубытка в ATR

input group "=== Визуализация на графике ==="
input bool   InpShowVisuals       = true;      // Рисовать коробку Мандарин и уровни BOS

// --- Глобальные переменные ---
int      atrHandle;
int      htfEmaHandle;
datetime lastBarTime       = 0;
double   lastSwingHigh     = 0;
datetime lastSwingHighTime = 0;
double   lastSwingLow      = 0;
datetime lastSwingLowTime  = 0;

int OnInit()
{
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(50);
   trade.SetMarginMode();
   trade.SetTypeFillingBySymbol(_Symbol);
   
   atrHandle = iATR(_Symbol, _Period, InpATRPeriod);
   if(atrHandle == INVALID_HANDLE) return(INIT_FAILED);
   
   if(InpUseHTFFilter)
   {
      htfEmaHandle = iMA(_Symbol, InpHTF, InpHTF_EMA, 0, MODE_EMA, PRICE_CLOSE);
      if(htfEmaHandle == INVALID_HANDLE) return(INIT_FAILED);
   }
   
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   IndicatorRelease(atrHandle);
   if(InpUseHTFFilter) IndicatorRelease(htfEmaHandle);
   ObjectsDeleteAll(0, "BMS_");
   Comment("");
}

// --- БЛОК АНАЛИЗА НОВОСТЕЙ MT5 ---
// Возвращает:
// outBias: 0 = нейтрально, 1 = Позитив для Крипты/Золота (Слабый USD -> BUY), -1 = Негатив (Сильный USD -> SELL)
bool AnalyzeMarketNews(bool &outIsPaused, int &outBias, string &outNewsStatus)
{
   outIsPaused   = false;
   outBias       = 0;
   outNewsStatus = "Спокойно (Новостей нет)";
   
   if(!InpUseNewsFilter)
   {
      outNewsStatus = "Выключен";
      return true;
   }
   
   // В тестере стратегий встроенный календарь недоступен, поэтому пропускаем проверку
   if(MQLInfoInteger(MQL_TESTER))
   {
      outNewsStatus = "Режим Тестера (Календарь отключен)";
      return true;
   }
   
   MqlCalendarValue values[];
   datetime timeNow  = TimeTradeServer();
   datetime timeFrom = timeNow - InpNewsEffectMin * 60;
   datetime timeTo   = timeNow + InpPauseBeforeMin * 60;
   
   if(!CalendarValueHistory(values, timeFrom, timeTo, NULL, InpNewsCurrency))
      return true;
      
   for(int i = 0; i < ArraySize(values); i++)
   {
      MqlCalendarEvent event;
      if(!CalendarEventById(values[i].event_id, event)) continue;
      
      // Берем только важные новости (High Importance = 3 звезды)
      if(event.importance != CALENDAR_IMPORTANCE_HIGH) continue;
      
      datetime eventTime = values[i].time;
      int diffSec = (int)(timeNow - eventTime); // Отрицательное = новость впереди, положительное = уже вышла
      
      // 1. Проверка паузы ДО и сразу ПОСЛЕ выхода новости
      if(diffSec >= -(InpPauseBeforeMin * 60) && diffSec <= (InpPauseAfterMin * 60))
      {
         outIsPaused   = true;
         outNewsStatus = StringFormat("ПАУЗА! Новость: %s (через/прошло %d мин)", event.name, diffSec / 60);
         return true;
      }
      
      // 2. Анализ вышедших данных (Факт против Прогноза) после окончания паузы
      if(InpTradeNewsImpulse && diffSec > (InpPauseAfterMin * 60) && diffSec <= (InpNewsEffectMin * 60))
      {
         if(values[i].HasActualValue() && values[i].HasForecastValue())
         {
            // В MQL5 impact_type показывает влияние на базовую валюту (USD):
            // CALENDAR_IMPACT_POSITIVE = USD растет (значит BTCUSD/XAUUSD падают -> SELL)
            // CALENDAR_IMPACT_NEGATIVE = USD падает (значит BTCUSD/XAUUSD растут -> BUY)
            if(values[i].impact_type == CALENDAR_IMPACT_POSITIVE)
            {
               outBias       = -1; // Сильный доллар -> Ищем SELL по BTCUSD
               outNewsStatus = StringFormat("Сильный USD (%s) -> Ищем SELL", event.name);
            }
            else if(values[i].impact_type == CALENDAR_IMPACT_NEGATIVE)
            {
               outBias       = 1;  // Слабый доллар -> Ищем BUY по BTCUSD
               outNewsStatus = StringFormat("Слабый USD (%s) -> Ищем BUY", event.name);
            }
            else
            {
               // Резервный расчет по разнице Факт - Прогноз
               double actual   = values[i].GetActualValue();
               double forecast = values[i].GetForecastValue();
               if(actual > forecast)
               {
                  outBias       = -1;
                  outNewsStatus = StringFormat("%s: Факт (%.2f) > Прогноз (%.2f) [SELL]", event.name, actual, forecast);
               }
               else if(actual < forecast)
               {
                  outBias       = 1;
                  outNewsStatus = StringFormat("%s: Факт (%.2f) < Прогноз (%.2f) [BUY]", event.name, actual, forecast);
               }
            }
         }
      }
   }
   return true;
}

// Поиск последних подтвержденных и НЕпробитых экстремумов (Swing High / Swing Low)
void UpdateMarketStructure()
{
   int    lookback     = 120;
   double fallbackHigh = 0;
   datetime fallbackHighTime = 0;
   double fallbackLow  = 0;
   datetime fallbackLowTime  = 0;
   
   for(int i = InpSwingPeriod + 2; i < lookback; i++)
   {
      bool isHigh = true;
      bool isLow  = true;
      double currentHigh = iHigh(_Symbol, _Period, i);
      double currentLow  = iLow(_Symbol, _Period, i);
      
      for(int j = 1; j <= InpSwingPeriod; j++)
      {
         if(iHigh(_Symbol, _Period, i - j) >= currentHigh || iHigh(_Symbol, _Period, i + j) > currentHigh) isHigh = false;
         if(iLow(_Symbol, _Period, i - j) <= currentLow  || iLow(_Symbol, _Period, i + j) < currentLow)  isLow  = false;
      }
      
      if(isHigh && fallbackHigh == 0) { fallbackHigh = currentHigh; fallbackHighTime = iTime(_Symbol, _Period, i); }
      if(isLow  && fallbackLow == 0)  { fallbackLow  = currentLow;  fallbackLowTime  = iTime(_Symbol, _Period, i); }
      
      // Проверяем, что уровень еще не был пробит свечами между i-1 и 2
      if(isHigh)
      {
         for(int k = 2; k < i; k++)
         {
            if(iClose(_Symbol, _Period, k) > currentHigh) { isHigh = false; break; }
         }
      }
      if(isLow)
      {
         for(int k = 2; k < i; k++)
         {
            if(iClose(_Symbol, _Period, k) < currentLow) { isLow = false; break; }
         }
      }
      
      if(isHigh && lastSwingHigh == 0)
      {
         lastSwingHigh     = currentHigh;
         lastSwingHighTime = iTime(_Symbol, _Period, i);
      }
      if(isLow && lastSwingLow == 0)
      {
         lastSwingLow     = currentLow;
         lastSwingLowTime = iTime(_Symbol, _Period, i);
      }
      if(lastSwingHigh > 0 && lastSwingLow > 0) break;
   }
   
   if(lastSwingHigh == 0 && fallbackHigh > 0) { lastSwingHigh = fallbackHigh; lastSwingHighTime = fallbackHighTime; }
   if(lastSwingLow  == 0 && fallbackLow  > 0) { lastSwingLow  = fallbackLow;  lastSwingLowTime  = fallbackLowTime;  }
}

// Отрисовка уровней BOS и коробки Мандарин на графике
void DrawStructureAndBox(bool isMandarinValid, double boxHigh, double boxLow)
{
   if(!InpShowVisuals) return;
   datetime timeNow = iTime(_Symbol, _Period, 0);
   
   if(lastSwingHigh > 0)
   {
      string nameH = "BMS_SwingHigh";
      ObjectDelete(0, nameH);
      ObjectCreate(0, nameH, OBJ_TREND, 0, lastSwingHighTime, lastSwingHigh, timeNow, lastSwingHigh);
      ObjectSetInteger(0, nameH, OBJPROP_COLOR, clrLimeGreen);
      ObjectSetInteger(0, nameH, OBJPROP_WIDTH, 2);
      ObjectSetInteger(0, nameH, OBJPROP_RAY_RIGHT, false);
   }
   
   if(lastSwingLow > 0)
   {
      string nameL = "BMS_SwingLow";
      ObjectDelete(0, nameL);
      ObjectCreate(0, nameL, OBJ_TREND, 0, lastSwingLowTime, lastSwingLow, timeNow, lastSwingLow);
      ObjectSetInteger(0, nameL, OBJPROP_COLOR, clrCrimson);
      ObjectSetInteger(0, nameL, OBJPROP_WIDTH, 2);
      ObjectSetInteger(0, nameL, OBJPROP_RAY_RIGHT, false);
   }
   
   if(isMandarinValid && InpUseMandarin)
   {
      string boxName = "BMS_Mandarin_" + TimeToString(iTime(_Symbol, _Period, 1), TIME_DATE|TIME_MINUTES);
      datetime tStart = iTime(_Symbol, _Period, 1 + InpMandarinBars);
      datetime tEnd   = iTime(_Symbol, _Period, 2);
      
      ObjectCreate(0, boxName, OBJ_RECTANGLE, 0, tStart, boxHigh, tEnd, boxLow);
      ObjectSetInteger(0, boxName, OBJPROP_COLOR, clrOrange);
      ObjectSetInteger(0, boxName, OBJPROP_FILL, true);
      ObjectSetInteger(0, boxName, OBJPROP_BACK, true);
   }
}

bool CheckMandarinBox(double atr, double &outHigh, double &outLow)
{
   outHigh = -DBL_MAX;
   outLow  = DBL_MAX;
   if(!InpUseMandarin) return true;
   
   for(int i = 2; i <= 1 + InpMandarinBars; i++)
   {
      double h = iHigh(_Symbol, _Period, i);
      double l = iLow(_Symbol, _Period, i);
      if(h > outHigh) outHigh = h;
      if(l < outLow)  outLow  = l;
   }
   return ((outHigh - outLow) <= (atr * InpMandarinMaxATR));
}

double CalculateCryptoLotSize(ENUM_ORDER_TYPE orderType, double entryPrice, double slDistancePrice)
{
   if(!InpUseAutoLot || slDistancePrice <= 0) return InpFixedLot;
   
   double balance   = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskMoney = balance * (InpRiskPercent / 100.0);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   
   if(tickValue <= 0 || tickSize <= 0) return InpFixedLot;
   
   double slTicks = slDistancePrice / tickSize;
   if(slTicks < 1.0) slTicks = 1.0;
   double rawLot  = riskMoney / (slTicks * tickValue);
   
   double minLot   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double volLimit = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_LIMIT);
   double stepLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(volLimit > 0 && maxLot > volLimit) maxLot = volLimit;
   
   double marginForOneLot = 0;
   if(OrderCalcMargin(orderType, _Symbol, 1.0, entryPrice, marginForOneLot) && marginForOneLot > 0)
   {
      double maxAllowedMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE) * (InpMaxMarginUsage / 100.0);
      double maxMarginLot     = maxAllowedMargin / marginForOneLot;
      if(rawLot > maxMarginLot) rawLot = maxMarginLot;
   }
   
   double lot = MathFloor(rawLot / stepLot) * stepLot;
   if(lot < minLot) lot = minLot;
   if(lot > maxLot) lot = maxLot;
   
   int lotDigits = (stepLot >= 1.0) ? 0 : ((stepLot >= 0.1) ? 1 : 2);
   return NormalizeDouble(lot, lotDigits);
}

int GetHTFTrendDirection()
{
   if(!InpUseHTFFilter) return 0;
   double emaVal[];
   ArraySetAsSeries(emaVal, true);
   if(CopyBuffer(htfEmaHandle, 0, 1, 3, emaVal) < 3) return 0;
   
   double htfClose = iClose(_Symbol, InpHTF, 1);
   if(htfClose > emaVal[0] && emaVal[0] > emaVal[2]) return 1;
   if(htfClose < emaVal[0] && emaVal[0] < emaVal[2]) return -1;
   return 0;
}

void ManagePositions(double atr)
{
   if(atr <= 0) return;
   
   double stopLevelDist = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   double minLot        = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double stepLot       = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   int    lotDigits     = (stepLot >= 1.0) ? 0 : ((stepLot >= 0.1) ? 1 : 2);
   
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
      {
         double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
         double currentSL = PositionGetDouble(POSITION_SL);
         double currentTP = PositionGetDouble(POSITION_TP);
         double volume    = PositionGetDouble(POSITION_VOLUME);
         long   posType   = PositionGetInteger(POSITION_TYPE);
         
         double offsetDist  = atr * InpBE_OffsetATR;
         double partialDist = atr * InpPartialTrigATR;
         double beTrigDist  = atr * InpBE_TriggerATR;
         double closeVol    = MathFloor((volume * (InpPartialClosePct / 100.0)) / stepLot) * stepLot;
         closeVol           = NormalizeDouble(closeVol, lotDigits);
         bool   canPartial  = (InpUsePartialClose && closeVol >= minLot && (volume - closeVol) >= minLot);
         
         if(posType == POSITION_TYPE_BUY)
         {
            double bid   = SymbolInfoDouble(_Symbol, SYMBOL_BID);
            double newSL = NormalizeDouble(openPrice + offsetDist, _Digits);
            bool   isAlreadyBE = (currentSL >= openPrice);
            
            if(canPartial && !isAlreadyBE && bid >= (openPrice + partialDist))
            {
               trade.PositionClosePartial(ticket, closeVol);
               ulong newTicket = PositionGetTicket(i);
               if(newTicket > 0 && (bid - newSL) > stopLevelDist)
                  trade.PositionModify(newTicket, newSL, currentTP);
               continue;
            }
            
            // Если лот минимальный (0.01) и дробить нельзя — переводим в БУ с запасом +0.6 ATR при достижении 2.0 ATR
            double effTrig = canPartial ? beTrigDist : (atr * 2.0);
            double effSL   = canPartial ? newSL : NormalizeDouble(openPrice + atr * 0.60, _Digits);
            if(InpUseBreakeven && !isAlreadyBE && bid >= (openPrice + effTrig) && (bid - effSL) > stopLevelDist)
               trade.PositionModify(ticket, effSL, currentTP);
         }
         else if(posType == POSITION_TYPE_SELL)
         {
            double ask   = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
            double newSL = NormalizeDouble(openPrice - offsetDist, _Digits);
            bool   isAlreadyBE = (currentSL > 0 && currentSL <= openPrice);
            
            if(canPartial && !isAlreadyBE && ask <= (openPrice - partialDist))
            {
               trade.PositionClosePartial(ticket, closeVol);
               ulong newTicket = PositionGetTicket(i);
               if(newTicket > 0 && (newSL - ask) > stopLevelDist)
                  trade.PositionModify(newTicket, newSL, currentTP);
               continue;
            }
            
            double effTrig = canPartial ? beTrigDist : (atr * 2.0);
            double effSL   = canPartial ? newSL : NormalizeDouble(openPrice - atr * 0.60, _Digits);
            if(InpUseBreakeven && !isAlreadyBE && ask <= (openPrice - effTrig) && (newSL - ask) > stopLevelDist)
               trade.PositionModify(ticket, effSL, currentTP);
         }
      }
   }
}

bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber) return true;
   }
   return false;
}

void OnTick()
{
   double atrVal[];
   if(CopyBuffer(atrHandle, 0, 1, 1, atrVal) <= 0) return;
   double atr = atrVal[0];
   
   ManagePositions(atr);
   
   int    htfTrend      = GetHTFTrendDirection();
   long   currentSpread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   double askPrice      = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bidPrice      = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double slDistance    = atr * InpSL_ATR;
   double tpDistance    = atr * InpTP_ATR;
   
   // Запускаем анализатор новостей
   bool   newsPaused = false;
   int    newsBias   = 0;
   string newsStatus = "";
   AnalyzeMarketNews(newsPaused, newsBias, newsStatus);
   
   if(lastSwingHigh == 0 || lastSwingLow == 0)
   {
      UpdateMarketStructure();
      double initBoxH = 0, initBoxL = 0;
      bool initMandarin = CheckMandarinBox(atr, initBoxH, initBoxL);
      DrawStructureAndBox(initMandarin, initBoxH, initBoxL);
   }
   
   if(InpShowVisuals)
   {
      string trendText  = (htfTrend == 1) ? "ВВЕРХ (Только BUY)" : ((htfTrend == -1) ? "ВНИЗ (Только SELL)" : "НЕЙТРАЛЬНО");
      double previewLot = CalculateCryptoLotSize(ORDER_TYPE_BUY, askPrice, slDistance);
      double riskUsd    = AccountInfoDouble(ACCOUNT_BALANCE) * (InpRiskPercent / 100.0);
      Comment(StringFormat("=== CRYPTO BOT v2.5 (AI NEWS + СЕЙФ 50%%) ===\nАктив: %s | Тренд H1: %s\nАнализ Новостей (%s): %s\nATR(14): %.2f | Спред: %d пт.\nРиск: %.1f%% (%.2f USD) | Расчетный лот: %.2f\nСейф: %.0f%% лота на %.1f ATR | Тейк: %.1f ATR\nSwing High: %.2f | Swing Low: %.2f",
              _Symbol, trendText, InpNewsCurrency, newsStatus, atr, currentSpread, InpRiskPercent, riskUsd, previewLot, InpPartialClosePct, InpPartialTrigATR, InpTP_ATR, lastSwingHigh, lastSwingLow));
   }
   
   // Если идет новостная пауза — новые сделки не открываем (но старые сопровождаем)
   if(newsPaused) return;
   
   datetime currentBarTime = iTime(_Symbol, _Period, 0);
   if(currentBarTime == lastBarTime) return;
   
   if(HasOpenPosition())
   {
      lastBarTime = currentBarTime;
      return;
   }
   if(InpMaxSpreadPoints > 0 && currentSpread > InpMaxSpreadPoints) return;
   
   lastSwingHigh = 0;
   lastSwingLow  = 0;
   UpdateMarketStructure();
   if(lastSwingHigh == 0 || lastSwingLow == 0) return;
   
   double open1  = iOpen(_Symbol, _Period, 1);
   double close1 = iClose(_Symbol, _Period, 1);
   double high1  = iHigh(_Symbol, _Period, 1);
   double low1   = iLow(_Symbol, _Period, 1);
   double close2 = iClose(_Symbol, _Period, 2);
   
   double range = high1 - low1;
   double body  = MathAbs(close1 - open1);
   if(range == 0) return;
   
   bool   isMarubozu  = (body / range) >= InpMarubozuRatio;
   bool   isStrongATR = (range >= (atr * InpATRMultiplier) && range <= (atr * 2.5));
   bool   isSqueeze   = ((atr / close1) <= 0.0026);
   
   MqlDateTime dt;
   TimeToStruct(currentBarTime, dt);
   bool   isActiveSession = !(dt.hour == 2 || dt.hour == 4 || dt.hour == 5 || dt.hour == 7 || dt.hour == 14 || dt.hour == 19);
   
   double boxH = 0, boxL = 0;
   bool   isMandarin  = (CheckMandarinBox(atr, boxH, boxL) && isSqueeze && isActiveSession);
   
   DrawStructureAndBox(isMandarin, boxH, boxL);
   lastBarTime = currentBarTime;
   
   // Проверяем согласие новостного импульса (если новость только что вышла, не торгуем против нее)
   bool allowBuyByNews  = (!InpTradeNewsImpulse || newsBias >= 0);
   bool allowSellByNews = (!InpTradeNewsImpulse || newsBias <= 0);
   
   // Вход BUY
   if(close1 > open1 && close2 <= lastSwingHigh && close1 > lastSwingHigh && isMarubozu && isStrongATR && isMandarin && (!InpUseHTFFilter || htfTrend == 1) && allowBuyByNews)
   {
      double lot = CalculateCryptoLotSize(ORDER_TYPE_BUY, askPrice, slDistance);
      double sl  = NormalizeDouble(askPrice - slDistance, _Digits);
      double tp  = NormalizeDouble(askPrice + tpDistance, _Digits);
      trade.Buy(lot, _Symbol, askPrice, sl, tp, "Crypto BOS+News Buy");
   }
   
   // Вход SELL
   if(close1 < open1 && close2 >= lastSwingLow && close1 < lastSwingLow && isMarubozu && isStrongATR && isMandarin && (!InpUseHTFFilter || htfTrend == -1) && allowSellByNews)
   {
      double lot = CalculateCryptoLotSize(ORDER_TYPE_SELL, bidPrice, slDistance);
      double sl  = NormalizeDouble(bidPrice + slDistance, _Digits);
      double tp  = NormalizeDouble(bidPrice - tpDistance, _Digits);
      trade.Sell(lot, _Symbol, bidPrice, sl, tp, "Crypto BOS+News Sell");
   }
}
