"""
백테스트 설정 관리
"""

from typing import Dict


def print_config(config: Dict):
    """설정 출력 (전략별 동적 출력)"""
    strategy_type = config.get('strategy_type', 'grit-trading')

    # 전략명 매핑
    strategy_names = {
        'grid_trading': '그리드 트레이딩',
        'momentum_breakout': '모멘텀 브레이크아웃',
        'volatility_breakout': '변동성 브레이크아웃',
        'bollinger_reversal': '볼린저밴드 리버설',
    }
    strategy_name = strategy_names.get(strategy_type, strategy_type)

    print(f"⚙️ 전략: {strategy_name}")
    print("=" * 40)

    # 공통 파라미터
    if 'target_profit' in config:
        print(f"목표 수익: +{config['target_profit']}%")
    if 'stop_loss' in config:
        print(f"손절: {config['stop_loss']}%")

    max_trades = config.get('max_trades_per_day')
    if max_trades is not None:
        print(f"일 최대 거래: {'무제한' if max_trades is None else f'{max_trades}회'}")

    print(f"수수료: {config.get('fee_rate', 0.05)}%")

    # 전략별 주요 파라미터
    print("\n주요 파라미터:")

    if strategy_type == 'momentum_breakout':
        print(f"  고점 기간: {config.get('lookback_period', 20)}일")
        print(f"  거래량 임계값: {config.get('volume_threshold', 1.5)}x")
        print(f"  RSI 최소: {config.get('rsi_min', 50)}")
        print(f"  트레일링 스톱: -{config.get('trailing_stop_pct', 2.0)}%")

    elif strategy_type == 'grid_trading':
        print(f"  그리드 레벨: {config.get('grid_levels', 5)}개")
        print(f"  그리드 간격: {config.get('grid_spacing', 1.0)}%")
        print(f"  최대 포지션: {config.get('max_positions', 3)}개")
        print(f"  개별 포지션 손절: {config.get('single_position_stop_loss', -1.5)}%")
        print(f"  개별 그리드 익절: +{config.get('single_grid_profit', 1.0)}%")
        print(f"  전체 손절: {config.get('total_stop_loss', -3.0)}%")

        # 장기 보유 손절 설정
        long_hold_minutes = config.get('long_hold_minutes', 0)
        if long_hold_minutes > 0:
            print(f"  장기 보유 손절: {long_hold_minutes}분 (-{abs(config.get('long_hold_loss_threshold', -1.0))}% 이상)")
        else:
            print(f"  장기 보유 손절: 비활성화")

        # 그리드 재초기화 설정
        reset_hours = config.get('grid_reset_hours', 24)
        if reset_hours > 0:
            print(f"  주기적 재초기화: {reset_hours}시간")
        else:
            print(f"  주기적 재초기화: 비활성화")
        print(f"  볼린저 밴드 기간: {config.get('bb_period', 20)}")
        print(f"  BB 폭 변화 임계값: {config.get('bb_width_change_threshold', 30.0)}%")

        # 볼린저 밴드 매수 필터 설정
        use_bb_filter = config.get('use_bb_entry_filter', True)
        if use_bb_filter:
            print(f"  BB 매수 필터: 활성화 (하위 {config.get('bb_entry_position_max', 0.4)*100:.0f}% 이내)")
        else:
            print(f"  BB 매수 필터: 비활성화")

    elif strategy_type == 'volatility_breakout':
        print(f"  ATR 기간: {config.get('atr_period', 14)}")
        print(f"  ATR 배수: {config.get('atr_multiplier', 1.5)}x")
        print(f"  익절 ATR 배수: {config.get('target_atr_multiple', 2.0)}x")
        print(f"  손절 ATR 배수: {config.get('stop_atr_multiple', 1.0)}x")
        print(f"  최소 ATR: ₩{config.get('min_atr_krw', 10000):,}")

    elif strategy_type == 'bollinger_reversal':
        print(f"  BB 기간: {config.get('bb_period', 20)}")
        print(f"  BB 표준편차: {config.get('bb_std', 2.0)}")
        print(f"  RSI 과매도: {config.get('rsi_oversold', 30)}")
        print(f"  RSI 과매수: {config.get('rsi_overbought', 70)}")
        print(f"  시간 손절: {config.get('time_stop_minutes', 60)}분")

    # 쿨타임
    cooldown = config.get('cooldown_minutes', 0)
    if cooldown == 0:
        print(f"  쿨타임: 없음 (즉시 재진입)")
    elif cooldown >= 1:
        print(f"  쿨타임: {cooldown}분")
    else:
        print(f"  쿨타임: {int(cooldown * 60)}초")

    print("=" * 40)


def get_grid_trading_config() -> Dict:
    """
    그리드 트레이딩 전략

    특징:
    - 횡보장 구간 수익
    - 높은 승률
    - 안정적 수익
    """
    return {
        'strategy_type': 'grid_trading',

        # 그리드 파라미터
        'grid_levels': 5,  # 5개 그리드
        'grid_spacing': 0.7,  # 0.7% 간격
        'max_positions': 3,  # 최대 3개 동시 보유

        # 변동성 조건
        'atr_period': 12,
        'max_atr_threshold': 0.8,  # ATR < 평균의 80%

        # 청산 조건
        'single_position_stop_loss': -0.5,  # 개별 포지션 손절 -0.5%
        'single_grid_profit': 0.7,  # 개별 그리드 +0.7%
        'total_stop_loss': 0,  # 전체 손실 -3%
        'long_hold_minutes': 0,  # 장기 보유 손절 비활성화
        'long_hold_loss_threshold': -1.0,
        'fee_rate': 0.05,

        # 그리드 재초기화
        'grid_reset_hours': 1,  # 1시간마다 재초기화
        'bb_period': 20,  # 볼린저 밴드 기간
        'bb_std': 2.0,
        'bb_width_change_threshold': 30.0,  # BB 폭 30% 변화 시 재초기화

        # 볼린저 밴드 매수 필터 (박스권 상단 진입 방지)
        'use_bb_entry_filter': True,  # BB 매수 필터 사용
        'bb_entry_position_max': 0.2,  # BB 하위 30% 이내에서만 매수 (기본)
        'bb_width_multiplier_narrow': 1.0,  # 좁은 밴드폭(< 4%): 40% 이내
        'bb_width_multiplier_wide': 1.5,  # 넓은 밴드폭(> 8%): 60% 이내

        # 기타
        'cooldown_minutes': 3,
        'max_trades_per_day': None,  # 무제한
    }


# 프리셋 맵핑
PRESETS = {
    'grid-trading': get_grid_trading_config,
}


def get_config(preset: str = 'grid-trading') -> Dict:
    """
    프리셋으로 설정 가져오기
    
    Args:
        preset: 'grid-trading'
    
    Returns:
        설정 딕셔너리
    """
    if preset not in PRESETS:
        print(f"⚠️ 알 수 없는 프리셋: {preset}, grid-trading 사용")
        preset = 'grid-trading'
    
    return PRESETS[preset]()