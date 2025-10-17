"""
백테스트 설정 관리
"""

from typing import Dict


def print_config(config: Dict):
    """설정 출력 (전략별 동적 출력)"""
    strategy_type = config.get('strategy_type', 'hybrid_grid')

    # 전략명 매핑
    strategy_names = {
        'hybrid_grid': '🚀 변동성 적응형 Hybrid Grid Trading',
        'grid_trading': '📊 그리드 트레이딩 (레거시)',
    }
    strategy_name = strategy_names.get(strategy_type, strategy_type)

    print(f"⚙️  전략: {strategy_name}")
    print("=" * 60)

    # Hybrid Grid 구조화된 설정 출력
    if strategy_type == 'hybrid_grid':
        # Grid 설정
        grid = config.get('grid', {})
        print(f"\n📊 Grid 설정:")
        print(f"  레벨: {grid.get('levels', 5)}개")
        print(f"  ATR spacing 계수(k): {grid.get('atr_spacing_k', 2.0)}")
        print(f"  Spacing 범위: {grid.get('min_grid_spacing', 0.3)}% ~ {grid.get('max_grid_spacing', 2.0)}%")
        print(f"  최대 포지션: {grid.get('max_positions', 3)}개")

        # 리스크 관리
        risk = config.get('risk', {})
        print(f"\n⚠️  리스크 관리:")
        print(f"  거래당 리스크: {risk.get('risk_per_trade', 0.01)*100:.1f}%")
        print(f"  ATR 손절 배수: {risk.get('atr_stop_multiple', 2.0)}")
        print(f"  개별 손절: {risk.get('single_position_stop_loss', -0.5)}%")
        print(f"  수수료: {risk.get('fee_rate', 0.05)}%")
        print(f"  슬리피지: {risk.get('slippage_pct', 0.05)}%")

        # 변동성 필터
        vol = config.get('volatility_filter', {})
        print(f"\n📈 변동성 필터:")
        print(f"  ATR 기간: {vol.get('atr_period', 12)}")
        print(f"  Grid 모드 임계값: ATR < 평균*{vol.get('max_atr_threshold', 0.8)}")
        print(f"  Breakout 감지: 표준편차 {vol.get('volatility_spike_threshold', 1.5)}x")

        # 추세 필터
        trend = config.get('trend_filter', {})
        print(f"\n🎯 추세 필터 (모드 전환):")
        print(f"  ADX 기간: {trend.get('adx_period', 14)}")
        print(f"  Trend 모드: ADX > {trend.get('adx_trend_threshold', 25)}")
        print(f"  Range 모드: ADX < {trend.get('adx_range_threshold', 20)}")
        print(f"  EMA 기간: {trend.get('ema_periods', [20, 50])}")

        # Breakout Sub-strategy
        breakout = config.get('breakout', {})
        if breakout.get('enabled', True):
            print(f"\n💥 Breakout Sub-strategy:")
            print(f"  포지션 비율: {breakout.get('position_fraction', 0.33)*100:.0f}%")
            print(f"  Long 트레일링: ATR * {breakout.get('trailing_stop_atr_multiple_long', 1.5)}")
            print(f"  Short 손절: ATR * {breakout.get('trailing_stop_atr_multiple_short', 0.5)}")

        # 부분 익절
        partial = config.get('partial_exit', {})
        if partial.get('enabled', True):
            print(f"\n💰 하이브리드 부분 익절:")
            print(f"  1차 익절: {partial.get('first_exit_pct', 0.5)*100:.0f}%")
            print(f"  목표: 그리드 {partial.get('profit_target_grid_levels', 1)}레벨")
            print(f"  범위: {partial.get('min_profit_target_pct', 0.5)}% ~ {partial.get('max_profit_target_pct', 1.5)}%")
            print(f"  나머지 트레일링: ATR * {partial.get('trailing_stop_atr_multiple', 1.0)}")

        # 실행 설정
        execution = config.get('execution', {})
        print(f"\n⚙️  실행 설정:")
        print(f"  쿨다운: {execution.get('cooldown_minutes', 3)}분")
        max_trades = execution.get('max_trades_per_day')
        print(f"  일일 최대 거래: {'무제한' if max_trades is None else f'{max_trades}회'}")

    # 레거시 grid_trading 출력
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


    print("=" * 60)


def get_hybrid_grid_config() -> Dict:
    """
    변동성 적응형 Hybrid Grid Trading 전략

    특징:
    - ATR 기반 동적 그리드 간격
    - Risk 기반 포지션 사이징
    - Grid/Trend 모드 자동 전환
    - Breakout Sub-strategy
    - 하이브리드 부분 익절 + 트레일링 스탑
    """
    return {
        'strategy_type': 'hybrid_grid',

        # Grid 설정
        'grid': {
            'levels': 5,                    # 그리드 레벨 개수
            'atr_spacing_k': 2.0,           # ATR 기반 spacing 계수
            'min_grid_spacing': 0.3,        # 최소 간격 (%)
            'max_grid_spacing': 2.0,        # 최대 간격 (%)
            'max_positions': 3,             # 최대 동시 포지션
        },

        # 리스크 관리
        'risk': {
            'risk_per_trade': 0.01,         # 거래당 리스크 (1%)
            'atr_stop_multiple': 2.0,       # ATR 손절 배수
            'total_stop_loss': 0,           # 전체 손절 (0=비활성화)
            'single_position_stop_loss': -0.5,  # 개별 손절 (%)
            'fee_rate': 0.05,               # 수수료 (%)
            'slippage_pct': 0.05,           # 슬리피지 (%)
        },

        # 변동성 필터
        'volatility_filter': {
            'atr_period': 12,               # ATR 계산 기간
            'max_atr_threshold': 0.8,       # Grid 모드용 (ATR < 평균*0.8)
            'volatility_spike_threshold': 1.5,  # Breakout 감지용 (표준편차)
            'atr_increase_threshold': 1.0,  # ATR 증가율 100%
        },

        # 추세 필터
        'trend_filter': {
            'adx_period': 14,               # ADX 계산 기간
            'adx_trend_threshold': 25,      # ADX > 25 = Trend
            'adx_range_threshold': 20,      # ADX < 20 = Range
            'ema_periods': [20, 50],        # EMA slope 계산용
            'ema_slope_threshold': 0.5,     # EMA slope 강도
        },

        # 그리드 리셋 정책
        'reset_policy': {
            'price_deviation_atr_multiple': 3.0,  # N*ATR 이탈 시 리셋
            'reset_cooldown_hours': 1.0,    # 리셋 후 쿨다운
            'bb_period': 20,                # 볼린저 밴드 기간
            'bb_std': 2.0,                  # 볼린저 밴드 표준편차
            'bb_width_change_threshold': 50.0,  # BB 폭 변화율 (%)
        },

        # BB 진입 필터
        'bb_entry_filter': {
            'enabled': True,                # BB 필터 사용
            'max_position_pct': 0.4,        # 하단 40% 이내
            'bb_width_narrow': 4.0,         # 좁은 밴드폭 기준 (%)
            'bb_width_wide': 8.0,           # 넓은 밴드폭 기준 (%)
        },

        # Breakout Sub-strategy
        'breakout': {
            'enabled': True,                # Breakout 전략 사용
            'position_fraction': 0.33,      # 1/3 포지션
            'trailing_stop_atr_multiple_long': 1.5,   # Long 트레일링
            'trailing_stop_atr_multiple_short': 0.5,  # Short 빠른 손절
            'std_period': 50,               # 표준편차 계산 기간
        },

        # 부분 익절 (하이브리드)
        'partial_exit': {
            'enabled': True,                # 부분 익절 사용
            'first_exit_pct': 0.5,          # 50% 익절
            'profit_target_grid_levels': 1, # 그리드 레벨 기준
            'min_profit_target_pct': 0.5,   # 최소 수익률
            'max_profit_target_pct': 1.5,   # 최대 수익률
            'trailing_stop_atr_multiple': 1.0,  # 나머지 트레일링
        },

        # 실행 설정
        'execution': {
            'cooldown_minutes': 3,          # 거래 후 쿨다운
            'max_trades_per_day': None,     # 일일 최대 거래 (None=무제한)
            'legacy_position_handling': 'ask',  # 기존 포지션 처리 ('ask', 'integrate', 'liquidate')
            'legacy_position_auto_choice': 1,   # ask 시 Enter 기본값 (1=통합, 2=청산)
        },
    }


def get_grid_trading_config() -> Dict:
    """
    기존 그리드 트레이딩 전략 (하위 호환성)

    Note: 새로운 프로젝트는 get_hybrid_grid_config() 사용 권장
    """
    return {
        'strategy_type': 'grid_trading',

        # 그리드 파라미터
        'grid_levels': 5,
        'grid_spacing': 0.7,
        'max_positions': 3,

        # 변동성 조건
        'atr_period': 12,
        'max_atr_threshold': 0.8,

        # 청산 조건
        'single_position_stop_loss': -0.5,
        'single_grid_profit': 0.7,
        'total_stop_loss': 0,
        'long_hold_minutes': 0,
        'long_hold_loss_threshold': -1.0,
        'fee_rate': 0.05,

        # 그리드 재초기화
        'grid_reset_hours': 1,
        'bb_period': 20,
        'bb_std': 2.0,
        'bb_width_change_threshold': 30.0,

        # 볼린저 밴드 매수 필터
        'use_bb_entry_filter': True,
        'bb_entry_position_max': 0.2,
        'bb_width_multiplier_narrow': 1.0,
        'bb_width_multiplier_wide': 1.5,

        # 기타
        'cooldown_minutes': 3,
        'max_trades_per_day': None,
    }


# 프리셋 맵핑
PRESETS = {
    'hybrid-grid': get_hybrid_grid_config,
    'grid-trading': get_grid_trading_config,  # 하위 호환성
}


def get_config(preset: str = 'hybrid-grid') -> Dict:
    """
    프리셋으로 설정 가져오기

    Args:
        preset: 'hybrid-grid' (기본) 또는 'grid-trading' (레거시)

    Returns:
        설정 딕셔너리
    """
    if preset not in PRESETS:
        print(f"⚠️ 알 수 없는 프리셋: {preset}, hybrid-grid 사용")
        preset = 'hybrid-grid'

    return PRESETS[preset]()