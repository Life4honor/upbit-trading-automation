#!/bin/bash
#
# 백테스트/로그 결과 정리 스크립트
#
# 사용법:
#   ./scripts/clean.sh                    # 백테스트 결과만 정리
#   ./scripts/clean.sh --all              # 백테스트 + 로그 모두 정리
#   ./scripts/clean.sh --coin BTC         # BTC 코인만 정리
#   ./scripts/clean.sh --coin all         # 모든 코인 정리
#   ./scripts/clean.sh --backup           # 백업 후 정리
#   ./scripts/clean.sh --force            # 확인 없이 바로 삭제
#

set -e

# ==========================================
# 설정
# ==========================================

BACKUP_MODE=false
FORCE_MODE=false
CLEAN_LOGS=false
COIN_FILTER=""

# ==========================================
# 인자 파싱
# ==========================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --backup)
            BACKUP_MODE=true
            shift
            ;;
        --force)
            FORCE_MODE=true
            shift
            ;;
        --all)
            CLEAN_LOGS=true
            shift
            ;;
        --coin)
            COIN_FILTER="$2"
            shift 2
            ;;
        --help|-h)
            echo "사용법: $0 [옵션]"
            echo ""
            echo "옵션:"
            echo "  --backup           백업 후 정리"
            echo "  --force            확인 없이 바로 삭제"
            echo "  --all              백테스트 결과 + 로그 모두 정리"
            echo "  --coin <COIN>      특정 코인만 정리 (예: BTC, ETH)"
            echo "  --coin all         모든 코인 정리"
            echo "  --help             도움말 표시"
            echo ""
            echo "예시:"
            echo "  $0                       # 백테스트 결과만 정리 (확인 메시지)"
            echo "  $0 --backup              # 백업 후 정리"
            echo "  $0 --force               # 확인 없이 삭제"
            echo "  $0 --all --force         # 모두 확인 없이 삭제"
            echo "  $0 --coin BTC            # BTC만 정리"
            echo "  $0 --coin ETH --force    # ETH만 확인 없이 삭제"
            echo "  $0 --coin all            # 모든 코인 정리"
            exit 0
            ;;
        *)
            echo "❌ 알 수 없는 옵션: $1"
            echo "사용법: $0 [--backup] [--force] [--all] [--coin <COIN>]"
            exit 1
            ;;
    esac
done

# ==========================================
# 함수
# ==========================================

clean_directory() {
    local dir=$1
    local name=$2

    if [ ! -d "$dir" ]; then
        echo "📁 $name 디렉토리가 없습니다."
        return 0
    fi

    if [ ! "$(ls -A "$dir" 2>/dev/null)" ]; then
        echo "📁 $name 디렉토리가 이미 비어있습니다."
        return 0
    fi

    # 파일 개수 확인
    local file_count=$(find "$dir" -type f | wc -l | tr -d ' ')
    local dir_count=$(find "$dir" -mindepth 1 -type d | wc -l | tr -d ' ')

    echo ""
    echo "🗑️  $name 정리"
    echo "   디렉토리: $dir"
    echo "   파일: ${file_count}개"
    echo "   폴더: ${dir_count}개"

    # 강제 모드가 아니면 확인 (기본값: yes)
    if [ "$FORCE_MODE" = false ]; then
        read -p "   삭제하시겠습니까? [Y/n]: " confirm
        # 소문자로 변환
        confirm=$(echo "$confirm" | tr '[:upper:]' '[:lower:]')
        # 빈 값이면 yes로 처리
        if [ -z "$confirm" ]; then
            confirm="y"
        fi
        # n 또는 no만 거부
        if [ "$confirm" = "n" ] || [ "$confirm" = "no" ]; then
            echo "   ⏭️  건너뛰기"
            return 0
        fi
    fi

    # 백업 모드
    if [ "$BACKUP_MODE" = true ]; then
        local backup_name="${dir}_backup_$(date +%Y%m%d_%H%M%S)"
        echo "   📦 백업 중: $backup_name"
        mv "$dir" "$backup_name"
        mkdir -p "$dir"
        echo "   ✅ 백업 완료: $backup_name"
    else
        echo "   🗑️  삭제 중..."
        rm -rf "$dir"/*
        echo "   ✅ 정리 완료"
    fi
}

# ==========================================
# 코인별 정리 함수
# ==========================================

clean_coin_directory() {
    local base_dir=$1
    local coin=$2
    local type_name=$3

    local coin_dir="$base_dir/$coin"

    if [ ! -d "$coin_dir" ]; then
        echo "📁 $coin 디렉토리가 없습니다: $coin_dir"
        return 0
    fi

    if [ ! "$(ls -A "$coin_dir" 2>/dev/null)" ]; then
        echo "📁 $coin 디렉토리가 이미 비어있습니다."
        return 0
    fi

    # 파일 개수 확인
    local file_count=$(find "$coin_dir" -type f | wc -l | tr -d ' ')
    local dir_count=$(find "$coin_dir" -mindepth 1 -type d | wc -l | tr -d ' ')

    echo ""
    echo "🗑️  $type_name - $coin 정리"
    echo "   디렉토리: $coin_dir"
    echo "   파일: ${file_count}개"
    echo "   폴더: ${dir_count}개"

    # 강제 모드가 아니면 확인 (기본값: yes)
    if [ "$FORCE_MODE" = false ]; then
        read -p "   삭제하시겠습니까? [Y/n]: " confirm
        # 소문자로 변환
        confirm=$(echo "$confirm" | tr '[:upper:]' '[:lower:]')
        # 빈 값이면 yes로 처리
        if [ -z "$confirm" ]; then
            confirm="y"
        fi
        # n 또는 no만 거부
        if [ "$confirm" = "n" ] || [ "$confirm" = "no" ]; then
            echo "   ⏭️  건너뛰기"
            return 0
        fi
    fi

    # 백업 모드
    if [ "$BACKUP_MODE" = true ]; then
        local backup_name="${coin_dir}_backup_$(date +%Y%m%d_%H%M%S)"
        echo "   📦 백업 중: $backup_name"
        mv "$coin_dir" "$backup_name"
        mkdir -p "$coin_dir"
        echo "   ✅ 백업 완료: $backup_name"
    else
        echo "   🗑️  삭제 중..."
        rm -rf "$coin_dir"/*
        echo "   ✅ 정리 완료"
    fi
}

# ==========================================
# 메인 로직
# ==========================================

echo "════════════════════════════════════════"
echo "🧹 결과 정리 스크립트"
echo "════════════════════════════════════════"

if [ "$BACKUP_MODE" = true ]; then
    echo "모드: 백업 후 정리"
elif [ "$FORCE_MODE" = true ]; then
    echo "모드: 강제 삭제 (확인 없음)"
else
    echo "모드: 일반 정리 (확인 필요)"
fi

if [ "$CLEAN_LOGS" = true ]; then
    echo "대상: 백테스트 결과 + 로그"
else
    echo "대상: 백테스트 결과만"
fi

if [ -n "$COIN_FILTER" ]; then
    if [ "$COIN_FILTER" = "all" ]; then
        echo "코인: 전체"
    else
        echo "코인: $COIN_FILTER"
    fi
fi

echo "════════════════════════════════════════"

# 코인별 정리
if [ -n "$COIN_FILTER" ]; then
    if [ "$COIN_FILTER" = "all" ]; then
        # 모든 코인 정리
        if [ -d "backtest_reports" ]; then
            for coin_dir in backtest_reports/*/; do
                if [ -d "$coin_dir" ]; then
                    coin=$(basename "$coin_dir")
                    clean_coin_directory "backtest_reports" "$coin" "백테스트 결과"
                fi
            done
        fi

        if [ "$CLEAN_LOGS" = true ] && [ -d "logs" ]; then
            for coin_dir in logs/*/; do
                if [ -d "$coin_dir" ]; then
                    coin=$(basename "$coin_dir")
                    clean_coin_directory "logs" "$coin" "로그"
                fi
            done
        fi
    else
        # 특정 코인만 정리
        clean_coin_directory "backtest_reports" "$COIN_FILTER" "백테스트 결과"

        if [ "$CLEAN_LOGS" = true ]; then
            clean_coin_directory "logs" "$COIN_FILTER" "로그"
        fi
    fi
else
    # 전체 디렉토리 정리 (기존 방식)
    clean_directory "backtest_reports" "백테스트 결과"

    if [ "$CLEAN_LOGS" = true ]; then
        clean_directory "logs" "로그"
    fi
fi

echo ""
echo "════════════════════════════════════════"
echo "✅ 정리 완료!"
echo "════════════════════════════════════════"

# 백업 폴더 목록 표시
if [ "$BACKUP_MODE" = true ]; then
    echo ""
    echo "📦 백업 폴더 목록:"
    ls -dt backtest_reports_backup_* 2>/dev/null | head -5 || echo "   (백업 없음)"

    if [ "$CLEAN_LOGS" = true ]; then
        ls -dt logs_backup_* 2>/dev/null | head -5 || echo "   (로그 백업 없음)"
    fi
fi

echo ""
