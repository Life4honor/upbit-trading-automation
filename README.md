# 🤖 Upbit 자동매매 시스템

**5가지 규칙기반 트레이딩 전략**으로 백테스트와 실거래 모두 지원

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![uv](https://img.shields.io/badge/uv-latest-green.svg)](https://github.com/astral-sh/uv)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ 특징

- 🎯 **5가지 전략**: Momentum Breakout, Grid Trading, Volatility Breakout, Bollinger Reversal, RSI Scalping
- ✅ **단일 로직**: 백테스트와 실거래가 동일한 코드 사용
- 🔄 **통합 시스템**: `--backtest` / `--live` 파라미터로 모드 선택
- 📊 **일관된 리포트**: JSON + Markdown + CSV 형식으로 결과 저장
- 🏗️ **확장 가능**: BaseStrategy 상속으로 새로운 전략 추가 용이
- 🔒 **안전 장치**: 손절, 익절, 시간 손절 등 다중 보호 장치

---

## 🚀 빠른 시작

### 설치

```bash
# 1. uv 설치
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 프로젝트 클론
git clone <repository-url>
cd upbit-trading-automation

# 3. Python 버전 설정
uv python install 3.11
uv python pin 3.11

# 4. 의존성 설치
uv sync
```

### 백테스트 (전략 검증)

```bash
# 기본 RSI 스캘핑 (7일)
uv run scripts/run.py --backtest -m KRW-BTC --days 7

# 모멘텀 브레이크아웃 (30일)
uv run scripts/run.py --backtest -m KRW-ETH -p momentum-breakout --days 30

# 그리드 트레이딩 (90일)
uv run scripts/run.py --backtest -m KRW-SOL -p grid-trading --days 90

# 볼린저 리버설 (30일)
uv run scripts/run.py --backtest -m KRW-BTC -p bollinger-reversal --days 30
```

### 실거래 (⚠️ 주의)

```bash
# 1. API 키 설정
mkdir -p config
cat > config/api_keys.json << 'EOF'
{
  "access_key": "YOUR_ACCESS_KEY",
  "secret_key": "YOUR_SECRET_KEY"
}
EOF

# 2. Dry-run (설정만 확인)
uv run scripts/run.py --live -m KRW-BTC -p bollinger-reversal -a 100000 --dry-run

# 3. 실전 실행
uv run scripts/run.py --live -m KRW-BTC -p bollinger-reversal -a 100000
```

---

## 🎯 트레이딩 전략

### 1. **Momentum Breakout** (모멘텀 브레이크아웃)

**특징**: 강한 추세 포착, 큰 수익 기대

```bash
uv run scripts/run.py --backtest -m KRW-BTC -p momentum-breakout --days 30
```

**진입 조건**:
- ✅ 가격이 20일 고점 돌파
- ✅ 거래량이 평균의 1.5배 이상
- ✅ RSI > 50 (과매도 아님)
- ✅ MACD > Signal (상승 추세)

**청산 조건**:
- 목표 익절: +3%
- 손절: -1.5%
- 트레일링 스톱: 고점 대비 -2%
- MACD 추세 전환 시 익절

**적합한 시장**: 강한 상승 추세, 높은 변동성

---

### 2. **Grid Trading** (그리드 트레이딩)

**특징**: 횡보장 수익 극대화, 높은 승률

```bash
uv run scripts/run.py --backtest -m KRW-ETH -p grid-trading --days 90
```

**진입 조건**:
- ✅ ATR < 평균의 80% (낮은 변동성)
- ✅ 그리드 하단 레벨 도달
- ✅ 최대 3개 포지션 동시 보유

**청산 조건**:
- 개별 그리드: +1% 익절
- 총 손실 한도: -3%
- 변동성 급증 시 청산

**적합한 시장**: 횡보장, 낮은 변동성

---

### 3. **Volatility Breakout** (변동성 브레이크아웃)

**특징**: ATR 기반 급등락 포착, 고위험 고수익

```bash
uv run scripts/run.py --backtest -m KRW-SOL -p volatility-breakout --days 60
```

**진입 조건**:
- ✅ ATR > 평균의 1.5배 (변동성 급증)
- ✅ 전일 고점 + (ATR * 0.5) 돌파
- ✅ 거래량 > 평균

**청산 조건**:
- 동적 익절: ATR의 2배
- 동적 손절: ATR의 1배
- 변동성 소멸 시 청산
- 고점 대비 -3% 반전 감지

**적합한 시장**: 급등락 장, 높은 변동성

---

### 4. **Bollinger Reversal** (볼린저 리버설)

**특징**: 평균회귀, 높은 승률, 빠른 진입/청산

```bash
uv run scripts/run.py --backtest -m KRW-BTC -p bollinger-reversal --days 30
```

**진입 조건**:
- ✅ BB 하단 돌파 후 반등
- ✅ RSI < 30 (과매도)
- ✅ 거래량 > 평균
- ✅ 양봉 출현 (반등 신호)

**청산 조건**:
- 목표: BB 중심선 도달 또는 +2%
- 손절: -1.5%
- BB 하단 재돌파 시 손절
- RSI > 70 과매수 익절
- 60분 시간 손절

**적합한 시장**: 횡보장, 과매도/과매수 반복

---

### 5. **RSI Scalping** (RSI 스캘핑) - Default

**특징**: 초단타 스캘핑, 동적 목표 수익률

```bash
uv run scripts/run.py --backtest -m KRW-ETH --days 7
```

**진입 조건**:
- ✅ RSI 5분: 60-85
- ✅ RSI 15분: 50-87
- ✅ SMA 7/25 정배열
- ✅ 거래량 > 평균
- ✅ 호가 불균형 > 60%

**청산 조건**:
- 동적 목표: 0.25~1.00% (시장 지표 기반)
- 손절: -0.45%
- SMA 이탈 청산
- 과열 익절 (RSI > 75)

**적합한 시장**: 모든 시장 (보수적)

---

## 📊 전략 비교

| 전략 | 승률 | 수익률 | 거래빈도 | 적합 시장 | 위험도 |
|------|------|--------|----------|-----------|--------|
| **Momentum Breakout** | 50-60% | +20~40% | 중간 | 강한 추세 | 중간 |
| **Grid Trading** | 80-90% | +10~20% | 높음 | 횡보장 | 낮음 |
| **Volatility Breakout** | 55-65% | +25~35% | 낮음 | 급등락 | 높음 |
| **Bollinger Reversal** | 70-80% | +15~25% | 높음 | 횡보/변동성 | 낮음 |
| **RSI Scalping** | 45-55% | +5~15% | 매우 높음 | 모든 시장 | 낮음 |

---

## 📁 프로젝트 구조

```
upbit-trading-automation/
├── src/core/
│   ├── base_strategy.py           # 전략 추상 클래스
│   ├── strategies/
│   │   ├── momentum_breakout.py   # 모멘텀 브레이크아웃
│   │   ├── grid_trading.py        # 그리드 트레이딩
│   │   ├── volatility_breakout.py # 변동성 브레이크아웃
│   │   ├── bollinger_reversal.py  # 볼린저 리버설
│   │   └── scalping.py            # RSI 스캘핑
│   ├── trader.py                  # 통합 트레이더 (전략 팩토리)
│   ├── api.py                     # Upbit API 래퍼
│   └── config.py                  # 전략별 preset 설정
├── scripts/
│   ├── run.py                     # 통합 실행 스크립트
│   ├── batch_runner.sh            # 배치 실행 (비교 모드)
│   └── clean.sh                   # 결과 정리
├── config/
│   └── api_keys.json              # API 키 (실거래용)
├── backtest_reports/              # 백테스트 결과
│   └── {COIN}/YYYY/MM/DD/
└── logs/                          # 실거래 로그
    └── {COIN}/YYYY/MM/DD/
```

---

## 🔧 배치 실행

### 전략 비교 모드

동일 코인에 대해 5가지 전략 모두 백테스트하고 결과 비교:

```bash
# 모든 전략 비교 (BTC+ETH, 30일)
./scripts/batch_runner.sh compare 30

# 단일 코인으로 전략 비교
./scripts/batch_runner.sh compare 30 KRW-BTC

# 특정 전략 실행 (모든 코인)
./scripts/batch_runner.sh backtest momentum-breakout 30

# 특정 전략 + 단일 코인
./scripts/batch_runner.sh backtest bollinger-reversal 90 KRW-BTC
```

### 결과 확인

```bash
# 백테스트 결과 확인
ls -lh backtest_reports/BTC/2025/10/15/

# 전략별 성과 비교
cat backtest_reports/BTC/2025/10/15/*_summary.txt
```

---

## 📝 사용 예시

### 백테스트

```bash
# 1. 기본 RSI 스캘핑 (7일)
uv run scripts/run.py --backtest -m KRW-BTC --days 7

# 2. 모멘텀 브레이크아웃 (30일)
uv run scripts/run.py --backtest -m KRW-ETH -p momentum-breakout --days 30

# 3. 그리드 트레이딩 (90일)
uv run scripts/run.py --backtest -m KRW-SOL -p grid-trading --days 90

# 4. 변동성 브레이크아웃 (60일)
uv run scripts/run.py --backtest -m KRW-BTC -p volatility-breakout --days 60

# 5. 볼린저 리버설 (30일)
uv run scripts/run.py --backtest -m KRW-ETH -p bollinger-reversal --days 30
```

### 실거래

```bash
# Dry-run (설정만 확인)
uv run scripts/run.py --live -m KRW-BTC -p bollinger-reversal -a 100000 --dry-run

# 실전 (볼린저 리버설)
uv run scripts/run.py --live -m KRW-BTC -p bollinger-reversal -a 100000

# 실전 (그리드 트레이딩)
uv run scripts/run.py --live -m KRW-ETH -p grid-trading -a 200000

# 체크 주기 변경 (기본 60초)
uv run scripts/run.py --live -m KRW-SOL -p momentum-breakout -a 50000 --interval 30
```

---

## 🎓 전략 선택 가이드

### 시장 상황별 추천 전략

**강한 상승 추세**:
- 1순위: Momentum Breakout
- 2순위: Volatility Breakout

**횡보장 (레인지)**:
- 1순위: Grid Trading
- 2순위: Bollinger Reversal

**높은 변동성**:
- 1순위: Volatility Breakout
- 2순위: Bollinger Reversal

**불확실한 시장**:
- 1순위: Bollinger Reversal
- 2순위: RSI Scalping (안전)

### 초보자 추천 순서

1. **Bollinger Reversal** (높은 승률, 명확한 신호)
2. **Grid Trading** (안정적, 횡보장)
3. **RSI Scalping** (보수적, 소액)
4. **Momentum Breakout** (추세 확실할 때)
5. **Volatility Breakout** (경험 쌓은 후)

---

## 🛡️ 안전 장치

모든 전략은 다음 안전 장치를 포함:

- ✅ **손절 보호**: 전략별 손절가 자동 청산
- ✅ **시간 손절**: 장기 보유 시 강제 청산
- ✅ **동적 익절**: 시장 상황에 따른 목표가 조정
- ✅ **잔고 확인**: 부족 시 자동 중단
- ✅ **쿨다운**: 거래 간 대기 시간
- ✅ **최대 거래 제한**: 일일 거래 횟수 제한

---

## 🔄 워크플로우

```
1. 전략 선택 (시장 상황 분석)
   ↓
2. 백테스트 (30-90일)
   ↓
3. 여러 전략 비교 (batch_runner.sh compare)
   ↓
4. 최고 성과 전략 선택
   ↓
5. 소액 실전 테스트 (5-10만원)
   ↓
6. 모니터링 및 조정
   ↓
7. 점진적 확장
```

---

## ⚠️ 주의사항

### ✅ 반드시 하세요

1. **백테스트 먼저** - 최소 30일, 권장 90일
2. **전략 비교** - 여러 전략 백테스트 후 선택
3. **소액으로 시작** - 5-10만원부터
4. **로그 확인** - 정기적으로 모니터링
5. **API 키 보안** - 절대 공개 금지 (.gitignore 확인)
6. **점진적 확장** - 안정되면 증액

### ❌ 하지 마세요

- 백테스트 없이 실전
- 한 가지 전략만 맹신
- 전 재산 투입
- API 키 공유/공개
- 불안정한 네트워크 환경
- 검증 안 된 파라미터 사용

---

## 🐛 트러블슈팅

### API 키 오류

```bash
# 키 확인
cat config/api_keys.json

# 권한 설정
chmod 600 config/api_keys.json
```

### 주문 실패

- **잔고 부족** → KRW 충전
- **최소 금액 미달** → 5000원 이상 설정
- **API 제한** → 체크 주기 증가 (--interval 120)

### 백테스트 오류

```bash
# 거래 없음 → 전략 변경 또는 기간 연장
# 데이터 다운로드 실패 → 네트워크 확인
# preset 오류 → preset 이름 확인 (--help)
```

---

## 📁 결과 파일 디렉토리 구조

모든 백테스트 및 라이브 거래 결과는 **코인별/날짜별**로 자동 정리됩니다:

### 백테스트 결과

```
backtest_reports/
├── BTC/                    # 코인별 디렉토리
│   └── 2025/              # 년도
│       └── 10/            # 월
│           └── 16/        # 일
│               ├── KRW-BTC_backtest_YYYYMMDD_HHmmss.log   # 로그 (세션별)
│               ├── KRW-BTC_backtest_YYYYMMDD_HHmmss.json  # JSON 결과
│               ├── KRW-BTC_backtest_YYYYMMDD_HHmmss.md    # 마크다운 리포트
│               └── KRW-BTC_backtest_YYYYMMDD_HHmmss.csv   # CSV 거래내역
├── ETH/
│   └── 2025/10/16/
└── SOL/
    └── 2025/10/16/
```

### 라이브 거래 결과

```
logs/
├── BTC/                    # 코인별 디렉토리
│   └── 2025/              # 년도
│       └── 10/            # 월
│           └── 16/        # 일
│               ├── KRW-BTC_live_YYYYMMDD_HHmmss.log       # 로그 (세션별)
│               ├── KRW-BTC_live_YYYYMMDD_HHmmss.json      # JSON 결과
│               ├── KRW-BTC_live_YYYYMMDD_HHmmss.md        # 마크다운 리포트
│               └── KRW-BTC_live_YYYYMMDD_HHmmss.csv       # CSV 거래내역
├── ETH/
└── SOL/
```

### 파일명 형식

- **세션 ID**: `YYYYMMDD_HHmmss` (시작 시간)
- **로그 파일**: `{마켓}_{모드}_{세션ID}.log`
- **결과 파일**: `{마켓}_{모드}_{세션ID}.{json|md|csv}`

### 장점

✅ **일자별 정리**: 특정 날짜의 결과를 쉽게 찾을 수 있음
✅ **코인별 분류**: 각 코인의 성과를 독립적으로 추적
✅ **세션 구분**: 같은 날 여러 번 실행해도 덮어쓰지 않음
✅ **형식 선택**: JSON(프로그래밍), MD(읽기), CSV(분석) 모두 제공

---
