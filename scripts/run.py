#!/usr/bin/env python3
"""
통합 실행 스크립트
백테스트와 실거래를 하나의 명령어로

사용법:
    # 백테스트 (기본 RSI 스캘핑)
    uv run scripts/run.py --backtest -m KRW-BTC --days 7

    # 백테스트 (새로운 전략)
    uv run scripts/run.py --backtest -m KRW-ETH -p momentum-breakout --days 30
    uv run scripts/run.py --backtest -m KRW-SOL -p grid-trading --days 90
    uv run scripts/run.py --backtest -m KRW-BTC -p volatility-breakout --days 60
    uv run scripts/run.py --backtest -m KRW-ETH -p bollinger-reversal --days 30

    # 실거래 (⚠️ 주의: 실제 거래!)
    uv run scripts/run.py --live -m KRW-BTC -a 100000
    uv run scripts/run.py --live -m KRW-ETH -p bollinger-reversal -a 50000
"""

import sys
import argparse
from pathlib import Path

# 프로젝트 루트
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from core.trader import UnifiedTrader
from core.api import UpbitAPI, load_api_keys
from core.config import get_config, print_config


def parse_args():
    """명령줄 인자"""
    parser = argparse.ArgumentParser(
        description='🤖 Upbit 통합 트레이더 (백테스트 + 실거래)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 백테스트 (기본 RSI 스캘핑)
  uv run scripts/run.py --backtest -m KRW-BTC --days 7

  # 백테스트 (새로운 전략)
  uv run scripts/run.py --backtest -m KRW-ETH -p momentum-breakout --days 30
  uv run scripts/run.py --backtest -m KRW-SOL -p grid-trading --days 90
  uv run scripts/run.py --backtest -m KRW-BTC -p volatility-breakout --days 60
  uv run scripts/run.py --backtest -m KRW-ETH -p bollinger-reversal --days 30

  # 실거래 (⚠️ 주의: 실제 거래!)
  uv run scripts/run.py --live -m KRW-BTC -a 100000
  uv run scripts/run.py --live -m KRW-ETH -p bollinger-reversal -a 50000

  # Dry-run (설정만 확인)
  uv run scripts/run.py --live -m KRW-BTC -p grid-trading -a 100000 --dry-run
        """
    )
    
    # 모드 선택
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        '--backtest',
        action='store_true',
        help='백테스트 모드 (과거 데이터 시뮬레이션)'
    )
    mode_group.add_argument(
        '--live',
        action='store_true',
        help='실거래 모드 (⚠️ 실제 거래 실행)'
    )
    
    # 공통 옵션
    parser.add_argument(
        '-m', '--market',
        type=str,
        required=True,
        help='마켓 코드 (예: KRW-BTC, KRW-ETH)'
    )
    
    parser.add_argument(
        '-p', '--preset',
        type=str,
        default='default',
        choices=[
            'default',
            'momentum-breakout',
            'grid-trading',
            'volatility-breakout',
            'bollinger-reversal',
        ],
        help='전략 프리셋 (기본: default=RSI스캘핑)'
    )
    
    # 백테스트 옵션
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='백테스트 기간 (일) (기본: 7)'
    )
    
    # 실거래 옵션
    parser.add_argument(
        '-a', '--amount',
        type=int,
        default=100000,
        help='1회 거래 금액 (원) (기본: 100,000)'
    )
    
    parser.add_argument(
        '--interval',
        type=int,
        default=5,
        help='체크 주기 (초) (기본: 5)'
    )
    
    # 커스텀 설정
    parser.add_argument(
        '--target',
        type=float,
        help='목표 수익률 (%%)'
    )
    
    parser.add_argument(
        '--stoploss',
        type=float,
        help='손절 기준 (%%)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='실행 전 설정만 확인 (거래 안 함)'
    )
    
    return parser.parse_args()


def confirm_live_trading():
    """실거래 확인"""
    print()
    print("⚠️" * 20)
    print()
    print("🚨 실제 거래가 실행됩니다!")
    print()
    print("확인 사항:")
    print("  1. ✅ API 키가 올바른지 확인")
    print("  2. ✅ 충분한 KRW 잔고 확인")
    print("  3. ✅ 전략 설정 확인")
    print("  4. ✅ 인터넷 연결 안정적인지 확인")
    print()
    print("⚠️" * 20)
    print()
    
    response = input("계속하시겠습니까? (yes/no): ").strip().lower()
    return response in ['yes', 'y']


def run_backtest(args, config):
    """백테스트 실행"""
    print()
    print("=" * 60)
    print("📊 백테스트 모드")
    print("=" * 60)
    print()
    
    trader = UnifiedTrader(config, args.market, mode='backtest')
    results = trader.run_backtest(days=args.days)
    
    if 'error' in results:
        print(f"❌ 오류: {results['error']}")
        return
    
    # 결과 출력
    print()
    print("=" * 60)
    print("✅ 백테스트 완료!")
    print("=" * 60)
    print(f"승률: {results['win_rate']:.1f}%")
    print(f"수익률: {results['total_profit_rate']:+.2f}%")
    print(f"거래: {results['total_trades']}회")
    print(f"MDD: {results['max_drawdown']:.2f}%")
    print(f"샤프: {results['sharpe_ratio']:.2f}")
    print("=" * 60)


def run_live(args, config):
    """실거래 실행"""
    print()
    print("=" * 60)
    print("🤖 실거래 모드")
    print("=" * 60)
    print()
    
    # API 키 로드
    try:
        print("🔑 API 키 로드...")
        keys = load_api_keys()
        print("✅ API 키 로드 완료")
    except Exception as e:
        print(f"❌ API 키 로드 실패: {e}")
        print()
        print("📝 config/api_keys.json 생성:")
        print("""
{
  "access_key": "YOUR_ACCESS_KEY",
  "secret_key": "YOUR_SECRET_KEY"
}
        """)
        sys.exit(1)
    
    # API 연결 테스트
    try:
        print()
        print("🔗 Upbit 연결 테스트...")
        api = UpbitAPI(keys['access_key'], keys['secret_key'])
        
        accounts = api.get_accounts()
        if not accounts:
            raise Exception("계좌 정보 없음")
        
        krw_balance = api.get_balance('KRW')
        print(f"✅ 연결 성공")
        print(f"💰 KRW 잔고: ₩{krw_balance:,.0f}")
        
    except Exception as e:
        print(f"❌ 연결 실패: {e}")
        sys.exit(1)
    
    # 잔고 확인
    if krw_balance < args.amount:
        print()
        print(f"❌ 잔고 부족: ₩{krw_balance:,.0f} < ₩{args.amount:,.0f}")
        sys.exit(1)
    
    print()
    print(f"📊 마켓: {args.market}")
    print(f"💵 거래 금액: ₩{args.amount:,.0f}")
    print(f"⏱️  체크 주기: {args.interval}초")
    print()
    
    # Dry-run
    if args.dry_run:
        print("✅ Dry-run: 설정만 확인")
        print("실제 거래를 하려면 --dry-run 제거")
        return
    
    # 확인
    if not confirm_live_trading():
        print("❌ 사용자 취소")
        sys.exit(0)
    
    # 트레이더 시작
    try:
        trader = UnifiedTrader(config, args.market, mode='live', api=api)
        trader.run_live()
        
    except KeyboardInterrupt:
        print()
        print("⚠️ 사용자 중지")
    
    except Exception as e:
        print()
        print(f"❌ 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """메인"""
    args = parse_args()
    
    # 설정 로드
    config = get_config(args.preset)
    
    # 커스텀 설정
    if args.target:
        config['target_profit'] = args.target
    if args.stoploss:
        config['stop_loss'] = args.stoploss
    
    if args.live:
        config['trade_amount'] = args.amount
        config['check_interval'] = args.interval
    
    # 설정 출력
    print_config(config)
    print()
    
    # 실행
    if args.backtest:
        run_backtest(args, config)
    else:
        run_live(args, config)


if __name__ == "__main__":
    main()