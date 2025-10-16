"""
초단타 스캘핑 전략 (RSI 기반)
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple
from datetime import datetime

from ..base_strategy import BaseStrategy


class ScalpingStrategy(BaseStrategy):
    """
    RSI 기반 초단타 스캘핑 전략
    백테스트와 실거래에서 동일한 로직 사용
    """

    def __init__(self, config: Dict):
        """
        초기화

        Args:
            config: 전략 설정
        """
        super().__init__(config)

        # RSI 조건
        self.rsi_5m_min = config.get('rsi_5m_min', 60)
        self.rsi_5m_max = config.get('rsi_5m_max', 75)
        self.rsi_15m_min = config.get('rsi_15m_min', 50)
        self.rsi_15m_max = config.get('rsi_15m_max', 70)
        self.rsi_1h_min = config.get('rsi_1h_min', 45)
        self.rsi_1h_max = config.get('rsi_1h_max', 80)

        # 동적 목표 수익률
        self.use_dynamic_target = config.get('use_dynamic_target', False)
        self.dynamic_target_min = config.get('dynamic_target_min', 0.30)
        self.dynamic_target_max = config.get('dynamic_target_max', 0.50)

        # 이동평균선 조건
        self.use_sma_alignment = config.get('use_sma_alignment', False)
        self.sma_periods = config.get('sma_periods', [7, 25, 99])

        # 볼린저 밴드 조건
        self.use_bollinger = config.get('use_bollinger', False)
        self.bb_period = config.get('bb_period', 20)
        self.bb_std = config.get('bb_std', 2.0)
        self.bb_position_min = config.get('bb_position_min', 0.1)
        self.bb_position_max = config.get('bb_position_max', 0.8)
        self.bb_width_min = config.get('bb_width_min', 0.0)

        # 거래량/호가 조건
        self.bid_ask_ratio_min = config.get('bid_ask_ratio_min', 1.0)
        self.volume_surge_ratio = config.get('volume_surge_ratio', 1.2)
        self.min_volume_krw = config.get('min_volume_krw', 0)
        self.volume_1h_increasing = config.get('volume_1h_increasing', False)
        self.strong_rsi_threshold = config.get('strong_rsi_threshold', 70)
        self.bid_ask_imbalance_min = config.get('bid_ask_imbalance_min', 0.6)

    def calculate_dynamic_target(self, market_data: Dict) -> float:
        """
        시장 지표 기반 동적 목표 수익률 계산

        계수 기반 계산:
        - RSI 강도: RSI가 높을수록 목표 수익률 상향 (강한 추세)
        - 거래량: 거래량이 많을수록 목표 수익률 상향 (유동성)
        - 호가 불균형: 매수세가 강할수록 목표 수익률 상향

        Args:
            market_data: 시장 데이터

        Returns:
            동적 목표 수익률 (%)
        """
        if not self.use_dynamic_target:
            return self.target_profit

        # 기본 점수 시작 (0.5 = 중간)
        score = 0.5

        # 1. RSI 강도 점수 (0.0 ~ 1.0)
        rsi_5m = market_data.get('rsi_5m', 50)
        if rsi_5m >= 70:  # 강한 상승
            rsi_score = 0.8 + (rsi_5m - 70) / 100
        elif rsi_5m >= 60:  # 중강 상승
            rsi_score = 0.5 + (rsi_5m - 60) / 33
        else:  # 약한 상승
            rsi_score = rsi_5m / 120

        # 2. 거래량 점수 (0.0 ~ 1.0)
        volume_surge = market_data.get('volume_surge_ratio', 1.0)
        if volume_surge >= 2.0:  # 매우 강한 거래량
            volume_score = 1.0
        elif volume_surge >= 1.5:  # 강한 거래량
            volume_score = 0.7 + (volume_surge - 1.5) * 0.6
        elif volume_surge >= 1.2:  # 보통 거래량
            volume_score = 0.4 + (volume_surge - 1.2) * 1.0
        else:  # 약한 거래량
            volume_score = volume_surge / 3

        # 3. 호가 불균형 점수 (0.0 ~ 1.0)
        bid_imbalance = market_data.get('bid_ask_imbalance', 0.5)
        if bid_imbalance >= 0.70:  # 매우 강한 매수세
            imbalance_score = 0.9 + (bid_imbalance - 0.70) * 3.3
        elif bid_imbalance >= 0.62:  # 강한 매수세
            imbalance_score = 0.6 + (bid_imbalance - 0.62) * 3.75
        else:  # 보통 매수세
            imbalance_score = bid_imbalance * 0.97

        # 가중 평균 계산 (RSI 40%, 거래량 30%, 호가 30%)
        score = (rsi_score * 0.4) + (volume_score * 0.3) + (imbalance_score * 0.3)

        # 최종 목표 수익률 계산
        dynamic_target = self.dynamic_target_min + (score * (self.dynamic_target_max - self.dynamic_target_min))

        # 범위 제한
        dynamic_target = max(self.dynamic_target_min, min(self.dynamic_target_max, dynamic_target))

        return round(dynamic_target, 2)

    def check_entry_conditions(self, market_data: Dict) -> Tuple[bool, str]:
        """
        매수 조건 체크

        Args:
            market_data: 시장 데이터

        Returns:
            (진입 가능 여부, 사유)
        """
        price = market_data['current_price']
        candle = market_data['latest_candle']
        rsi_5m = market_data['rsi_5m']

        # 1. RSI 5분 조건
        if not (self.rsi_5m_min <= rsi_5m <= self.rsi_5m_max):
            return False, f"RSI 5m 조건 미충족 ({rsi_5m:.1f})"

        # 2. RSI 15분 조건
        if not (self.rsi_15m_min <= market_data['rsi_15m'] <= self.rsi_15m_max):
            return False, f"RSI 15m 조건 미충족 ({market_data['rsi_15m']:.1f})"

        # 3. RSI 1시간 조건
        if 'rsi_1h' in market_data:
            if not (self.rsi_1h_min <= market_data['rsi_1h'] <= self.rsi_1h_max):
                return False, f"RSI 1h 조건 미충족 ({market_data['rsi_1h']:.1f})"

        # 4. 이동평균 정배열 체크
        if self.use_sma_alignment:
            smas = []
            for period in self.sma_periods:
                key = f'sma_{period}'
                if key in market_data:
                    smas.append(market_data[key])

            if len(smas) >= 2:
                if price <= smas[0]:
                    return False, f"정배열 미충족 (가격: {price:.0f} <= SMA{self.sma_periods[0]}: {smas[0]:.0f})"

                for i in range(len(smas) - 1):
                    if smas[i] <= smas[i + 1]:
                        return False, f"정배열 미충족 (SMA{self.sma_periods[i]}: {smas[i]:.0f} <= SMA{self.sma_periods[i+1]}: {smas[i+1]:.0f})"

        # 5. SMA 7 근접 체크
        if 'sma_7' in market_data:
            if price < market_data['sma_7']:
                return False, f"SMA 7 아래 (가격: {price:.0f} < SMA7: {market_data['sma_7']:.0f})"

            sma_diff = (price - market_data['sma_7']) / market_data['sma_7'] * 100
            if sma_diff > 0.7:
                return False, f"SMA 7 거리 초과 ({sma_diff:.2f}% > 0.7%)"

        # 6. 볼린저 밴드 조건
        if self.use_bollinger and all(k in market_data for k in ['bb_upper', 'bb_middle', 'bb_lower', 'bb_width']):
            bb_upper = market_data['bb_upper']
            bb_lower = market_data['bb_lower']
            bb_width = market_data['bb_width']

            if bb_width < self.bb_width_min:
                return False, f"변동성 부족 (BB Width: {bb_width:.2f}% < {self.bb_width_min}%)"

            if bb_upper > bb_lower:
                bb_position = (price - bb_lower) / (bb_upper - bb_lower)
                if not (self.bb_position_min <= bb_position <= self.bb_position_max):
                    return False, f"BB 위치 조건 미충족 (위치: {bb_position:.2%})"

        # 7. 상승 캔들
        if candle['close'] <= candle['open']:
            return False, "음봉 캔들"

        # 8. 거래량 체크
        skip_volume_check = rsi_5m >= self.strong_rsi_threshold

        if not skip_volume_check:
            if self.min_volume_krw > 0:
                volume_krw = candle['volume'] * candle['close']
                if volume_krw < self.min_volume_krw:
                    return False, f"절대 거래량 부족 (₩{volume_krw:,.0f} < ₩{self.min_volume_krw:,.0f})"

            if 'volume_ma' in market_data and market_data['volume_ma'] > 0:
                volume_ratio = candle['volume'] / market_data['volume_ma']
                if volume_ratio < self.volume_surge_ratio:
                    return False, f"거래량 부족 ({volume_ratio:.2f}x < {self.volume_surge_ratio}x)"

            if self.volume_1h_increasing and 'volume_1h_ma' in market_data:
                if market_data.get('volume_1h_current', 0) < market_data['volume_1h_ma']:
                    return False, "1시간 거래량 감소 추세"

        # 9. 호가 분석
        if 'bid_ask_ratio' in market_data:
            if market_data['bid_ask_ratio'] < self.bid_ask_ratio_min:
                return False, f"매수세 부족 (비율: {market_data['bid_ask_ratio']:.2f})"

        if 'total_bid_size' in market_data and 'total_ask_size' in market_data:
            total_size = market_data['total_bid_size'] + market_data['total_ask_size']
            if total_size > 0:
                bid_weight = market_data['total_bid_size'] / total_size
                if bid_weight < self.bid_ask_imbalance_min:
                    return False, f"호가 불균형 (매수 비중: {bid_weight:.2%})"

        return True, "매수 조건 충족"

    def check_exit_conditions(self, position: Dict, market_data: Dict,
                              holding_minutes: float) -> Tuple[bool, str, str]:
        """
        매도 조건 체크

        Args:
            position: 포지션 정보
            market_data: 현재 시장 데이터
            holding_minutes: 보유 시간 (분)

        Returns:
            (청산 여부, 청산 유형, 사유)
        """
        current_price = market_data['current_price']
        entry_price = position['entry_price']
        profit_rate = (current_price - entry_price) / entry_price * 100

        target_profit = position.get('target_profit', self.target_profit)

        # 1. 목표 익절
        if profit_rate >= target_profit:
            return True, 'TAKE_PROFIT', f"목표 익절 (+{profit_rate:.2f}%)"

        # 2. 과열 익절
        if holding_minutes >= 8 and market_data['rsi_5m'] > 75 and profit_rate >= 0.5:
            return True, 'TAKE_PROFIT', f"과열 익절 (+{profit_rate:.2f}%)"

        # 3. SMA 7 이탈
        if 'sma_7' in market_data:
            if current_price < market_data['sma_7'] * 0.998 and profit_rate > 0.05:
                return True, 'TAKE_PROFIT', f"SMA 이탈 익절 (+{profit_rate:.2f}%)"

            if current_price < market_data['sma_7'] * 0.997 and profit_rate <= 0.05:
                return True, 'TAKE_PROFIT', f"SMA 이탈 청산 ({profit_rate:.2f}%)"

        # 4. 손절가 도달
        if profit_rate <= self.stop_loss:
            return True, 'STOP_LOSS', f"손절 ({profit_rate:.2f}%)"

        # 5. RSI 급락 빠른 손절
        if holding_minutes <= 5:
            entry_rsi = position.get('entry_rsi_5m', position.get('entry_rsi', 50))
            if market_data['rsi_5m'] < entry_rsi - 10 and profit_rate <= -0.3:
                return True, 'STOP_LOSS', f"급락 손절 ({profit_rate:.2f}%)"

        # 6. 빠른 손절
        if holding_minutes >= 30:
            if profit_rate < -0.2:
                if market_data['rsi_5m'] < position.get('entry_rsi_5m', 50) - 5:
                    return True, 'STOP_LOSS', f"하락 추세 손절 ({profit_rate:+.2f}%)"

        # 7. 장기 보유 손절
        if holding_minutes >= 60:
            if profit_rate < 0:
                return True, 'STOP_LOSS', f"장기 보유 손절 ({profit_rate:+.2f}%)"

        return False, None, None
