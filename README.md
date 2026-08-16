# scalping-backtest

## 목표 (이게 전부다)

각 구간마다 **독립적으로** 시작 자본 **$100**을 넣고, 그 구간 안에서 **최소 10,000배 ($1,000,000)** 에 도달해야 한다.

- **한 구간만** 수천~수만 배 → **실패**
- **모든** 롤링 1~2개월 구간이 각각 10,000배 → **성공**
- **계좌 청산(합산 equity 전멸/wipe) = 0창** ← 목표. 격리 **슬롯** 청산은 허용·참고 지표일 뿐 (슬롯 liq=0이 목표가 아님)
- **MDD는 목표가 아님** (기록만). 창 안에서 드로우다운이 깊어도, 10,000x를 찍고 계좌가 전멸하지 않으면 통과
- 평가 단위: **PORT5** 합산 계좌 (BTC/ETH/BNB/SOL/XRP, 심볼별 전략, 기본 20% 배분·마지막 슬롯은 잔여 현금 전액, 격리 마진), 각 심볼 **1m**, 수수료/슬리피지 **켠 상태** (끄면 안 됨)
- 러너: `python -u eval_portfolio_windows.py` (BTC 단독 대조는 `eval_windows.py` 유지)

예시로 아래처럼 이어지는 **모든** 구간이 각각 $100 → 10,000배여야 한다  
(달력 월 정렬 예시; 실제 러너는 ~60일 창 / 30일 스텝으로 동일 기간을 덮는다):

| # | 구간 |
|---|------|
| 1 | 2021-08 ~ 2021-10 |
| 2 | 2021-09 ~ 2021-11 |
| 3 | 2021-10 ~ 2021-12 |
| … | … (한 달씩 밀며 계속) |
| … | 2026-05 ~ 2026-07 |
| … | 2026-06 ~ 2026-08 |

**Done 조건:** 모든 창에서  
1) `hit_10000x == true`  
2) `account_liq == false` (계좌 청산 0)  

MDD는 Done 조건이 아니다.  

## 성공/실패 지표 (우선순위)

1. **`hits_10000x` / 전체 창** ← 1순위 (올리기)
2. **중앙값(median) peak 배수** ← 2순위 (전 구간이 움직이는지)
3. **최악 창(min) peak 배수** ← 3순위 (구멍 구간)
4. **`n_account_liq` (계좌 청산/wipe 창 수) → 0** ← 슬롯 `liq`와 구분
5. max peak / 슬롯 `liq` / `mdd` ← **보조 지표** (슬롯 liq↑·MDD 악화만으로 Revert 금지)

> 과거 실수: 2022-01 폭락 창 max만 ~3100배로 키움.  
> 나머지 대다수 창은 peak≈1 → **목표 관점에서 실패 상태**.

## 연구 루프 (STRICT)

1세트 = 아래를 **빠짐없이**:

1. **현재 코드**로 창 평가 1회
2. **진단** (hits, median/min/max peak, **계좌 청산(wipe)**, 거래수, 슬롯 청산(참고), mdd(참고), 어떤 창이 죽는지, 실패모드, 다음 가설)
3. **소스 코드 1개** 응집 수정 (전략/엔진). JSON 파라미터 배치 스윕은 세트 아님
4. 수정 후 평가 1회
5. **Keep / Revert**
   - Keep: `hits_10000x` 증가, 또는 (히트 동일해도) **median/min peak**가 10,000배에 의미 있게 접근하고 **계좌 wipe가 늘지 않을** 때
   - Revert: 히트·median/min이 안 나아지거나, max만 오르고 전 구간 지표가 악화될 때, **계좌 청산 창 수↑**
   - **슬롯 liq↑·MDD 악화만으로 Revert 금지**. **max peak만 올리는 수정은 Keep 아님**

## 평가 단위 (PORT5)

BTC 단독 올인 복리는 폐기했다. 기본 평가는 **5심볼 분산 포트폴리오**:

| 항목 | 값 |
|------|----|
| 심볼 | BTCUSDT / ETHUSDT / BNBUSDT / SOLUSDT / XRPUSDT |
| 전략 | 심볼별 **1m 단타 지표** (RSI / BB / VWAP / EMA / Stoch / MACD / ATR / 거래량) |
| 배분 | 열린 심볼 `<4` → 총 equity의 **20%**; `==4`(마지막 슬롯) → **잔여 현금 전액** |
| 마진 | **격리** (한 심볼 청산 = 그 슬롯 마진만 손실; 슬롯 liq ≠ 계좌 청산) |
| 목표 | 합산 계좌 창마다 $100 → 10,000x **+ 계좌 청산 0** (MDD 비목표) |

| 심볼 | 전략 | 주요 보조지표 |
|------|------|----------------|
| BTC | **국면별 3전략** (bull 추세 / bear 추세 / sideways BB 페이드) | 15m HTF EMA, EMA9/21, VWAP, RSI, MACD, BB, ATR |
| ETH | **국면별 3전략** (bull/bear RSI 모멘텀 / sideways BB 페이드) | RSI(7), EMA8/21, VWAP, BB, ATR |
| BNB | **국면별 3전략** (bull/bear BB 돌파 / sideways 밴드 페이드) | BB(20,2), squeeze, RSI, VWAP, ATR |
| SOL | **국면별 3전략** (bull/bear Stoch+MACD / sideways Stoch 페이드) | Stoch, MACD, EMA9, ATR 확장 |
| XRP | **국면별 3전략** (bull/bear 추세 되돌림 / sideways BB+RSI 페이드) | BB, RSI, EMA21, ATR |

## 국면(regime) 전략 — 심볼별 bull / bear / sideways

1m 단타이지만 **15m HTF**로 국면을 나누고, **해당 봉의 국면 전략만** 진입한다 (`strategies/regime.py`).

### 국면 분류 (공통, look-ahead 없음)

| 국면 | 조건 (15m HTF EMA50 + 1m 보조) |
|------|--------------------------------|
| **bull** | close > HTF EMA, EMA 기울기 > 0, ROC(60) > 0.08%, BB 폭 좁지 않음 |
| **bear** | close < HTF EMA, EMA 기울기 < 0, ROC(60) < -0.08%, BB 폭 좁지 않음 |
| **sideways** | 위 둘 다 아님 (횡보·스퀴즈·약한 추세) |

### 심볼별 전략 매핑

| 심볼 | bull (상승) | bear (하락) | sideways (횡보) |
|------|-------------|-------------|-----------------|
| BTC | EMA 크로스 + VWAP + MACD 추세 | 숏 추세 우선 + 과매도 반등 롱 | BB 터치 RSI 페이드 |
| ETH | RSI55 턴 + EMA8/21 + VWAP | RSI45 턴 숏 우선 + VWAP 반등 | BB+RSI 극단 페이드 |
| BNB | 스퀴즈/상단 돌파 + VWAP | 하단 돌파 + VWAP | BB 터치 RSI 페이드 |
| SOL | Stoch+MACD 모멘텀 (롱 우선) | Stoch+MACD 모멘텀 (숏 우선) | Stoch 극단 페이드 |
| XRP | EMA21 위 RSI 되돌림 롱 | EMA21 아래 RSI 되돌림 숏 | BB+RSI 평균회귀 (기존) |

### 연구 룰 (국면 축) — STRICT

목표는 **심볼별 상승/하락/횡보 전략을 코드로 다듬어** 전 창 10,000x + 계좌청산 0에 다가가는 것이다. 국면 스위치만 넣고 전략 본문을 방치하면 안 된다.

- **1세트 = 응집 수정 1개.** 우선 대상은 **심볼 1개의 `_bull` / `_bear` / `_sideways` 중 하나** (지표·진입·SL/trail·cooldown).
- 진단에 **어느 심볼 + 어느 국면**이 약한 창/wipe를 만드는지 적고, 그 축만 고친다.
- **심볼·국면을 돌려가며** 수정한다 (예: BTC sideways → ETH bear → SOL bull …). 같은 심볼·같은 국면만 연속 반복 금지.
- 공통 `classify_regime` 또는 `portfolio_engine.py`만 만지는 세트는 **진단이 그쪽을 가리킬 때만**, 그리고 **연속으로 쌓지 않는다**. 그다음 세트는 다시 심볼 국면 전략으로 돌아온다.
- Keep 우선순위: **hits → median → min → account_liq**. MDD는 Keep/Revert에 쓰지 않는다.
- 국면 전환만 바꿔 **max만 오르는 수정**은 Revert.
- sideways는 **횡보·chop** lift용, bull/bear는 **방향장** lift용.

```bash
python -u eval_portfolio_windows.py --capital 100 --tag port5 --out-dir reports/iter
# 스모크
python -u eval_portfolio_windows.py --start 2024-01 --end 2024-06 --max-windows 3 --tag smoke_port5
```

BTC 단독 대조용 `compound_engine.py` / `eval_windows.py`는 유지한다.

## 전략 리셋 (v2 — 전 구간 커버)

이전 챔피언(숏 전용 + 폭락 ATR size_boost)은 **한 레짐 수확기**였다. 폐기 방향:

| 버릴 것 | 이유 |
|---------|------|
| 숏 전용 | 상승/횡보 구간에서 거래 자체가 안 남 |
| extreme `size_boost` | 폭락 창 max만 키움, 전 구간 히트와 무관 |
| “max peak Keep” | 목표와 반대 방향 최적화 |

| 새 방향 | 이유 |
|---------|------|
| **심볼별 bull/bear/sideways 3전략** (15m HTF 국면 스위치) | chop vs 추세 구간에 맞는 진입 분리 |
| **롱+숏 레짐 정렬** (일봉 EMA + HTF) | 매 구간에 방향성 기회가 있게 |
| **균일 사이징** (boost 없음) | 특정 폭락에만 레버리지 몰빵 금지 |
| **필터는 ‘수수료 안 녹일 정도’만** | 너무 빡세면 43/59창이 무거래(peak=1) |
| 엔진 복리 + 실비용 유지 | 리얼리즘 |

이후 세트는 **죽은 창(peak≈1 / wipe)을 살리는 수정**을 우선한다.  
폭락 창을 더 키우는 수정은, 전 구간 히트/중앙값이 같이 나아지지 않으면 Revert.

## 탐색 원칙 (한 축에 갇히지 말 것)

한 가지 손잡이(예: trail `close_frac` 미세 상향)만 반복해서 median이 미세하게만 오르고 **hits / dead / min이 안 움직이면**, 그 축은 한계에 도달한 것으로 본다.

그때는 아래를 **번갈아** 시도한다 (세트당 응집 수정 1개 유지):

| 방향 | 예 |
|------|----|
| **지표 추가** | 새 모멘텀/볼륨/구조 필터, 보조 돌파 경로 |
| **지표 수정** | lookback, ROC/slope 기간, ATR 임계, body/range, HTF 정렬 완화·강화 |
| **지표 제거·완화** | 죽은 창(0거래)을 막는 과도한 AND 필터 끄기/완화 |
| **진입 구조 변경** | Donchian/일봉 경로, cooldown·reentry, 롱·숏 레짐 조건 |
| **엔진 리스크** | SL grace, risk cap, trail unlock, 사이징 — **계좌 wipe↑면 Revert** (슬롯 liq↑만으로 Revert 금지) |

금지에 가까운 패턴:

- 이미 Keep만 나오는 미세 ladder를 **수십 세트 연속**으로만 돌리기
- max만 키우는 폭락 특화 튜닝
- 수수료/슬리피지 끄기

Keep 기준은 그대로: **hits → median → min**. 실험 범위만 넓힌다.
