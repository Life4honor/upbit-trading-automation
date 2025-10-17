"""
변동성 적응형 Hybrid Grid Trading 전략

Grid Trading + Breakout Trading을 결합한 하이브리드 전략
- Range 모드: Grid Trading (횡보장)
- Trend 모드: Breakout Trading (추세장)
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, List
from datetime import datetime
from enum import Enum

from .grid_trading import GridTradingStrategy


class MarketMode(Enum):
    """마켓 모드 구분"""
    RANGE = "range"      # 횡보장 (Grid Trading)
    TREND = "trend"      # 추세장 (Breakout Trading)
    NEUTRAL = "neutral"  # 중립 (상황에 따라 선택)


class HybridGridStrategy(GridTradingStrategy):
    """
    변동성 적응형 Hybrid Grid Trading 전략

    특징:
    - ADX + EMA slope 기반 마켓 모드 자동 판단
    - Range 모드: Grid Trading (부모 클래스)
    - Trend 모드: Breakout Sub-strategy
    - 동적 포지션 사이징 (ATR 기반)
    - 하이브리드 부분 익절 + 트레일링 스탑
    """

    def __init__(self, config: Dict):
        """
        초기화

        Args:
            config: 전략 설정
        """
        super().__init__(config)

        # 추세 필터 설정
        trend_config = config.get('trend_filter', {})
        self.adx_period = trend_config.get('adx_period', 14)
        self.adx_trend_threshold = trend_config.get('adx_trend_threshold', 25)
        self.adx_range_threshold = trend_config.get('adx_range_threshold', 20)
        self.ema_periods = trend_config.get('ema_periods', [20, 50])
        self.ema_slope_threshold = trend_config.get('ema_slope_threshold', 0.5)

        # 변동성 필터 설정
        vol_config = config.get('volatility_filter', {})
        self.volatility_spike_threshold = vol_config.get('volatility_spike_threshold', 1.5)
        self.atr_increase_threshold = vol_config.get('atr_increase_threshold', 1.0)

        # Breakout 설정
        breakout_config = config.get('breakout', {})
        self.breakout_enabled = breakout_config.get('enabled', True)
        self.breakout_position_fraction = breakout_config.get('position_fraction', 0.33)
        self.trailing_stop_atr_multiple_long = breakout_config.get('trailing_stop_atr_multiple_long', 1.5)
        self.trailing_stop_atr_multiple_short = breakout_config.get('trailing_stop_atr_multiple_short', 0.5)
        self.std_period = breakout_config.get('std_period', 50)

        # 부분 익절 설정
        partial_config = config.get('partial_exit', {})
        self.partial_exit_enabled = partial_config.get('enabled', True)
        self.first_exit_pct = partial_config.get('first_exit_pct', 0.5)  # 50% 익절
        self.profit_target_grid_levels = partial_config.get('profit_target_grid_levels', 1)
        self.min_profit_target_pct = partial_config.get('min_profit_target_pct', 0.5)
        self.max_profit_target_pct = partial_config.get('max_profit_target_pct', 1.5)
        self.trailing_stop_atr_multiple = partial_config.get('trailing_stop_atr_multiple', 1.0)

        # 현재 마켓 모드
        self.current_mode = MarketMode.NEUTRAL

    def determine_market_mode(self, market_data: Dict, df: pd.DataFrame) -> MarketMode:
        """
        마켓 모드 판단 (ADX + EMA slope)

        Args:
            market_data: 현재 시장 데이터
            df: OHLC 데이터프레임 (ADX 계산용)

        Returns:
            MarketMode (RANGE, TREND, NEUTRAL)
        """
        # ADX 계산
        adx = self.calculate_adx(df, period=self.adx_period)

        # EMA slope 계산 (여러 기간의 평균)
        ema_slopes = []
        for period in self.ema_periods:
            slope = self.calculate_ema_slope(df['close'], period=period, lookback=5)
            ema_slopes.append(slope)

        avg_ema_slope = sum(ema_slopes) / len(ema_slopes) if ema_slopes else 0

        # 모드 판단
        # TREND: ADX > 25 AND abs(EMA slope) > 0.5
        if adx > self.adx_trend_threshold and abs(avg_ema_slope) > self.ema_slope_threshold:
            return MarketMode.TREND

        # RANGE: ADX < 20
        elif adx < self.adx_range_threshold:
            return MarketMode.RANGE

        # NEUTRAL: 그 외
        else:
            return MarketMode.NEUTRAL
