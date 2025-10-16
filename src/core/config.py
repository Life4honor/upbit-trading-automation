"""
백테스트 설정 관리
"""

from typing import Dict


def get_default_config() -> Dict:
    """
    그리드 트레이딩 전략 (기본값)

    특징:
    - 횡보장 구간 수익
    - 높은 승률 (92%+)
    - 안정적 수익
    - 장기 보유 전략
    """
    return {
        'strategy_type': 'grid_trading',
        'initial_capital': 1_000_000,

        # 그리드 파라미터
        'grid_levels': 5,  # 5개 그리드
        'grid_spacing': 1.0,  # 1% 간격
        'max_positions': 3,  # 최대 3개 동시 보유

        # 변동성 조건
        'atr_period': 14,
        'max_atr_threshold': 0.8,  # ATR < 평균의 80%

        # 청산 조건
        'single_grid_profit': 1.0,  # 개별 그리드 +1%
        'total_stop_loss': -3.0,  # 전체 손실 -3%
        'long_hold_minutes': 0,  # 장기 보유 손절 비활성화
        'long_hold_loss_threshold': -1.0,
        'fee_rate': 0.05,

        # 그리드 재초기화
        'grid_reset_hours': 24,  # 24시간마다 재초기화
        'bb_period': 20,  # 볼린저 밴드 기간
        'bb_std': 2.0,
        'bb_width_change_threshold': 30.0,  # BB 폭 30% 변화 시 재초기화

        # 기타
        'cooldown_minutes': 0,
        'max_trades_per_day': None,  # 무제한
    }



def print_config(config: Dict):
    """설정 출력 (전략별 동적 출력)"""
    strategy_type = config.get('strategy_type', 'scalping')

    # 전략명 매핑
    strategy_names = {
        'scalping': 'RSI 스캘핑',
        'momentum_breakout': '모멘텀 브레이크아웃',
        'grid_trading': '그리드 트레이딩',
        'volatility_breakout': '변동성 브레이크아웃',
        'bollinger_reversal': '볼린저밴드 리버설',
    }
    strategy_name = strategy_names.get(strategy_type, strategy_type)

    print(f"⚙️ 전략: {strategy_name}")
    print("=" * 40)
    print(f"초기 자본: ₩{config['initial_capital']:,}")

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

    if strategy_type == 'scalping':
        # RSI 스캘핑 전용
        if 'rsi_5m_min' in config:
            print(f"  RSI 5분: {config['rsi_5m_min']}-{config['rsi_5m_max']}")
        if 'rsi_15m_min' in config:
            print(f"  RSI 15분: {config['rsi_15m_min']}-{config['rsi_15m_max']}")
        if 'rsi_1h_min' in config:
            print(f"  RSI 1시간: {config['rsi_1h_min']}-{config['rsi_1h_max']}")
        if 'volume_surge_ratio' in config:
            print(f"  거래량 배율: {config['volume_surge_ratio']}x")
        if 'bid_ask_ratio_min' in config:
            print(f"  호가 비율: {config['bid_ask_ratio_min']}+")

    elif strategy_type == 'momentum_breakout':
        print(f"  고점 기간: {config.get('lookback_period', 20)}일")
        print(f"  거래량 임계값: {config.get('volume_threshold', 1.5)}x")
        print(f"  RSI 최소: {config.get('rsi_min', 50)}")
        print(f"  트레일링 스톱: -{config.get('trailing_stop_pct', 2.0)}%")

    elif strategy_type == 'grid_trading':
        print(f"  그리드 레벨: {config.get('grid_levels', 5)}개")
        print(f"  그리드 간격: {config.get('grid_spacing', 1.0)}%")
        print(f"  최대 포지션: {config.get('max_positions', 3)}개")
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


def get_momentum_breakout_config() -> Dict:
    """
    모멘텀 브레이크아웃 전략

    특징:
    - 고점 돌파 + 거래량 급증
    - 강한 추세 포착
    - 중간 승률, 큰 수익
    """
    return {
        'strategy_type': 'momentum_breakout',
        'initial_capital': 1_000_000,

        # 청산 조건
        'target_profit': 3.0,  # +3%
        'stop_loss': -1.5,  # -1.5%
        'fee_rate': 0.05,

        # 브레이크아웃 파라미터
        'lookback_period': 20,  # 20일 고점
        'volume_threshold': 1.5,  # 거래량 1.5배
        'rsi_min': 50,  # RSI > 50

        # MACD
        'macd_fast': 12,
        'macd_slow': 26,
        'macd_signal': 9,

        # 트레일링 스톱
        'trailing_stop_pct': 2.0,  # 고점 대비 -2%

        # 기타
        'cooldown_minutes': 5,
        'max_trades_per_day': 10,
    }


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
        'initial_capital': 1_000_000,

        # 그리드 파라미터
        'grid_levels': 5,  # 5개 그리드
        'grid_spacing': 1.0,  # 1% 간격
        'max_positions': 3,  # 최대 3개 동시 보유

        # 변동성 조건
        'atr_period': 14,
        'max_atr_threshold': 0.8,  # ATR < 평균의 80%

        # 청산 조건
        'single_grid_profit': 1.0,  # 개별 그리드 +1%
        'total_stop_loss': -3.0,  # 전체 손실 -3%
        'fee_rate': 0.05,

        # 기타
        'cooldown_minutes': 0,
        'max_trades_per_day': None,  # 무제한
    }


def get_volatility_breakout_config() -> Dict:
    """
    변동성 브레이크아웃 전략

    특징:
    - ATR 급증 포착
    - 고위험 고수익
    - 낮은 거래 빈도
    """
    return {
        'strategy_type': 'volatility_breakout',
        'initial_capital': 1_000_000,

        # ATR 파라미터
        'atr_period': 14,
        'atr_multiplier': 1.5,  # ATR > 평균의 1.5배
        'breakout_atr_factor': 0.5,  # 전일 고점 + ATR*0.5

        # 청산 조건 (동적 ATR 기반)
        'target_atr_multiple': 2.0,  # 익절: ATR * 2
        'stop_atr_multiple': 1.0,  # 손절: ATR * 1
        'fee_rate': 0.05,

        # 거래량
        'volume_threshold': 1.2,

        # 최소 변동성
        'min_atr_krw': 10000,  # 최소 ATR 10,000원

        # 기타
        'cooldown_minutes': 10,
        'max_trades_per_day': 5,
    }


def get_bollinger_reversal_config() -> Dict:
    """
    볼린저밴드 리버설 전략 (평균회귀)

    특징:
    - BB 하단 반등 포착
    - 높은 승률
    - 빠른 진입/청산
    """
    return {
        'strategy_type': 'bollinger_reversal',
        'initial_capital': 1_000_000,

        # 볼린저밴드
        'bb_period': 20,
        'bb_std': 2.0,
        'bb_width_min': 2.0,  # 최소 변동성

        # 진입 조건
        'rsi_period': 14,
        'rsi_oversold': 30,  # RSI < 30
        'volume_threshold': 1.2,
        'require_reversal_candle': True,  # 양봉 필수

        # 청산 조건
        'target_bb_position': 0.5,  # BB 중심선
        'target_profit_pct': 2.0,  # 또는 +2%
        'stop_loss_pct': -1.5,  # -1.5%
        'time_stop_minutes': 60,  # 60분 시간 손절
        'rsi_overbought': 70,  # RSI > 70 익절
        'fee_rate': 0.05,

        # 기타
        'cooldown_minutes': 5,
        'max_trades_per_day': 15,
    }


# 프리셋 맵핑
PRESETS = {
    # 기존 RSI 스캘핑
    'default': get_default_config,

    # 새로운 전략들
    'momentum-breakout': get_momentum_breakout_config,
    'grid-trading': get_grid_trading_config,
    'volatility-breakout': get_volatility_breakout_config,
    'bollinger-reversal': get_bollinger_reversal_config,
}


def get_config(preset: str = 'default') -> Dict:
    """
    프리셋으로 설정 가져오기
    
    Args:
        preset: 'default'
    
    Returns:
        설정 딕셔너리
    """
    if preset not in PRESETS:
        print(f"⚠️ 알 수 없는 프리셋: {preset}, default 사용")
        preset = 'default'
    
    return PRESETS[preset]()