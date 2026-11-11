//+------------------------------------------------------------------+
//|                                       David_Trullas_Fibo_Bot.mq5 |
//|     Метод Давида Трульяса Вила (HLIT: MACD + RSI + Vol + Fibo)   |
//|     Специальная сборка для BTCUSD (AMarkets Demo / Live MT5)     |
//+------------------------------------------------------------------+
#property copyright "David Trullas Vila Method — Auto Fibonacci BTCUSD Bot"
#property link      "https://www.amarkets.com"
#property version   "1.00"
#property description "Автоматический бот по системе чемпиона мира Давида Трульяса Вила:"
#property description "1. Фильтр дивергенций и моментума MACD (12, 26, 9)"
#property description "2. Подтверждение скорости RSI (14) и тиковых объемов (Volume)"
#property description "3. Авто-построение сетки Фибоначчи: вход на пробое 23.6%, Сейф+БУ на 38.2%, Тейк на 61.8%/66%"
#property description "4. Жесткий дневной риск-менеджмент (лимит убытка в день, серия стопов, динамический риск по конфлюэнсу)"

#include <Trade\Trade.mqh>
CTrade trade;

// --- Перечисления настроек стратегии ---
enum ENUM_SIGNAL_MODE
{
   SIGNAL_DIVERGENCE_ONLY      = 0, // Только классическая дивергенция MACD (Строгий метод Трульяса)
   SIGNAL_DIVERGENCE_OR_IMPULSE= 1  // Дивергенция MACD ИЛИ разворот моментума после импульса
};

enum ENUM_HTF_MODE
{
   HTF_DISABLED                = 0, // Выключен (торговля всех сетапов интрадей)
   HTF_CONFLUENCE_BONUS        = 1, // Усиливать лот при совпадении со старшим трендом (Рекомендуется)
   HTF_STRICT_FILTER           = 2  // Строго только в сторону тренда старшего ТФ
};

// --- Входные параметры ---
input group "=== 1. Таймфреймы (Система Давида Трульяса) ==="
input ENUM_TIMEFRAMES   InpWorkTF            = PERIOD_M5;                 // Рабочий ТФ для сетки Фибоначчи (M1 / M5 / M15)
input ENUM_HTF_MODE     InpHTFMode           = HTF_CONFLUENCE_BONUS;      // Режим старшего таймфрейма (Контекст)
input ENUM_TIMEFRAMES   InpHTF               = PERIOD_H1;                 // Старший ТФ тренда (M15 / H1 / H4)
input int               InpHTF_EMA           = 50;                        // Период EMA на старшем ТФ

input group "=== 2. Сетка Фибоначчи (Авто-натяжка и Уровни) ==="
input int               InpPivotStrength     = 4;                         // Сила свинга (свечей слева и справа от пика)
input int               InpLookbackBars      = 120;                       // Глубина поиска свингов и дивергенций (баров)
input double            InpMinImpulseATR     = 1.6;                       // Мин. размер импульса для сетки Фибо (в ATR)
input double            InpFiboEntryLevel    = 0.236;                     // Уровень входа Фибоначчи (23.6% по Трульясу)
input double            InpFiboTP1Level      = 0.382;                     // Уровень TP1 / Сейф + Безубыток (38.2% по Трульясу)
input double            InpFiboTrailLevel    = 0.500;                     // Уровень подтяжки стопа в профит (50.0% Фибо)
input double            InpFiboTP2Level      = 0.618;                     // Главная цель TP2 (61.8% или 0.660 = 2/3 импульса)
input bool              InpRequireCandleClose= true;                      // Ждать закрытия свечи за уровнем 23.6% (защита от шума)

input group "=== 3. Фильтры Трульяса: MACD (12,26,9) + RSI (14) + Volume ==="
input ENUM_SIGNAL_MODE  InpSignalMode        = SIGNAL_DIVERGENCE_OR_IMPULSE; // Режим генерации сигнала
input int               InpMACD_Fast         = 12;                        // MACD Быстрая EMA (Классика: 12)
input int               InpMACD_Slow         = 26;                        // MACD Медленная EMA (Классика: 26)
input int               InpMACD_Signal       = 9;                         // MACD Сигнальная SMA (Классика: 9)
input int               InpRSI_Period        = 14;                        // Период RSI (Классика: 14)
input double            InpRSI_Overbought    = 65.0;                      // Зона перекупленности RSI (для SELL)
input double            InpRSI_Oversold      = 35.0;                      // Зона перепроданности RSI (для BUY)
input int               InpVolMAPeriod       = 20;                        // Период среднего объема (Tick Volume)

input group "=== 4. Риск-менеджмент и Мани-менеджмент Трульяса ==="
input bool              InpUseAutoLot        = true;                      // Авто-расчет лота от риска
input double            InpBaseRiskPercent   = 1.0;                       // Базовый риск на сделку (% от баланса)
input bool              InpUseConfluenceRisk = true;                      // Увеличивать риск при полном подтверждении (MACD+RSI+Vol)
input double            InpBonusRiskStep     = 0.5;                       // Надбавка к риску за каждый фильтр подтверждения (%)
input double            InpMaxRiskPercent    = 2.5;                       // Максимальный риск на сделку (%)
input double            InpFixedLot          = 0.02;                      // Фиксированный лот (если Авто-лот = false)
input double            InpMaxMarginUsage    = 80.0;                      // Макс. нагрузка на свободную маржу (%)
input double            InpSL_BufferATR      = 0.25;                      // Защитный отступ Stop Loss за экстремум 0% (в ATR)
input bool              InpUsePartialClose   = true;                      // Закрывать часть позиции на уровне 38.2% («Сейф»)
input double            InpTP1_ClosePercent  = 50.0;                      // Какой % объема закрывать на 38.2% Фибо
input bool              InpUseBreakeven      = true;                      // Переводить остаток в Безубыток на 38.2% Фибо
input double            InpBE_OffsetATR      = 0.15;                      // Защитный плюс безубытка (в ATR)

input group "=== 5. Дневные лимиты (Дисциплина Чемпионата Мира) ==="
input double            InpMaxDailyLossPct   = 4.0;                       // Макс. дневной убыток в % от баланса (0 = выкл)
input double            InpDailyProfitTarget = 8.0;                       // Дневная цель по прибыли в % (0 = выкл)
input int               InpMaxConsecLosses   = 3;                         // Стоп-торговля после N убытков подряд за день (0 = выкл)

input group "=== 6. Защита AMarkets (Спред, Новости USD, Визуализация) ==="
input ulong             InpMagicNumber       = 888236;                    // Magic Number (Trullas Fibo 23.6)
input int               InpMaxSpreadPoints   = 3500;                      // Макс. спред в пунктах для BTCUSD (0 = выкл)
input bool              InpUseNewsFilter     = true;                      // Пауза во время важных новостей USD (Календарь MT5)
input int               InpNewsPauseBefore   = 15;                        // Пауза ДО важной новости USD (минут)
input int               InpNewsPauseAfter    = 10;                        // Пауза ПОСЛЕ важной новости USD (минут)
input bool              InpDrawFiboGrid      = true;                      // Рисовать авто-сетку Фибоначчи и панель на графике

// --- Структура активной сетки Фибоначчи ---
struct FiboSetup
{
   bool     isActive;          // Активна ли сейчас натянутая сетка
   int      direction;         // 1 = BUY (Сетка на падение, ждем возврат вверх за 23.6%), -1 = SELL (Сетка на рост, ждем возврат вниз за 23.6%)
   datetime time100;           // Время начала импульса (100% Фибо)
   double   price100;          // Цена начала импульса (100% Фибо)
   datetime time0;             // Время экстремума разворота (0% Фибо)
   double   price0;            // Цена экстремума разворота (0% Фибо — за него ставится SL)
   double   lvl236;            // Расчетная цена уровня 23.6% (Триггер входа)
   double   lvl382;            // Расчетная цена уровня 38.2% (TP1 + Безубыток)
   double   lvl500;            // Расчетная цена уровня 50.0% (Трейлинг)
   double   lvl618;            // Расчетная цена уровня 61.8% / 66% (TP2)
   bool     hasMACDDiv;        // Наличие классической дивергенции MACD
   bool     hasRSIConfirm;     // Подтверждение по RSI (14)
   bool     hasVolConfirm;     // Подтверждение по объему (Volume)
   bool     hasHTFConfirm;     // Совпадение с трендом старшего ТФ
   bool     tradeExecuted;     // Был ли уже выполнен вход по этой сетке
   string   signalReason;      // Описание сетапа для панели
};

// --- Глобальные переменные ---
int       macdHandle    = INVALID_HANDLE;
int       rsiHandle     = INVALID_HANDLE;
int       atrHandle     = INVALID_HANDLE;
int       htfEmaHandle  = INVALID_HANDLE;
datetime  lastBarTime   = 0;
FiboSetup currentFibo;

// Переменные сопровождения открытой позиции по уровням Фибоначчи
double    activePosPrice0  = 0;
double    activePosPrice100= 0;
double    activePosLvl236  = 0;
double    activePosLvl382  = 0;
double    activePosLvl500  = 0;
double    activePosLvl618  = 0;
int       activePosDir     = 0;

#define FIBO_OBJ_PREFIX "DTV_Fibo_"

//+------------------------------------------------------------------+
//| Инициализация советника                                          |
//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(50);
   trade.SetMarginMode();
   trade.SetTypeFillingBySymbol(_Symbol);

   ENUM_TIMEFRAMES tf = (InpWorkTF == PERIOD_CURRENT) ? _Period : InpWorkTF;

   macdHandle = iMACD(_Symbol, tf, InpMACD_Fast, InpMACD_Slow, InpMACD_Signal, PRICE_CLOSE);
   rsiHandle  = iRSI(_Symbol, tf, InpRSI_Period, PRICE_CLOSE);
   atrHandle  = iATR(_Symbol, tf, 14);

   if(macdHandle == INVALID_HANDLE || rsiHandle == INVALID_HANDLE || atrHandle == INVALID_HANDLE)
   {
      Print("Ошибка инициализации индикаторов MACD / RSI / ATR!");
      return(INIT_FAILED);
   }

   if(InpHTFMode != HTF_DISABLED)
   {
      htfEmaHandle = iMA(_Symbol, InpHTF, InpHTF_EMA, 0, MODE_EMA, PRICE_CLOSE);
      if(htfEmaHandle == INVALID_HANDLE)
      {
         Print("Ошибка инициализации EMA старшего таймфрейма!");
         return(INIT_FAILED);
      }
   }

   ZeroMemory(currentFibo);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Деинициализация                                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(macdHandle   != INVALID_HANDLE) IndicatorRelease(macdHandle);
   if(rsiHandle    != INVALID_HANDLE) IndicatorRelease(rsiHandle);
   if(atrHandle    != INVALID_HANDLE) IndicatorRelease(atrHandle);
   if(htfEmaHandle != INVALID_HANDLE) IndicatorRelease(htfEmaHandle);

   ObjectsDeleteAll(0, FIBO_OBJ_PREFIX);
   Comment("");
}

//+------------------------------------------------------------------+
//| Получение рабочего таймфрейма                                    |
//+------------------------------------------------------------------+
ENUM_TIMEFRAMES WorkTF()
{
   return (InpWorkTF == PERIOD_CURRENT) ? _Period : InpWorkTF;
}

//+------------------------------------------------------------------+
//| Определение тренда на старшем ТФ (H1 EMA)                        |
//+------------------------------------------------------------------+
int GetHTFTrend()
{
   if(InpHTFMode == HTF_DISABLED || htfEmaHandle == INVALID_HANDLE) return 0;

   double ema[];
   ArraySetAsSeries(ema, true);
   if(CopyBuffer(htfEmaHandle, 0, 1, 3, ema) < 3) return 0;

   double c1 = iClose(_Symbol, InpHTF, 1);
   if(c1 > ema[0] && ema[0] >= ema[2]) return 1;
   if(c1 < ema[0] && ema[0] <= ema[2]) return -1;
   return 0;
}

//+------------------------------------------------------------------+
//| Проверка экономических новостей USD в календаре MT5              |
//+------------------------------------------------------------------+
bool CheckNewsPause(string &outStatus)
{
   outStatus = "Спокойно";
   if(!InpUseNewsFilter)
   {
      outStatus = "Фильтр выкл.";
      return false;
   }
   if(MQLInfoInteger(MQL_TESTER))
   {
      outStatus = "Тестер (Календарь выкл.)";
      return false;
   }

   MqlCalendarValue values[];
   datetime now  = TimeTradeServer();
   datetime from = now - InpNewsPauseAfter * 60;
   datetime to   = now + InpNewsPauseBefore * 60;

   if(!CalendarValueHistory(values, from, to, NULL, "USD"))
      return false;

   for(int i = 0; i < ArraySize(values); i++)
   {
      MqlCalendarEvent ev;
      if(!CalendarEventById(values[i].event_id, ev)) continue;
      if(ev.importance != CALENDAR_IMPORTANCE_HIGH) continue;

      int diffMin = (int)((now - values[i].time) / 60);
      outStatus = StringFormat("ПАУЗА НОВОСТЕЙ: %s (%d мин)", ev.name, diffMin);
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Контроль дневного лимита убытков и серии стопов (Дисциплина Д.Т.)|
//+------------------------------------------------------------------+
bool CheckDailyRiskLimits(double &outDailyPct, int &outConsecLosses, string &outRiskStatus)
{
   outDailyPct     = 0.0;
   outConsecLosses = 0;
   outRiskStatus   = "В норме (Торговля разрешена)";

   datetime now = TimeCurrent();
   MqlDateTime dt;
   TimeToStruct(now, dt);
   dt.hour = 0; dt.min = 0; dt.sec = 0;
   datetime startOfDay = StructToTime(dt);

   if(!HistorySelect(startOfDay, now)) return true;

   double realizedPnL = 0.0;
   int totalDeals = HistoryDealsTotal();

   for(int i = 0; i < totalDeals; i++)
   {
      ulong dealTicket = HistoryDealGetTicket(i);
      if(dealTicket == 0) continue;
      if(HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != (long)InpMagicNumber) continue;
      if(HistoryDealGetString(dealTicket, DEAL_SYMBOL) != _Symbol) continue;

      long entryType = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
      if(entryType == DEAL_ENTRY_OUT || entryType == DEAL_ENTRY_INOUT)
      {
         double pnl = HistoryDealGetDouble(dealTicket, DEAL_PROFIT)
                    + HistoryDealGetDouble(dealTicket, DEAL_SWAP)
                    + HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
         realizedPnL += pnl;

         if(pnl < -0.01)
            outConsecLosses++;
         else if(pnl > 0.01)
            outConsecLosses = 0;
      }
   }

   // Учитываем плавающий результат открытой позиции
   double floatingPnL = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == (long)InpMagicNumber)
      {
         floatingPnL += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
      }
   }

   double currentBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   double startBalance   = currentBalance - realizedPnL;
   if(startBalance <= 0) startBalance = currentBalance;

   outDailyPct = ((realizedPnL + floatingPnL) / startBalance) * 100.0;

   if(InpMaxDailyLossPct > 0.0 && outDailyPct <= -InpMaxDailyLossPct)
   {
      outRiskStatus = StringFormat("СТОП НА ДЕНЬ: Достигнут лимит убытка (%.2f%% <= -%.2f%%)", outDailyPct, InpMaxDailyLossPct);
      return false;
   }

   if(InpDailyProfitTarget > 0.0 && outDailyPct >= InpDailyProfitTarget)
   {
      outRiskStatus = StringFormat("ЦЕЛЬ ДНЯ ВЫПОЛНЕНА: Прибыль +%.2f%% (Лимит +%.2f%%)", outDailyPct, InpDailyProfitTarget);
      return false;
   }

   if(InpMaxConsecLosses > 0 && outConsecLosses >= InpMaxConsecLosses)
   {
      outRiskStatus = StringFormat("СТОП НА ДЕНЬ: Серия из %d убыточных сделок подряд", outConsecLosses);
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
//| Проверка фрактального пика / впадины на рабочем ТФ               |
//+------------------------------------------------------------------+
bool IsSwingHigh(ENUM_TIMEFRAMES tf, int barIdx, int strength)
{
   double h = iHigh(_Symbol, tf, barIdx);
   for(int j = 1; j <= strength; j++)
   {
      if(barIdx - j < 1) return false;
      if(iHigh(_Symbol, tf, barIdx - j) > h || iHigh(_Symbol, tf, barIdx + j) >= h)
         return false;
   }
   return true;
}

bool IsSwingLow(ENUM_TIMEFRAMES tf, int barIdx, int strength)
{
   double l = iLow(_Symbol, tf, barIdx);
   for(int j = 1; j <= strength; j++)
   {
      if(barIdx - j < 1) return false;
      if(iLow(_Symbol, tf, barIdx - j) < l || iLow(_Symbol, tf, barIdx + j) <= l)
         return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| Пересчет ценовых уровней внутри структуры FiboSetup              |
//+------------------------------------------------------------------+
void RecalculateFiboLevels(FiboSetup &fibo)
{
   double range = MathAbs(fibo.price100 - fibo.price0);
   if(fibo.direction == 1) // BUY: 0% внизу (Swing Low), 100% вверху (Swing High)
   {
      fibo.lvl236 = NormalizeDouble(fibo.price0 + range * InpFiboEntryLevel, _Digits);
      fibo.lvl382 = NormalizeDouble(fibo.price0 + range * InpFiboTP1Level,   _Digits);
      fibo.lvl500 = NormalizeDouble(fibo.price0 + range * InpFiboTrailLevel, _Digits);
      fibo.lvl618 = NormalizeDouble(fibo.price0 + range * InpFiboTP2Level,   _Digits);
   }
   else if(fibo.direction == -1) // SELL: 0% вверху (Swing High), 100% внизу (Swing Low)
   {
      fibo.lvl236 = NormalizeDouble(fibo.price0 - range * InpFiboEntryLevel, _Digits);
      fibo.lvl382 = NormalizeDouble(fibo.price0 - range * InpFiboTP1Level,   _Digits);
      fibo.lvl500 = NormalizeDouble(fibo.price0 - range * InpFiboTrailLevel, _Digits);
      fibo.lvl618 = NormalizeDouble(fibo.price0 - range * InpFiboTP2Level,   _Digits);
   }
}

//+------------------------------------------------------------------+
//| Отрисовка автоматической сетки Фибоначчи на графике              |
//+------------------------------------------------------------------+
void DrawAutoFiboGrid(const FiboSetup &fibo)
{
   if(!InpDrawFiboGrid) return;

   string objName = FIBO_OBJ_PREFIX + "Grid";
   ObjectDelete(0, objName);

   if(!fibo.isActive) return;

   // В MT5 объект OBJ_FIBO строит уровень 0.0 во второй точке (time2, price2) и 1.0 (100%) в первой точке (time1, price1)
   if(!ObjectCreate(0, objName, OBJ_FIBO, 0, fibo.time100, fibo.price100, fibo.time0, fibo.price0))
      return;

   color gridColor = (fibo.direction == 1) ? clrDodgerBlue : clrTomato;
   ObjectSetInteger(0, objName, OBJPROP_COLOR, gridColor);
   ObjectSetInteger(0, objName, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, objName, OBJPROP_RAY_RIGHT, true);
   ObjectSetInteger(0, objName, OBJPROP_BACK, false);

   double levels[6] = {0.0, InpFiboEntryLevel, InpFiboTP1Level, InpFiboTrailLevel, InpFiboTP2Level, 1.0};
   string labels[6];
   labels[0] = "0.0% [Экстремум / SL зона] (%$)";
   labels[1] = StringFormat("%.1f%% [ВХОД ТРУЛЬЯСА] (%%$)", InpFiboEntryLevel * 100.0);
   labels[2] = StringFormat("%.1f%% [TP1 СЕЙФ + БЕЗУБЫТОК] (%%$)", InpFiboTP1Level * 100.0);
   labels[3] = StringFormat("%.1f%% [ТРЕЙЛИНГ СТОПА] (%%$)", InpFiboTrailLevel * 100.0);
   labels[4] = StringFormat("%.1f%% [TP2 ГЛАВНАЯ ЦЕЛЬ] (%%$)", InpFiboTP2Level * 100.0);
   labels[5] = "100.0% [Начало импульса] (%$)";

   ObjectSetInteger(0, objName, OBJPROP_LEVELS, 6);
   for(int i = 0; i < 6; i++)
   {
      ObjectSetDouble(0, objName, OBJPROP_LEVELVALUE, i, levels[i]);
      ObjectSetString(0, objName, OBJPROP_LEVELTEXT,  i, labels[i]);
      ObjectSetInteger(0, objName, OBJPROP_LEVELCOLOR, i, gridColor);
      ObjectSetInteger(0, objName, OBJPROP_LEVELSTYLE, i, (i == 1 || i == 2 || i == 4) ? STYLE_SOLID : STYLE_DOT);
      ObjectSetInteger(0, objName, OBJPROP_LEVELWIDTH, i, (i == 1 || i == 2 || i == 4) ? 2 : 1);
   }

   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| Поиск свингов, дивергенции MACD/RSI/Volume и построение сетки    |
//+------------------------------------------------------------------+
void ScanForTrullasFiboSetup(double atr, int htfTrend)
{
   ENUM_TIMEFRAMES tf = WorkTF();
   int copyCount = InpLookbackBars + 10;

   double macdMain[], macdSig[], rsiBuf[];
   long   volBuf[];
   ArraySetAsSeries(macdMain, true);
   ArraySetAsSeries(macdSig,  true);
   ArraySetAsSeries(rsiBuf,   true);
   ArraySetAsSeries(volBuf,   true);

   if(CopyBuffer(macdHandle, 0, 0, copyCount, macdMain) < copyCount) return;
   if(CopyBuffer(macdHandle, 1, 0, copyCount, macdSig)  < copyCount) return;
   if(CopyBuffer(rsiHandle,  0, 0, copyCount, rsiBuf)   < copyCount) return;
   if(CopyTickVolume(_Symbol, tf, 0, copyCount, volBuf) < copyCount) return;

   // Средний тиковый объем за InpVolMAPeriod баров
   double avgVol = 0;
   for(int v = 1; v <= InpVolMAPeriod; v++) avgVol += (double)volBuf[v];
   avgVol /= (double)InpVolMAPeriod;

   // Собираем последние 2 Swing High и 2 Swing Low
   int highIdx[2] = {-1, -1};
   int lowIdx[2]  = {-1, -1};
   int hFound = 0, lFound = 0;

   for(int i = InpPivotStrength + 1; i < InpLookbackBars - InpPivotStrength; i++)
   {
      if(hFound < 2 && IsSwingHigh(tf, i, InpPivotStrength))
      {
         highIdx[hFound] = i;
         hFound++;
      }
      if(lFound < 2 && IsSwingLow(tf, i, InpPivotStrength))
      {
         lowIdx[lFound] = i;
         lFound++;
      }
      if(hFound >= 2 && lFound >= 2) break;
   }

   if(hFound < 1 || lFound < 1) return;

   // Определяем, какой экстремум сформировался последним (завершил последний импульс)
   int lastLowBar  = lowIdx[0];
   int lastHighBar = highIdx[0];

   // Также проверяем совсем свежий локальный экстремум на барах 2..InpPivotStrength, если цена уже начала откат
   for(int r = 2; r <= InpPivotStrength; r++)
   {
      if(iLow(_Symbol, tf, r) < iLow(_Symbol, tf, lastLowBar) && iClose(_Symbol, tf, 1) > iLow(_Symbol, tf, r))
         lastLowBar = r;
      if(iHigh(_Symbol, tf, r) > iHigh(_Symbol, tf, lastHighBar) && iClose(_Symbol, tf, 1) < iHigh(_Symbol, tf, r))
         lastHighBar = r;
   }

   // --- ВАРИАНТ 1: Последним был минимум (Нисходящий импульс от High -> к Low). Ищем сетап BUY ---
   if(lastLowBar < lastHighBar)
   {
      if(InpHTFMode == HTF_STRICT_FILTER && htfTrend < 0) return;

      double price100 = iHigh(_Symbol, tf, lastHighBar);
      double price0   = iLow(_Symbol, tf, lastLowBar);
      double impulse  = price100 - price0;

      if(impulse < atr * InpMinImpulseATR) return;

      // Проверяем, не ушла ли цена уже ниже price0 или слишком далеко вверх (выше 38.2%)
      double c1 = iClose(_Symbol, tf, 1);
      double lvl382Test = price0 + impulse * InpFiboTP1Level;
      if(c1 < price0 || c1 >= lvl382Test) return;

      // 1. Проверка дивергенции MACD (12, 26, 9) между текущим Low и предыдущим Swing Low
      bool hasMACDDiv = false;
      int prevLowBar  = (lastLowBar == lowIdx[0]) ? lowIdx[1] : lowIdx[0];
      if(prevLowBar > lastLowBar)
      {
         double lowCurr  = iLow(_Symbol, tf, lastLowBar);
         double lowPrev  = iLow(_Symbol, tf, prevLowBar);
         double macdCurr = macdMain[lastLowBar];
         double macdPrev = macdMain[prevLowBar];

         // Бычья дивергенция: Цена ниже (или двойное дно), а MACD выше
         if(lowCurr <= lowPrev * 1.0015 && macdCurr > macdPrev)
            hasMACDDiv = true;
      }

      // Разворот моментума MACD вверх на последних барах
      bool hasMACDMomentum = (macdMain[1] > macdMain[2] && (macdMain[1] > macdSig[1] || (macdMain[1] - macdSig[1]) > (macdMain[2] - macdSig[2])));

      if(InpSignalMode == SIGNAL_DIVERGENCE_ONLY && !hasMACDDiv) return;
      if(InpSignalMode == SIGNAL_DIVERGENCE_OR_IMPULSE && !hasMACDDiv && !hasMACDMomentum) return;

      // 2. Подтверждение RSI (14): выход из перепроданности или дивергенция RSI
      bool hasRSIConfirm = (rsiBuf[lastLowBar] <= InpRSI_Oversold || (prevLowBar > lastLowBar && rsiBuf[lastLowBar] > rsiBuf[prevLowBar])) && (rsiBuf[1] > rsiBuf[lastLowBar]);

      // 3. Подтверждение Объема (Volume): повышенный объем на развороте/пробое ИЛИ затухание объема на втором дне
      bool hasVolConfirm = ((double)volBuf[1] > avgVol * 1.05) || (prevLowBar > lastLowBar && volBuf[lastLowBar] < volBuf[prevLowBar]);

      // Если это новый экстремум — обновляем сетку Фибоначчи
      datetime t0   = iTime(_Symbol, tf, lastLowBar);
      datetime t100 = iTime(_Symbol, tf, lastHighBar);

      if(!currentFibo.isActive || currentFibo.direction != 1 || currentFibo.time0 != t0 || currentFibo.time100 != t100)
      {
         currentFibo.isActive       = true;
         currentFibo.direction      = 1;
         currentFibo.time100        = t100;
         currentFibo.price100       = price100;
         currentFibo.time0          = t0;
         currentFibo.price0         = price0;
         currentFibo.hasMACDDiv     = hasMACDDiv;
         currentFibo.hasRSIConfirm  = hasRSIConfirm;
         currentFibo.hasVolConfirm  = hasVolConfirm;
         currentFibo.hasHTFConfirm  = (htfTrend == 1);
         currentFibo.tradeExecuted  = false;
         currentFibo.signalReason   = hasMACDDiv ? "Бычья дивергенция MACD" : "Импульс + разворот MACD вверх";
         RecalculateFiboLevels(currentFibo);
         DrawAutoFiboGrid(currentFibo);
      }
      else
      {
         // Обновляем динамические флаги подтверждения
         currentFibo.hasRSIConfirm = currentFibo.hasRSIConfirm || hasRSIConfirm;
         currentFibo.hasVolConfirm = currentFibo.hasVolConfirm || hasVolConfirm;
         currentFibo.hasHTFConfirm = (htfTrend == 1);
      }
   }
   // --- ВАРИАНТ 2: Последним был максимум (Восходящий импульс от Low -> к High). Ищем сетап SELL ---
   else if(lastHighBar < lastLowBar)
   {
      if(InpHTFMode == HTF_STRICT_FILTER && htfTrend > 0) return;

      double price100 = iLow(_Symbol, tf, lastLowBar);
      double price0   = iHigh(_Symbol, tf, lastHighBar);
      double impulse  = price0 - price100;

      if(impulse < atr * InpMinImpulseATR) return;

      double c1 = iClose(_Symbol, tf, 1);
      double lvl382Test = price0 - impulse * InpFiboTP1Level;
      if(c1 > price0 || c1 <= lvl382Test) return;

      // 1. Проверка медвежьей дивергенции MACD (12, 26, 9)
      bool hasMACDDiv = false;
      int prevHighBar = (lastHighBar == highIdx[0]) ? highIdx[1] : highIdx[0];
      if(prevHighBar > lastHighBar)
      {
         double highCurr = iHigh(_Symbol, tf, lastHighBar);
         double highPrev = iHigh(_Symbol, tf, prevHighBar);
         double macdCurr = macdMain[lastHighBar];
         double macdPrev = macdMain[prevHighBar];

         // Медвежья дивергенция: Цена выше (или двойная вершина), а MACD ниже
         if(highCurr >= highPrev * 0.9985 && macdCurr < macdPrev)
            hasMACDDiv = true;
      }

      bool hasMACDMomentum = (macdMain[1] < macdMain[2] && (macdMain[1] < macdSig[1] || (macdMain[1] - macdSig[1]) < (macdMain[2] - macdSig[2])));

      if(InpSignalMode == SIGNAL_DIVERGENCE_ONLY && !hasMACDDiv) return;
      if(InpSignalMode == SIGNAL_DIVERGENCE_OR_IMPULSE && !hasMACDDiv && !hasMACDMomentum) return;

      // 2. Подтверждение RSI (14): выход из перекупленности или дивергенция RSI
      bool hasRSIConfirm = (rsiBuf[lastHighBar] >= InpRSI_Overbought || (prevHighBar > lastHighBar && rsiBuf[lastHighBar] < rsiBuf[prevHighBar])) && (rsiBuf[1] < rsiBuf[lastHighBar]);

      // 3. Подтверждение Объема (Volume)
      bool hasVolConfirm = ((double)volBuf[1] > avgVol * 1.05) || (prevHighBar > lastHighBar && volBuf[lastHighBar] < volBuf[prevHighBar]);

      datetime t0   = iTime(_Symbol, tf, lastHighBar);
      datetime t100 = iTime(_Symbol, tf, lastLowBar);

      if(!currentFibo.isActive || currentFibo.direction != -1 || currentFibo.time0 != t0 || currentFibo.time100 != t100)
      {
         currentFibo.isActive       = true;
         currentFibo.direction      = -1;
         currentFibo.time100        = t100;
         currentFibo.price100       = price100;
         currentFibo.time0          = t0;
         currentFibo.price0         = price0;
         currentFibo.hasMACDDiv     = hasMACDDiv;
         currentFibo.hasRSIConfirm  = hasRSIConfirm;
         currentFibo.hasVolConfirm  = hasVolConfirm;
         currentFibo.hasHTFConfirm  = (htfTrend == -1);
         currentFibo.tradeExecuted  = false;
         currentFibo.signalReason   = hasMACDDiv ? "Медвежья дивергенция MACD" : "Импульс + разворот MACD вниз";
         RecalculateFiboLevels(currentFibo);
         DrawAutoFiboGrid(currentFibo);
      }
      else
      {
         currentFibo.hasRSIConfirm = currentFibo.hasRSIConfirm || hasRSIConfirm;
         currentFibo.hasVolConfirm = currentFibo.hasVolConfirm || hasVolConfirm;
         currentFibo.hasHTFConfirm = (htfTrend == -1);
      }
   }
}

//+------------------------------------------------------------------+
//| Расчет динамического процента риска по методу конфлюэнса Трульяса|
//+------------------------------------------------------------------+
double GetEffectiveRiskPercent(const FiboSetup &fibo)
{
   double riskPct = InpBaseRiskPercent;
   if(InpUseConfluenceRisk && fibo.isActive)
   {
      if(fibo.hasMACDDiv)    riskPct += InpBonusRiskStep * 0.5;
      if(fibo.hasRSIConfirm) riskPct += InpBonusRiskStep;
      if(fibo.hasVolConfirm) riskPct += InpBonusRiskStep;
      if(InpHTFMode == HTF_CONFLUENCE_BONUS && fibo.hasHTFConfirm)
         riskPct += InpBonusRiskStep * 0.5;
   }
   if(riskPct > InpMaxRiskPercent) riskPct = InpMaxRiskPercent;
   return riskPct;
}

//+------------------------------------------------------------------+
//| Расчет лота с учетом дистанции до SL за уровнем 0.0% Фибоначчи   |
//+------------------------------------------------------------------+
double CalculateTrullasLot(ENUM_ORDER_TYPE orderType, double entryPrice, double slPrice, double riskPct)
{
   double slDist = MathAbs(entryPrice - slPrice);
   if(!InpUseAutoLot || slDist <= 0) return InpFixedLot;

   double balance   = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskMoney = balance * (riskPct / 100.0);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);

   if(tickValue <= 0 || tickSize <= 0) return InpFixedLot;

   double slTicks = slDist / tickSize;
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

//+------------------------------------------------------------------+
//| Проверка наличия открытой позиции бота                           |
//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == (long)InpMagicNumber)
         return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Сопровождение открытых сделок по уровням Фибоначчи (38.2% и 50%) |
//+------------------------------------------------------------------+
void ManageFiboPositions(double atr)
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

      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != (long)InpMagicNumber)
         continue;

      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double currentSL = PositionGetDouble(POSITION_SL);
      double currentTP = PositionGetDouble(POSITION_TP);
      double volume    = PositionGetDouble(POSITION_VOLUME);
      long   posType   = PositionGetInteger(POSITION_TYPE);

      // Если советник перезапускался, восстанавливаем целевые ступени от цены открытия и TP
      double target382 = activePosLvl382;
      double target500 = activePosLvl500;
      double target236 = activePosLvl236;

      if(posType == POSITION_TYPE_BUY)
      {
         double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         if(target382 <= openPrice && currentTP > openPrice)
         {
            double distToTP = currentTP - openPrice;
            target236 = openPrice;
            target382 = NormalizeDouble(openPrice + distToTP * 0.38, _Digits);
            target500 = NormalizeDouble(openPrice + distToTP * 0.68, _Digits);
         }

         double beSL       = NormalizeDouble(openPrice + atr * InpBE_OffsetATR, _Digits);
         bool   isAlreadyBE= (currentSL >= openPrice);
         double closeVol   = MathFloor((volume * (InpTP1_ClosePercent / 100.0)) / stepLot) * stepLot;
         closeVol          = NormalizeDouble(closeVol, lotDigits);
         bool   canPartial = (InpUsePartialClose && closeVol >= minLot && (volume - closeVol) >= minLot);

         // 1. Достижение Первой Цели Трульяса — Уровень 38.2% Фибоначчи (Сейф + Безубыток)
         if(target382 > openPrice && bid >= target382 && !isAlreadyBE)
         {
            if(canPartial)
            {
               trade.PositionClosePartial(ticket, closeVol);
               ulong newTicket = PositionGetTicket(i);
               if(newTicket > 0 && InpUseBreakeven && (bid - beSL) > stopLevelDist)
                  trade.PositionModify(newTicket, beSL, currentTP);
               continue;
            }
            else if(InpUseBreakeven && (bid - beSL) > stopLevelDist)
            {
               trade.PositionModify(ticket, beSL, currentTP);
            }
         }

         // 2. Достижение уровня 50.0% Фибоначчи — подтягиваем SL на уровень 38.2% (или 23.6%)
         if(target500 > openPrice && bid >= target500)
         {
            double trailSL = NormalizeDouble((target236 + target382) * 0.5, _Digits);
            if(trailSL > currentSL && trailSL > openPrice && (bid - trailSL) > stopLevelDist)
               trade.PositionModify(ticket, trailSL, currentTP);
         }
      }
      else if(posType == POSITION_TYPE_SELL)
      {
         double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         if((target382 <= 0 || target382 >= openPrice) && currentTP > 0 && currentTP < openPrice)
         {
            double distToTP = openPrice - currentTP;
            target236 = openPrice;
            target382 = NormalizeDouble(openPrice - distToTP * 0.38, _Digits);
            target500 = NormalizeDouble(openPrice - distToTP * 0.68, _Digits);
         }

         double beSL       = NormalizeDouble(openPrice - atr * InpBE_OffsetATR, _Digits);
         bool   isAlreadyBE= (currentSL > 0 && currentSL <= openPrice);
         double closeVol   = MathFloor((volume * (InpTP1_ClosePercent / 100.0)) / stepLot) * stepLot;
         closeVol          = NormalizeDouble(closeVol, lotDigits);
         bool   canPartial = (InpUsePartialClose && closeVol >= minLot && (volume - closeVol) >= minLot);

         // 1. Достижение уровня 38.2% Фибоначчи (Сейф + Безубыток)
         if(target382 > 0 && target382 < openPrice && ask <= target382 && !isAlreadyBE)
         {
            if(canPartial)
            {
               trade.PositionClosePartial(ticket, closeVol);
               ulong newTicket = PositionGetTicket(i);
               if(newTicket > 0 && InpUseBreakeven && (beSL - ask) > stopLevelDist)
                  trade.PositionModify(newTicket, beSL, currentTP);
               continue;
            }
            else if(InpUseBreakeven && (beSL - ask) > stopLevelDist)
            {
               trade.PositionModify(ticket, beSL, currentTP);
            }
         }

         // 2. Достижение уровня 50.0% Фибоначчи — подтягиваем SL в плюс
         if(target500 > 0 && target500 < openPrice && ask <= target500)
         {
            double trailSL = NormalizeDouble((target236 + target382) * 0.5, _Digits);
            if((currentSL == 0 || trailSL < currentSL) && trailSL < openPrice && (trailSL - ask) > stopLevelDist)
               trade.PositionModify(ticket, trailSL, currentTP);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Проверка пробоя уровня 23.6% Фибоначчи и открытие сделки         |
//+------------------------------------------------------------------+
void CheckFiboEntryTrigger(double atr)
{
   if(!currentFibo.isActive || currentFibo.tradeExecuted) return;

   ENUM_TIMEFRAMES tf = WorkTF();
   double ask   = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid   = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double c1    = iClose(_Symbol, tf, 1);
   double o1    = iOpen(_Symbol, tf, 1);
   double low0  = iLow(_Symbol, tf, 0);
   double high0 = iHigh(_Symbol, tf, 0);

   // 1. Инвалидация сетки, если цена обновила экстремум 0% (пробила точку 0% дальше) или уже улетела за 38.2% без входа
   if(currentFibo.direction == 1)
   {
      if(bid < currentFibo.price0 - atr * 0.10 || bid >= currentFibo.lvl382)
      {
         currentFibo.isActive = false;
         DrawAutoFiboGrid(currentFibo);
         return;
      }

      // Проверяем условие пробоя 23.6% Фибоначчи вверх
      bool triggered = false;
      if(InpRequireCandleClose)
         triggered = (c1 > currentFibo.lvl236 && c1 > o1 && bid >= currentFibo.lvl236 && bid < currentFibo.lvl382);
      else
         triggered = (bid >= currentFibo.lvl236 && low0 <= currentFibo.lvl236 && bid < currentFibo.lvl382);

      if(triggered)
      {
         double slPrice = NormalizeDouble(currentFibo.price0 - atr * InpSL_BufferATR, _Digits);
         double tpPrice = currentFibo.lvl618;

         // Защита от слишком узкого или слишком далекого SL
         double slDist = ask - slPrice;
         if(slDist < atr * 0.5) slPrice = NormalizeDouble(ask - atr * 0.6, _Digits);
         if(slDist > atr * 4.5) slPrice = NormalizeDouble(ask - atr * 3.5, _Digits);
         if(tpPrice <= ask + atr * 0.4) tpPrice = NormalizeDouble(ask + atr * 2.0, _Digits);

         double effRisk = GetEffectiveRiskPercent(currentFibo);
         double lot     = CalculateTrullasLot(ORDER_TYPE_BUY, ask, slPrice, effRisk);

         string comment = StringFormat("Trullas BUY Fibo23.6 (R:%.1f%%)", effRisk);
         if(trade.Buy(lot, _Symbol, ask, slPrice, tpPrice, comment))
         {
            currentFibo.tradeExecuted = true;
            activePosPrice0  = currentFibo.price0;
            activePosPrice100= currentFibo.price100;
            activePosLvl236  = currentFibo.lvl236;
            activePosLvl382  = currentFibo.lvl382;
            activePosLvl500  = currentFibo.lvl500;
            activePosLvl618  = currentFibo.lvl618;
            activePosDir     = 1;
         }
      }
   }
   else if(currentFibo.direction == -1)
   {
      if(ask > currentFibo.price0 + atr * 0.10 || ask <= currentFibo.lvl382)
      {
         currentFibo.isActive = false;
         DrawAutoFiboGrid(currentFibo);
         return;
      }

      // Проверяем условие пробоя 23.6% Фибоначчи вниз
      bool triggered = false;
      if(InpRequireCandleClose)
         triggered = (c1 < currentFibo.lvl236 && c1 < o1 && ask <= currentFibo.lvl236 && ask > currentFibo.lvl382);
      else
         triggered = (ask <= currentFibo.lvl236 && high0 >= currentFibo.lvl236 && ask > currentFibo.lvl382);

      if(triggered)
      {
         double slPrice = NormalizeDouble(currentFibo.price0 + atr * InpSL_BufferATR, _Digits);
         double tpPrice = currentFibo.lvl618;

         double slDist = slPrice - bid;
         if(slDist < atr * 0.5) slPrice = NormalizeDouble(bid + atr * 0.6, _Digits);
         if(slDist > atr * 4.5) slPrice = NormalizeDouble(bid + atr * 3.5, _Digits);
         if(tpPrice >= bid - atr * 0.4) tpPrice = NormalizeDouble(bid - atr * 2.0, _Digits);

         double effRisk = GetEffectiveRiskPercent(currentFibo);
         double lot     = CalculateTrullasLot(ORDER_TYPE_SELL, bid, slPrice, effRisk);

         string comment = StringFormat("Trullas SELL Fibo23.6 (R:%.1f%%)", effRisk);
         if(trade.Sell(lot, _Symbol, bid, slPrice, tpPrice, comment))
         {
            currentFibo.tradeExecuted = true;
            activePosPrice0  = currentFibo.price0;
            activePosPrice100= currentFibo.price100;
            activePosLvl236  = currentFibo.lvl236;
            activePosLvl382  = currentFibo.lvl382;
            activePosLvl500  = currentFibo.lvl500;
            activePosLvl618  = currentFibo.lvl618;
            activePosDir     = -1;
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Вывод информационной панели Давида Трульяса на график            |
//+------------------------------------------------------------------+
void UpdateDashboard(double atr, int htfTrend, double dailyPct, int consecLosses, string riskStatus, string newsStatus)
{
   if(!InpDrawFiboGrid) return;

   ENUM_TIMEFRAMES tf = WorkTF();
   long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   string htfText = (htfTrend == 1) ? "БЫЧИЙ (ВВЕРХ)" : ((htfTrend == -1) ? "МЕДВЕЖИЙ (ВНИЗ)" : "НЕЙТРАЛЬНО");

   string fiboStatus = "Ожидание нового импульса и дивергенции MACD...";
   if(currentFibo.isActive)
   {
      string dirStr = (currentFibo.direction == 1) ? "BUY (Сетка вверх)" : "SELL (Сетка вниз)";
      string confStr = StringFormat("MACD:%s | RSI:%s | VOL:%s | HTF:%s",
                       currentFibo.hasMACDDiv ? "ДА" : "ИМП",
                       currentFibo.hasRSIConfirm ? "ДА" : "НЕТ",
                       currentFibo.hasVolConfirm ? "ДА" : "НЕТ",
                       currentFibo.hasHTFConfirm ? "ДА" : "НЕТ");
      fiboStatus = StringFormat("%s [%s]\n"
                                "   -> Конфлюэнс: %s (Риск сделки: %.2f%%)\n"
                                "   -> 0.0%% (Экстремум/SL): %.2f | 23.6%% (ВХОД): %.2f\n"
                                "   -> 38.2%% (TP1 Сейф+БУ): %.2f | 61.8%% (TP2 Цель): %.2f",
                                dirStr, currentFibo.signalReason, confStr, GetEffectiveRiskPercent(currentFibo),
                                currentFibo.price0, currentFibo.lvl236, currentFibo.lvl382, currentFibo.lvl618);
   }

   Comment(StringFormat(
      "=== DAVID TRULLAS VILA BOT (HLIT: MACD + RSI + VOL + AUTO FIBO) ===\n"
      "Счет: AMarkets | Актив: %s | Рабочий ТФ: %s | Старший ТФ (%s): %s\n"
      "ATR(14): %.2f | Текущий спред: %d пт. (Макс: %d) | Новости USD: %s\n"
      "Дневной P&L: %.2f%% (Лимит: -%.1f%% / Цель: +%.1f%%) | Стопов подряд: %d | Статус: %s\n"
      "-------------------------------------------------------------------\n"
      "АВТО-СЕТКА ФИБОНАЧЧИ: %s",
      _Symbol, EnumToString(tf), EnumToString(InpHTF), htfText,
      atr, spread, InpMaxSpreadPoints, newsStatus,
      dailyPct, InpMaxDailyLossPct, InpDailyProfitTarget, consecLosses, riskStatus,
      fiboStatus));
}

//+------------------------------------------------------------------+
//| Основной цикл OnTick                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   double atrBuf[];
   if(CopyBuffer(atrHandle, 0, 1, 1, atrBuf) <= 0) return;
   double atr = atrBuf[0];

   // 1. Постоянное сопровождение открытых позиций по ступеням Фибоначчи (38.2% Сейф+БУ и 50% Трейлинг)
   ManageFiboPositions(atr);

   // 2. Проверка контекста, новостей и дневных лимитов риска Давида Трульяса
   int    htfTrend     = GetHTFTrend();
   double dailyPct     = 0.0;
   int    consecLosses = 0;
   string riskStatus   = "";
   bool   allowByRisk  = CheckDailyRiskLimits(dailyPct, consecLosses, riskStatus);

   string newsStatus   = "";
   bool   newsPaused   = CheckNewsPause(newsStatus);

   // 3. Поиск новых свингов и построение авто-сетки Фибоначчи при открытии новой свечи рабочего ТФ
   ENUM_TIMEFRAMES tf = WorkTF();
   datetime currentBar = iTime(_Symbol, tf, 0);
   if(currentBar != lastBarTime)
   {
      if(!HasOpenPosition())
         ScanForTrullasFiboSetup(atr, htfTrend);
      lastBarTime = currentBar;
   }

   // 4. Обновление информационной панели на графике
   UpdateDashboard(atr, htfTrend, dailyPct, consecLosses, riskStatus, newsStatus);

   // 5. Проверка условий для входа на пробое уровня 23.6% Фибоначчи
   if(!allowByRisk || newsPaused) return;
   if(HasOpenPosition()) return;

   long currentSpread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   if(InpMaxSpreadPoints > 0 && currentSpread > InpMaxSpreadPoints) return;

   CheckFiboEntryTrigger(atr);
}
//+------------------------------------------------------------------+
