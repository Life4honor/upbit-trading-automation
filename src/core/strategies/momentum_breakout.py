"""
모멘텀 브레이크아웃 전략
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple
from datetime import datetime

from ..base_strategy import BaseStrategy


class MomentumBreakoutStrategy(BaseStrategy):
    """
    모멘텀 브레이크아웃 전략

    진입:
    - 가격이 N일 고점 돌파
    - 거래량이 평균의 X배 이상
    - RSI > 50 (과매도 아님)
    - MACD > Signal (상승 추세)

    청산:
    - 목표: +3% 수익
    - 손절: -1.5% 손실
    - 또는 고점 대비 -2% 하락
    """

    def __init__(self, config: Dict):
        """
        초기화

        Args:
            config: 전략 설정
        """
        super().__init__(config)

        # 브레이크아웃 파라미터
        self.lookback_period = config.get('lookback_period', 20)  # 돌파 감지 기간
        self.volume_threshold = config.get('volume_threshold', 1.5)  # 거래량 배율
        self.rsi_min = config.get('rsi_min', 50)  # RSI 최소값

        # MACD 파라미터
        self.macd_fast = config.get('macd_fast', 12)
        self.macd_slow = config.get('macd_slow', 26)
        self.macd_signal = config.get('macd_signal', 9)

        # 청산 파라미터
        self.target_profit = config.get('target_profit', 3.0)  # 목표 수익률 (%)
        self.stop_loss = config.get('stop_loss', -1.5)  # 손절 기준 (%)
        self.trailing_stop_pct = config.get('trailing_stop_pct', 2.0)  # 고점 대비 트레일링 (%)

    def check_entry_conditions(self, market_data: Dict) -> Tuple[bool, str]:
        """
        매수 조건 체크

        Args:
            market_data: 시장 데이터
                - current_price: 현재가
                - highest_price_Nd: N일 고점
                - rsi_5m: RSI
                - macd, macd_signal, macd_histogram: MACD 지표
                - volume_ratio: 거래량 배율
                - latest_candle: 최근 캔들

        Returns:
            (진입 가능 여부, 사유)
        """
        current_price = market_data['current_price']
        candle = market_data['latest_candle']

        # 1. 고점 돌파 체크
        highest_key = f'highest_price_{self.lookback_period}d'
        if highest_key not in market_data:
            return False, f"{self.lookback_period}일 고점 데이터 없음"

        highest_price = market_data[highest_key]

        # 현재가가 고점을 돌파했는지 확인
        if current_price <= highest_price:
            return False, f"고점 미돌파 (현재: ₩{current_price:,.0f} <= 고점: ₩{highest_price:,.0f})"

        # 2. 거래량 체크
        volume_ratio = market_data.get('volume_ratio', 0)
        if volume_ratio < self.volume_threshold:
            return False, f"거래량 부족 ({volume_ratio:.2f}x < {self.volume_threshold}x)"

        # 3. RSI 체크 (과매도 아닌지 확인)
        rsi = market_data.get('rsi_5m', 50)
        if rsi < self.rsi_min:
            return False, f"RSI 너무 낮음 ({rsi:.1f} < {self.rsi_min})"

        # 4. MACD 체크 (상승 추세 확인)
        macd = market_data.get('macd', 0)
        macd_signal = market_data.get('macd_signal', 0)

        if macd <= macd_signal:
            return False, f"MACD 신호 미충족 (MACD: {macd:.2f} <= Signal: {macd_signal:.2f})"

        # 5. 양봉 확인 (선택적, 강한 신호)
        if candle['close'] <= candle['open']:
            return False, "음봉 캔들"

        return True, f"모멘텀 브레이크아웃 진입 (고점 돌파: +{(current_price/highest_price-1)*100:.2f}%)"

    def check_exit_conditions(self, position: Dict, market_data: Dict,
                              holding_minutes: float) -> Tuple[bool, str, str]:
        """
        매도 조건 체크

        Args:
            position: 포지션 정보
                - entry_price: 진입가
                - peak_price: 진입 후 최고가 (업데이트 필요)
            market_data: 현재 시장 데이터
            holding_minutes: 보유 시간 (분)

        Returns:
            (청산 여부, 청산 유형, 사유)
        """
        current_price = market_data['current_price']
        entry_price = position['entry_price']
        profit_rate = (current_price - entry_price) / entry_price * 100

        # 포지션의 최고가 업데이트 (트레일링 스톱용)
        peak_price = position.get('peak_price', entry_price)
        if current_price > peak_price:
            position['peak_price'] = current_price
            peak_price = current_price

        # 1. 목표 익절
        if profit_rate >= self.target_profit:
            return True, 'TAKE_PROFIT', f"목표 익절 (+{profit_rate:.2f}%)"

        # 2. 손절가 도달
        if profit_rate <= self.stop_loss:
            return True, 'STOP_LOSS', f"손절 ({profit_rate:.2f}%)"

        # 3. 트레일링 스톱 (고점 대비 일정 % 하락)
        if peak_price > entry_price:  # 수익 중일 때만
            drawdown_from_peak = (current_price - peak_price) / peak_price * 100
            if drawdown_from_peak <= -self.trailing_stop_pct:
                return True, 'TAKE_PROFIT', f"트레일링 스톱 (고점 대비 {drawdown_from_peak:.2f}%)"

        # 4. MACD 추세 전환 (하락 전환 시 청산)
        macd = market_data.get('macd', 0)
        macd_signal = market_data.get('macd_signal', 0)

        if macd < macd_signal and profit_rate > 0.5:
            return True, 'TAKE_PROFIT', f"MACD 추세 전환 익절 (+{profit_rate:.2f}%)"

        # 5. 장기 보유 손절 (60분 이상 보유, 손실 중)
        if holding_minutes >= 60 and profit_rate < 0:
            return True, 'STOP_LOSS', f"장기 보유 손절 ({profit_rate:.2f}%)"

        return False, None, None
