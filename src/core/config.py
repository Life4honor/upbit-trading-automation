"""
백테스트 설정 관리
"""

from typing import Dict


def get_default_config() -> Dict:
    return {
        'initial_capital': 1_000_000,
        'target_profit': 0.5,  # 목표 수익률
        'stop_loss': -0.45,  # 손절 기준 (완화)
        'max_trades_per_day': None,  # None = 무제한
        'fee_rate': 0.05,

        # RSI 조건 (범위 완화)
        'rsi_5m_min': 60,
        'rsi_5m_max': 85,
        'rsi_15m_min': 50,
        'rsi_15m_max': 87,
        'rsi_1h_min': 45,
        'rsi_1h_max': 90,

        # 이동평균선 조건
        'use_sma_alignment': True,  # 정배열 체크
        'sma_periods': [7, 25],  # SMA 7, 25 사용

        # 볼린저 밴드 조건
        'use_bollinger': False,

        # 거래량 조건 (완화)
        'volume_surge_ratio': 1.00,
        'min_volume_krw': 2_000_000,  # 200만
        'volume_1h_increasing': True,

        # 호가 조건 (완화)
        'bid_ask_ratio_min': 1.2,      # 1.2
        'bid_ask_imbalance_min': 0.6,  # 매수 호가 60% 이상

        # 기타
        'cooldown_minutes': 5,
        'strong_rsi_threshold': 70,  # 75 → 70 (거래량 체크 스킵 조건 완화)

        # 동적 목표 수익률
        'use_dynamic_target': True,  # 동적 목표 수익률 활성화
        'dynamic_target_min': 0.25,  # 최소 목표 수익률
        'dynamic_target_max': 1.00,  # 최대 목표 수익률

        # 시간대 필터 (거래량 분석 결과 기반)
        'use_time_filter': True,  # 시간대 필터 사용 여부 (기본: 비활성화)
        'time_filter_mode': 'safe',  # optimal/safe/peak/custom
        'exclude_weekdays': [],  # 제외할 요일 (0=월, 4=금, 6=일)
        'preferred_weekdays': None,  # 선호 요일 (None=모든 요일)
        'allowed_hours': list(range(24)),  # custom 모드용 허용 시간
    }



def print_config(config: Dict):
    """설정 출력"""
    print("⚙️ 백테스트 설정")
    print("=" * 40)
    print(f"초기 자본: ₩{config['initial_capital']:,}")
    print(f"목표 수익: +{config['target_profit']}%")
    print(f"손절: {config['stop_loss']}%")
    max_trades = config['max_trades_per_day']
    print(f"일 최대 거래: {'무제한' if max_trades is None else f'{max_trades}회'}")
    print(f"수수료: {config['fee_rate']}%")
    print(f"RSI 5분: {config['rsi_5m_min']}-{config['rsi_5m_max']}")
    print(f"RSI 15분: {config['rsi_15m_min']}-{config['rsi_15m_max']}")
    print(f"RSI 1시간: {config['rsi_1h_min']}-{config['rsi_1h_max']}")
    cooldown = config['cooldown_minutes']
    if cooldown == 0:
        print(f"쿨타임: 없음 (즉시 재진입)")
    elif cooldown >= 1:
        print(f"쿨타임: {cooldown}분")
    else:
        print(f"쿨타임: {int(cooldown * 60)}초")
    print(f"거래량 배율: {config.get('volume_surge_ratio', 'N/A')}x")
    print(f"호가 비율: {config.get('bid_ask_ratio_min', 'N/A')}+")
    bid_imbalance = config.get('bid_ask_imbalance_min', None)
    if bid_imbalance:
        print(f"호가 불균형: {bid_imbalance:.1%}+ (매수 호가 비중)")
    print("=" * 40)


def get_optimal_time_config() -> Dict:
    """
    최적 시간대 전략 설정 (거래량 분석 결과 기반)

    시간대 필터 활성화:
    - 오전 6-12시 (아시아 피크)
    - 밤 11시-새벽 2시 (미국 마감 + 아시아 시작)
    - 토요일 우선 (거래량 2배)
    - 금요일 제외 (거래량 최저)
    """
    config = get_default_config()
    config.update({
        'use_time_filter': True,
        'time_filter_mode': 'optimal',  # 6-12시, 23-02시
        'exclude_weekdays': [4],  # 금요일 제외 (거래량 60% 수준)
        'preferred_weekdays': None,  # 모든 요일 (금요일 제외)
    })
    return config


def get_weekend_warrior_config() -> Dict:
    """
    주말 전용 전략 설정

    토요일/일요일만 거래:
    - 거래량: 평균 대비 190%
    - 변동성 증가로 수익 기회 증가
    - 직장인 최적 전략
    """
    config = get_default_config()
    config.update({
        'use_time_filter': True,
        'time_filter_mode': 'optimal',
        'preferred_weekdays': [5, 6],  # 토요일, 일요일만
    })
    return config


def get_safe_hours_config() -> Dict:
    """
    안전 시간대 전략

    저거래량 시간 제외:
    - 새벽 3-5시 제외 (거래량 40-50%)
    - 오후 2-3시 제외 (점심 후 저조)
    - 저녁 7-9시 제외 (저녁 시간)
    """
    config = get_default_config()
    config.update({
        'use_time_filter': True,
        'time_filter_mode': 'safe',  # 저거래량 시간만 제외
    })
    return config


def get_peak_only_config() -> Dict:
    """
    피크 시간 전용 전략 (공격적)

    최고 거래량 시간만:
    - 오전 6-9시 (아침 피크)
    - 자정-새벽 1시 (야간 피크)
    - 가장 적은 거래 빈도
    - 가장 높은 성공률 기대
    """
    config = get_default_config()
    config.update({
        'use_time_filter': True,
        'time_filter_mode': 'peak',
        'exclude_weekdays': [4],  # 금요일 제외
    })
    return config


# 프리셋 맵핑
PRESETS = {
    'default': get_default_config,
    'optimal-time': get_optimal_time_config,
    'weekend': get_weekend_warrior_config,
    'safe-hours': get_safe_hours_config,
    'peak-only': get_peak_only_config,
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