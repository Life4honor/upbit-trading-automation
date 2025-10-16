#!/bin/bash
#
# 배치 실행 스크립트 (백테스트/실거래)
# 복수 코인에 대해 비동기 병렬 실행 + 전략 비교 모드
#
# 사용법:
#   ./scripts/batch_runner.sh backtest [preset] [days] [market]     # 백테스트 모드
#   ./scripts/batch_runner.sh compare [days] [market]               # 전략 비교 모드
#   ./scripts/batch_runner.sh live [preset] [amount] [market]       # 실거래 모드
#
# 예시:
#   ./scripts/batch_runner.sh backtest bollinger-reversal 30 KRW-BTC  # 단일 코인
#   ./scripts/batch_runner.sh backtest bollinger-reversal 30          # 모든 코인 (BTC, ETH)
#   ./scripts/batch_runner.sh compare 30
#   ./scripts/batch_runner.sh live grid-trading 100000 KRW-BTC
#

set -e

# ==========================================
# 설정
# ==========================================

# 실행 모드 (backtest, compare, 또는 live)
MODE="${1:-backtest}"

# 기본 대상 코인
DEFAULT_MARKETS=("KRW-BTC" "KRW-ETH")

# 사용 가능한 전략 목록
STRATEGIES=("default" "momentum-breakout" "grid-trading" "volatility-breakout" "bollinger-reversal")

# 최대 동시 실행 수
MAX_PARALLEL=10

# ==========================================
# 모드별 파라미터 처리
# ==========================================

if [ "$MODE" = "backtest" ]; then
    # 백테스트 모드: preset, days, market 설정
    PRESET="${2:-default}"
    DAYS="${3:-30}"
    MARKET="${4:-}"

    # Preset 유효성 검사
    if [[ ! " ${STRATEGIES[@]} " =~ " ${PRESET} " ]]; then
        echo "❌ 잘못된 preset: $PRESET"
        echo "사용 가능한 preset: ${STRATEGIES[@]}"
        exit 1
    fi

    # 마켓 설정
    if [ -n "$MARKET" ]; then
        MARKETS=("$MARKET")
    else
        MARKETS=("${DEFAULT_MARKETS[@]}")
    fi

elif [ "$MODE" = "compare" ]; then
    # 비교 모드: 모든 전략 실행
    DAYS="${2:-30}"
    MARKET="${3:-}"

    # 마켓 설정
    if [ -n "$MARKET" ]; then
        MARKETS=("$MARKET")
    else
        MARKETS=("${DEFAULT_MARKETS[@]}")
    fi

elif [ "$MODE" = "live" ]; then
    # 실거래 모드: preset, 금액, market 설정
    PRESET="${2:-default}"
    TRADE_AMOUNT="${3:-100000}"
    MARKET="${4:-}"

    # Preset 유효성 검사
    if [[ ! " ${STRATEGIES[@]} " =~ " ${PRESET} " ]]; then
        echo "❌ 잘못된 preset: $PRESET"
        echo "사용 가능한 preset: ${STRATEGIES[@]}"
        exit 1
    fi

    # 마켓 설정
    if [ -n "$MARKET" ]; then
        MARKETS=("$MARKET")
    else
        MARKETS=("${DEFAULT_MARKETS[@]}")
    fi

else
    echo "❌ 잘못된 모드: $MODE"
    echo ""
    echo "사용법:"
    echo "  $0 backtest [preset] [days] [market]"
    echo "  $0 compare [days] [market]"
    echo "  $0 live [preset] [amount] [market]"
    echo ""
    echo "예시:"
    echo "  $0 backtest bollinger-reversal 30 KRW-BTC  # 단일 코인"
    echo "  $0 backtest bollinger-reversal 30          # 모든 코인"
    echo "  $0 compare 30"
    echo "  $0 live grid-trading 100000 KRW-BTC"
    exit 1
fi

# ==========================================
# 함수
# ==========================================

# 백테스트 실행 함수
run_backtest() {
    local market=$1
    local preset=$2
    local days=$3

    # 배치 실행 로그를 날짜별로 정리
    local date_path=$(date +%Y/%m/%d)
    local log_dir="batch_logs/${date_path}"
    mkdir -p "$log_dir"
    local log_file="${log_dir}/batch_${market}_${preset}_${days}d_$(date +%Y%m%d_%H%M%S).log"

    echo "🔄 [백테스트] $market - $preset (${days}일) 시작..."

    if [ "$preset" = "default" ]; then
        uv run scripts/run.py --backtest -m "$market" --days "$days" > "$log_file" 2>&1
    else
        uv run scripts/run.py --backtest -m "$market" -p "$preset" --days "$days" > "$log_file" 2>&1
    fi

    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        echo "✅ [백테스트] $market - $preset (${days}일) 완료"

        # 결과 요약 추출
        local win_rate=$(grep "승률:" "$log_file" | awk '{print $2}' || echo "N/A")
        local profit=$(grep "수익률:" "$log_file" | awk '{print $2}' || echo "N/A")
        local trades=$(grep "거래:" "$log_file" | awk '{print $2}' | head -1 || echo "N/A")

        echo "   승률: $win_rate | 수익률: $profit | 거래: $trades"
    else
        echo "❌ [백테스트] $market - $preset (${days}일) 실패 (코드: $exit_code)"
    fi

    return $exit_code
}

# 실거래 실행 함수
run_live() {
    local market=$1
    local preset=$2
    local amount=$3

    echo "🤖 [실거래] $market - $preset (₩${amount}) 시작..."
    echo "⚠️  주의: 실제 거래가 시작됩니다!"

    # 실거래는 포그라운드에서 실행 (Ctrl+C로 중지 가능)
    if [ "$preset" = "default" ]; then
        uv run scripts/run.py --live -m "$market" -a "$amount"
    else
        uv run scripts/run.py --live -m "$market" -p "$preset" -a "$amount"
    fi

    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        echo "✅ [실거래] $market 정상 종료"
    else
        echo "❌ [실거래] $market 비정상 종료 (코드: $exit_code)"
    fi

    return $exit_code
}

# PID 배열에서 완료된 작업 체크
wait_for_slot() {
    while [ ${#PIDS[@]} -ge $MAX_PARALLEL ]; do
        for i in "${!PIDS[@]}"; do
            if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
                wait "${PIDS[$i]}" 2>/dev/null
                unset PIDS[$i]
            fi
        done
        PIDS=("${PIDS[@]}")  # 배열 재정렬
        sleep 0.5
    done
}

# 전략 비교 결과 요약 함수
print_comparison_summary() {
    local days=$1

    echo ""
    echo "════════════════════════════════════════"
    echo "📊 전략 비교 결과 요약 (${days}일)"
    echo "════════════════════════════════════════"
    echo ""

    printf "%-25s | %-10s | %-12s | %-10s\n" "전략" "승률" "수익률" "거래 횟수"
    echo "─────────────────────────────────────────────────────────────"

    for strategy in "${STRATEGIES[@]}"; do
        # 최신 로그 파일 찾기 (날짜별 디렉토리 탐색)
        local latest_log=$(find batch_logs -name "batch_*_${strategy}_${days}d_*.log" 2>/dev/null | sort -r | head -1)

        if [ -f "$latest_log" ]; then
            local win_rate=$(grep "승률:" "$latest_log" | awk '{print $2}' || echo "N/A")
            local profit=$(grep "수익률:" "$latest_log" | awk '{print $2}' || echo "N/A")
            local trades=$(grep "거래:" "$latest_log" | awk '{print $2}' | head -1 || echo "N/A")

            printf "%-25s | %-10s | %-12s | %-10s\n" "$strategy" "$win_rate" "$profit" "$trades"
        else
            printf "%-25s | %-10s | %-12s | %-10s\n" "$strategy" "N/A" "N/A" "N/A"
        fi
    done

    echo "─────────────────────────────────────────────────────────────"
    echo ""
}

# ==========================================
# 메인 로직
# ==========================================

# 배치 로그 디렉토리 생성 (날짜별)
mkdir -p batch_logs/$(date +%Y/%m/%d)

echo "════════════════════════════════════════"
echo "🚀 배치 실행기"
echo "════════════════════════════════════════"
echo "모드: $MODE"

if [ "$MODE" = "backtest" ]; then
    echo "전략: $PRESET"
    echo "기간: ${DAYS}일"
    echo "코인: ${MARKETS[@]}"
    echo "병렬 실행: 최대 $MAX_PARALLEL 개"
    echo ""

elif [ "$MODE" = "compare" ]; then
    echo "전략: 전체 비교 (${#STRATEGIES[@]}개)"
    echo "기간: ${DAYS}일"
    echo "코인: ${MARKETS[@]}"
    echo "병렬 실행: 최대 $MAX_PARALLEL 개"
    echo ""

elif [ "$MODE" = "live" ]; then
    echo "전략: $PRESET"
    echo "코인: ${MARKETS[@]}"
    echo "거래 금액: ₩$TRADE_AMOUNT"
    echo "⚠️  실거래 모드입니다!"
    echo ""
    read -p "계속하시겠습니까? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "취소되었습니다."
        exit 0
    fi
fi

echo "════════════════════════════════════════"
echo ""

# 백테스트/비교 모드인 경우 기존 결과 정리 확인
if [ "$MODE" = "backtest" ] || [ "$MODE" = "compare" ]; then
    if [ -d "backtest_reports" ] && [ "$(ls -A backtest_reports 2>/dev/null)" ]; then
        echo "🗑️  기존 백테스트 결과 정리"
        echo ""
        ./scripts/clean.sh
        echo ""
    fi
fi

# 시작 시간
START_TIME=$(date +%s)

# PID 배열 (백그라운드 작업 관리)
declare -a PIDS

# ==========================================
# 백테스트 모드
# ==========================================

if [ "$MODE" = "backtest" ]; then
    TOTAL_TASKS=${#MARKETS[@]}
    CURRENT_TASK=0

    echo "📊 총 $TOTAL_TASKS 개 백테스트 작업 시작 ($PRESET)"
    echo ""

    for market in "${MARKETS[@]}"; do
        # 동시 실행 수 제한
        wait_for_slot

        # 백그라운드로 실행
        run_backtest "$market" "$PRESET" "$DAYS" &
        PIDS+=($!)

        CURRENT_TASK=$((CURRENT_TASK + 1))
        echo "📈 진행: $CURRENT_TASK/$TOTAL_TASKS"
        echo ""

        # 짧은 대기 (API 요청 분산)
        sleep 1
    done

    # 모든 작업 완료 대기
    echo "⏳ 남은 작업 완료 대기 중..."
    for pid in "${PIDS[@]}"; do
        wait "$pid" 2>/dev/null || true
    done

# ==========================================
# 전략 비교 모드
# ==========================================

elif [ "$MODE" = "compare" ]; then
    TOTAL_TASKS=$((${#MARKETS[@]} * ${#STRATEGIES[@]}))
    CURRENT_TASK=0

    echo "📊 총 $TOTAL_TASKS 개 백테스트 작업 시작 (전략 비교)"
    echo ""

    for market in "${MARKETS[@]}"; do
        for strategy in "${STRATEGIES[@]}"; do
            # 동시 실행 수 제한
            wait_for_slot

            # 백그라운드로 실행
            run_backtest "$market" "$strategy" "$DAYS" &
            PIDS+=($!)

            CURRENT_TASK=$((CURRENT_TASK + 1))
            echo "📈 진행: $CURRENT_TASK/$TOTAL_TASKS"
            echo ""

            # 짧은 대기 (API 요청 분산)
            sleep 2
        done
    done

    # 모든 작업 완료 대기
    echo "⏳ 남은 작업 완료 대기 중..."
    for pid in "${PIDS[@]}"; do
        wait "$pid" 2>/dev/null || true
    done

    # 비교 결과 요약 출력
    print_comparison_summary "$DAYS"

# ==========================================
# 실거래 모드 (순차 실행)
# ==========================================

elif [ "$MODE" = "live" ]; then
    echo "⚠️  실거래는 한 번에 하나씩 순차 실행됩니다."
    echo "⚠️  Ctrl+C로 현재 거래를 중지할 수 있습니다."
    echo ""

    for market in "${MARKETS[@]}"; do
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "🤖 $market 실거래 시작 ($PRESET)"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

        run_live "$market" "$PRESET" "$TRADE_AMOUNT"

        echo ""
        read -p "다음 코인으로 진행하시겠습니까? (yes/no): " continue_trade
        if [ "$continue_trade" != "yes" ]; then
            echo "중단되었습니다."
            break
        fi
    done
fi

# ==========================================
# 완료 요약
# ==========================================

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
MINUTES=$((ELAPSED / 60))
SECONDS=$((ELAPSED % 60))

echo ""
echo "════════════════════════════════════════"
echo "✅ 모든 작업 완료!"
echo "════════════════════════════════════════"
echo "총 소요 시간: ${MINUTES}분 ${SECONDS}초"
echo ""

if [ "$MODE" = "backtest" ] || [ "$MODE" = "compare" ]; then
    echo "📊 결과 확인:"
    echo "  백테스트 결과: backtest_reports/{코인}/{날짜}/"
    echo "  배치 로그: batch_logs/$(date +%Y/%m/%d)/"
    echo ""

    if [ "$MODE" = "compare" ]; then
        echo "💡 Tip:"
        echo "  전략별 상세 결과는 backtest_reports/{코인}/$(date +%Y/%m/%d)/ 에서 확인하세요"
        echo "  최고 성과 전략을 선택하여 실전 테스트를 진행하세요"
    fi
    echo ""
    echo "📝 주요 파일:"
    echo "  - JSON: 프로그래밍 분석용"
    echo "  - MD:   읽기 편한 리포트"
    echo "  - CSV:  스프레드시트 분석용"
fi

echo "════════════════════════════════════════"
