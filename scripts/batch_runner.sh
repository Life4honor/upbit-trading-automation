#!/bin/bash
#
# 배치 실행 스크립트 (백테스트/실거래)
# 복수 코인에 대해 비동기 병렬 실행
#
# 사용법:
#   ./scripts/batch_runner.sh backtest      # 백테스트 모드
#   ./scripts/batch_runner.sh live 100000   # 실거래 모드 (거래금액)
#

set -e

# ==========================================
# 설정
# ==========================================

# 실행 모드 (backtest 또는 live)
MODE="${1:-backtest}"

# 실거래 금액 (live 모드일 때만 사용)
TRADE_AMOUNT="${2:-100000}"

# 대상 코인
MARKETS=("KRW-BTC" "KRW-ETH" "KRW-XRP" "KRW-SOL")

# 백테스트 기간 (backtest 모드일 때만 사용)
DAYS=(7 30)

# 최대 동시 실행 수
MAX_PARALLEL=8

# ==========================================
# 함수
# ==========================================

# 백테스트 실행 함수
run_backtest() {
    local market=$1
    local days=$2
    local log_file="logs/batch_${market}_${days}d_$(date +%Y%m%d_%H%M%S).log"

    echo "🔄 [백테스트] $market - ${days}일 시작..."

    uv run scripts/run.py --backtest -m "$market" --days "$days" > "$log_file" 2>&1

    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        echo "✅ [백테스트] $market - ${days}일 완료"
        # 결과 요약 출력
        grep -A 5 "백테스트 완료" "$log_file" || true
    else
        echo "❌ [백테스트] $market - ${days}일 실패 (코드: $exit_code)"
    fi

    return $exit_code
}

# 실거래 실행 함수
run_live() {
    local market=$1
    local amount=$2

    echo "🤖 [실거래] $market - ₩${amount} 시작..."
    echo "⚠️  주의: 실제 거래가 시작됩니다!"

    # 실거래는 포그라운드에서 실행 (Ctrl+C로 중지 가능)
    uv run scripts/run.py --live -m "$market" -a "$amount"

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

# ==========================================
# 메인 로직
# ==========================================

# 로그 디렉토리 생성
mkdir -p logs

echo "════════════════════════════════════════"
echo "🚀 배치 실행기"
echo "════════════════════════════════════════"
echo "모드: $MODE"
echo "코인: ${MARKETS[@]}"

if [ "$MODE" = "backtest" ]; then
    echo "기간: ${DAYS[@]}일"
    echo "병렬 실행: 최대 $MAX_PARALLEL 개"
    echo ""

    # 기존 백테스트 결과 정리 (clean.sh 사용)
    if [ -d "backtest_reports" ] && [ "$(ls -A backtest_reports 2>/dev/null)" ]; then
        echo "🗑️  기존 백테스트 결과를 정리합니다..."
        echo ""

        # clean.sh 실행 (강제 모드)
        ./scripts/clean.sh --force

        echo ""
    else
        echo "📁 백테스트 결과 디렉토리가 비어있거나 없습니다."
        mkdir -p backtest_reports
        echo ""
    fi
elif [ "$MODE" = "live" ]; then
    echo "거래 금액: ₩$TRADE_AMOUNT"
    echo "⚠️  실거래 모드입니다!"
    echo ""
    read -p "계속하시겠습니까? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "취소되었습니다."
        exit 0
    fi
else
    echo "❌ 잘못된 모드: $MODE"
    echo "사용법: $0 [backtest|live] [거래금액]"
    exit 1
fi

echo "════════════════════════════════════════"
echo ""

# 시작 시간
START_TIME=$(date +%s)

# PID 배열 (백그라운드 작업 관리)
declare -a PIDS

# ==========================================
# 백테스트 모드
# ==========================================

if [ "$MODE" = "backtest" ]; then
    TOTAL_TASKS=$((${#MARKETS[@]} * ${#DAYS[@]}))
    CURRENT_TASK=0

    echo "📊 총 $TOTAL_TASKS 개 백테스트 작업 시작"
    echo ""

    for market in "${MARKETS[@]}"; do
        for day in "${DAYS[@]}"; do
            # 동시 실행 수 제한
            wait_for_slot

            # 백그라운드로 실행
            run_backtest "$market" "$day" &
            PIDS+=($!)

            CURRENT_TASK=$((CURRENT_TASK + 1))
            echo "📈 진행: $CURRENT_TASK/$TOTAL_TASKS"
            echo ""

            # 짧은 대기 (API 요청 분산)
            sleep 1
        done
    done

    # 모든 작업 완료 대기
    echo "⏳ 남은 작업 완료 대기 중..."
    for pid in "${PIDS[@]}"; do
        wait "$pid" 2>/dev/null || true
    done

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
        echo "🤖 $market 실거래 시작"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

        run_live "$market" "$TRADE_AMOUNT"

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

if [ "$MODE" = "backtest" ]; then
    echo "📊 결과 확인:"
    echo "  backtest_reports/ 디렉토리를 확인하세요"
    echo ""
    echo "📝 로그 확인:"
    echo "  ls -lh logs/batch_*.log"
fi

echo "════════════════════════════════════════"
