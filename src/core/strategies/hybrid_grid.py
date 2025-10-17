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

    def check_breakout_entry(self, market_data: Dict, df: pd.DataFrame, mode: MarketMode) -> Tuple[bool, str, str]:
        """
        Breakout 진입 조건 체크

        조건:
        - TREND 모드
        - 표준편차 급증 (volatility spike)
        - EMA 정배열(Long) 또는 역배열(Short)

        Args:
            market_data: 시장 데이터
            df: OHLC 데이터프레임
            mode: 현재 마켓 모드

        Returns:
            (진입 가능 여부, 방향 ('long' or 'short'), 사유)
        """
        if not self.breakout_enabled:
            return False, None, "Breakout 전략 비활성화"

        if mode != MarketMode.TREND:
            return False, None, f"모드 불일치 ({mode.value})"

        current_price = market_data['current_price']

        # 1. 변동성 급증 체크 (표준편차)
        current_std, mean_std = self.calculate_rolling_std(df['close'], period=self.std_period)

        if current_std <= mean_std * self.volatility_spike_threshold:
            return False, None, f"변동성 급증 없음 (std: {current_std:.2f} < {mean_std * self.volatility_spike_threshold:.2f})"

        # 2. EMA 배열 체크 (추세 방향 확인)
        ema_slopes = []
        for period in self.ema_periods:
            slope = self.calculate_ema_slope(df['close'], period=period, lookback=5)
            ema_slopes.append(slope)

        avg_slope = sum(ema_slopes) / len(ema_slopes) if ema_slopes else 0

        # Long: 상승 추세 (EMA 정배열)
        if avg_slope > self.ema_slope_threshold:
            return True, 'long', f"Breakout Long (변동성: {current_std:.2f}, EMA slope: {avg_slope:+.2f}%)"

        # Short: 하락 추세 (EMA 역배열)
        elif avg_slope < -self.ema_slope_threshold:
            return True, 'short', f"Breakout Short (변동성: {current_std:.2f}, EMA slope: {avg_slope:+.2f}%)"

        else:
            return False, None, f"추세 불명확 (EMA slope: {avg_slope:+.2f}%)"

    def check_breakout_exit(self, position: Dict, market_data: Dict, holding_minutes: float) -> Tuple[bool, str, str]:
        """
        Breakout 청산 조건 체크

        - Long: ATR * 1.5 트레일링 스탑 (여유)
        - Short: ATR * 0.5 빠른 손절 (공격적)

        Args:
            position: 포지션 정보
                - entry_price: 진입가
                - direction: 'long' or 'short'
                - highest_price: 최고가 (Long 트레일링용)
                - lowest_price: 최저가 (Short 트레일링용)
            market_data: 현재 시장 데이터
            holding_minutes: 보유 시간 (분)

        Returns:
            (청산 여부, 청산 유형, 사유)
        """
        current_price = market_data['current_price']
        entry_price = position['entry_price']
        direction = position.get('direction', 'long')
        atr = market_data.get('atr', 0)

        profit_rate = (current_price - entry_price) / entry_price * 100

        # Long 포지션
        if direction == 'long':
            # 최고가 업데이트
            highest_price = position.get('highest_price', entry_price)
            if current_price > highest_price:
                position['highest_price'] = current_price
                highest_price = current_price

            # 트레일링 스탑 (ATR * 1.5)
            if atr > 0:
                stop_price = highest_price - (atr * self.trailing_stop_atr_multiple_long)
                if current_price <= stop_price:
                    return True, 'TAKE_PROFIT', f"Long 트레일링 스탑 ({profit_rate:+.2f}%)"

            # 기본 손절 (-2%)
            if profit_rate <= -2.0:
                return True, 'STOP_LOSS', f"Long 손절 ({profit_rate:+.2f}%)"

        # Short 포지션
        elif direction == 'short':
            # 최저가 업데이트
            lowest_price = position.get('lowest_price', entry_price)
            if current_price < lowest_price:
                position['lowest_price'] = current_price
                lowest_price = current_price

            # 빠른 손절 (ATR * 0.5)
            if atr > 0:
                stop_price = lowest_price + (atr * self.trailing_stop_atr_multiple_short)
                if current_price >= stop_price:
                    return True, 'STOP_LOSS', f"Short 손절 ({profit_rate:+.2f}%)"

            # 기본 익절 (+2%)
            if profit_rate >= 2.0:
                return True, 'TAKE_PROFIT', f"Short 익절 ({profit_rate:+.2f}%)"

        return False, None, None

    def check_entry_conditions(self, market_data: Dict, df: pd.DataFrame = None) -> Tuple[bool, str]:
        """
        매수 조건 체크 (오버라이드)

        모드에 따라 Grid 또는 Breakout 로직 선택

        Args:
            market_data: 시장 데이터
            df: OHLC 데이터프레임 (모드 판단용)

        Returns:
            (진입 가능 여부, 사유)
        """
        # 데이터프레임이 없으면 Grid 모드로 폴백
        if df is None or len(df) < max(self.adx_period, max(self.ema_periods), self.std_period):
            return super().check_entry_conditions(market_data)

        # 마켓 모드 판단
        mode = self.determine_market_mode(market_data, df)
        self.current_mode = mode

        # RANGE/NEUTRAL 모드: Grid Trading
        if mode in [MarketMode.RANGE, MarketMode.NEUTRAL]:
            can_enter, reason = super().check_entry_conditions(market_data)
            if can_enter:
                # sub_strategy 태그 추가를 위해 market_data에 저장
                market_data['sub_strategy'] = 'grid'
            return can_enter, f"[{mode.value.upper()}] {reason}"

        # TREND 모드: Breakout Trading
        elif mode == MarketMode.TREND:
            can_enter, direction, reason = self.check_breakout_entry(market_data, df, mode)
            if can_enter:
                # sub_strategy와 direction 태그 추가
                market_data['sub_strategy'] = 'breakout'
                market_data['direction'] = direction
            return can_enter, f"[{mode.value.upper()}] {reason}"

        return False, f"알 수 없는 모드: {mode}"

    def check_exit_conditions(self, position: Dict, market_data: Dict,
                              holding_minutes: float) -> Tuple[bool, str, str]:
        """
        매도 조건 체크 (오버라이드)

        포지션의 sub_strategy에 따라 분기

        Args:
            position: 포지션 정보
                - sub_strategy: 'grid' or 'breakout'
            market_data: 현재 시장 데이터
            holding_minutes: 보유 시간 (분)

        Returns:
            (청산 여부, 청산 유형, 사유)
        """
        sub_strategy = position.get('sub_strategy', 'grid')

        # Grid 포지션
        if sub_strategy == 'grid':
            return super().check_exit_conditions(position, market_data, holding_minutes)

        # Breakout 포지션
        elif sub_strategy == 'breakout':
            return self.check_breakout_exit(position, market_data, holding_minutes)

        # 기본 폴백 (Grid)
        else:
            return super().check_exit_conditions(position, market_data, holding_minutes)
