"""
변동성 브레이크아웃 전략
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple
from datetime import datetime

from ..base_strategy import BaseStrategy


class VolatilityBreakoutStrategy(BaseStrategy):
    """
    변동성 브레이크아웃 전략 (ATR 기반)

    특징:
    - 급격한 변동성 증가 시 진입
    - 큰 움직임 포착
    - 고위험 고수익

    진입:
    - ATR 급증 (평균의 1.5배 이상)
    - 가격이 전일 고점 + (ATR * 0.5) 돌파
    - 거래량 > 평균

    청산:
    - 목표: ATR의 2배 수익
    - 손절: ATR의 1배 손실
    - 또는 변동성 급락 시
    """

    def __init__(self, config: Dict):
        """
        초기화

        Args:
            config: 전략 설정
        """
        super().__init__(config)

        # ATR 파라미터
        self.atr_period = config.get('atr_period', 14)
        self.atr_multiplier = config.get('atr_multiplier', 1.5)  # 진입 기준 (ATR 급증)
        self.breakout_atr_factor = config.get('breakout_atr_factor', 0.5)  # 돌파 기준

        # 청산 파라미터
        self.target_atr_multiple = config.get('target_atr_multiple', 2.0)  # 목표: ATR * 2
        self.stop_atr_multiple = config.get('stop_atr_multiple', 1.0)  # 손절: ATR * 1

        # 거래량 파라미터
        self.volume_threshold = config.get('volume_threshold', 1.2)

        # 최소 변동성 (너무 작은 ATR은 제외)
        self.min_atr_krw = config.get('min_atr_krw', 10000)  # 최소 ATR (원화)

    def check_entry_conditions(self, market_data: Dict) -> Tuple[bool, str]:
        """
        매수 조건 체크

        Args:
            market_data: 시장 데이터
                - current_price: 현재가
                - atr: ATR 값
                - atr_ma: ATR 평균
                - prev_high: 전일 고점
                - volume_ratio: 거래량 배율
                - latest_candle: 최근 캔들

        Returns:
            (진입 가능 여부, 사유)
        """
        current_price = market_data['current_price']
        atr = market_data.get('atr', 0)
        atr_ma = market_data.get('atr_ma', 0)

        # 1. ATR 유효성 체크
        if atr <= 0 or atr_ma <= 0:
            return False, "ATR 데이터 없음"

        # 2. 최소 변동성 체크 (너무 작은 코인 제외)
        if atr < self.min_atr_krw:
            return False, f"ATR 너무 작음 (₩{atr:,.0f} < ₩{self.min_atr_krw:,.0f})"

        # 3. ATR 급증 체크 (변동성 증가)
        atr_ratio = atr / atr_ma
        if atr_ratio < self.atr_multiplier:
            return False, f"ATR 급증 없음 ({atr_ratio:.2f}x < {self.atr_multiplier}x)"

        # 4. 가격 돌파 체크
        # 전일 고점 + (ATR * 0.5) 돌파
        prev_high = market_data.get('prev_high', 0)
        if prev_high <= 0:
            return False, "전일 고점 데이터 없음"

        breakout_level = prev_high + (atr * self.breakout_atr_factor)

        if current_price < breakout_level:
            return False, f"돌파 레벨 미도달 (현재: ₩{current_price:,.0f} < 목표: ₩{breakout_level:,.0f})"

        # 5. 거래량 체크
        volume_ratio = market_data.get('volume_ratio', 0)
        if volume_ratio < self.volume_threshold:
            return False, f"거래량 부족 ({volume_ratio:.2f}x < {self.volume_threshold}x)"

        # 6. 양봉 확인 (강한 상승 신호)
        candle = market_data.get('latest_candle')
        if candle and candle['close'] <= candle['open']:
            return False, "음봉 캔들"

        breakout_pct = (current_price - prev_high) / prev_high * 100
        return True, f"변동성 브레이크아웃 진입 (ATR: {atr_ratio:.2f}x, 돌파: +{breakout_pct:.2f}%)"

    def check_exit_conditions(self, position: Dict, market_data: Dict,
                              holding_minutes: float) -> Tuple[bool, str, str]:
        """
        매도 조건 체크

        Args:
            position: 포지션 정보
                - entry_price: 진입가
                - entry_atr: 진입 시 ATR
            market_data: 현재 시장 데이터
            holding_minutes: 보유 시간 (분)

        Returns:
            (청산 여부, 청산 유형, 사유)
        """
        current_price = market_data['current_price']
        entry_price = position['entry_price']
        entry_atr = position.get('entry_atr', 0)
        profit = current_price - entry_price

        if entry_atr <= 0:
            # ATR 정보 없으면 고정 비율 사용
            profit_rate = (profit / entry_price) * 100
            if profit_rate >= 3.0:
                return True, 'TAKE_PROFIT', f"목표 익절 (+{profit_rate:.2f}%)"
            if profit_rate <= -2.0:
                return True, 'STOP_LOSS', f"손절 ({profit_rate:.2f}%)"
        else:
            # 1. ATR 기반 목표 익절
            target_profit = entry_atr * self.target_atr_multiple
            if profit >= target_profit:
                profit_rate = (profit / entry_price) * 100
                return True, 'TAKE_PROFIT', f"ATR 목표 익절 (+{profit_rate:.2f}%, ₩{profit:,.0f})"

            # 2. ATR 기반 손절
            stop_loss = -entry_atr * self.stop_atr_multiple
            if profit <= stop_loss:
                profit_rate = (profit / entry_price) * 100
                return True, 'STOP_LOSS', f"ATR 손절 ({profit_rate:.2f}%, ₩{profit:,.0f})"

        # 3. 변동성 급락 시 청산 (진입 이유 소멸)
        current_atr = market_data.get('atr', 0)
        atr_ma = market_data.get('atr_ma', 0)

        if current_atr > 0 and atr_ma > 0:
            current_atr_ratio = current_atr / atr_ma

            # ATR이 평균 이하로 떨어지면 변동성 소멸로 판단
            if current_atr_ratio < 1.0 and profit > 0:
                profit_rate = (profit / entry_price) * 100
                return True, 'TAKE_PROFIT', f"변동성 소멸 익절 (+{profit_rate:.2f}%)"

        # 4. 장기 보유 손절 (90분 이상, 손실 중)
        if holding_minutes >= 90:
            profit_rate = (profit / entry_price) * 100
            if profit_rate < 0:
                return True, 'STOP_LOSS', f"장기 보유 손절 ({profit_rate:.2f}%)"

        # 5. 급격한 반전 감지 (고점 대비 -3% 하락)
        peak_price = position.get('peak_price', entry_price)
        if current_price > peak_price:
            position['peak_price'] = current_price
            peak_price = current_price

        if peak_price > entry_price:
            drawdown_from_peak = (current_price - peak_price) / peak_price * 100
            if drawdown_from_peak <= -3.0:
                profit_rate = (profit / entry_price) * 100
                return True, 'TAKE_PROFIT', f"반전 감지 익절 (고점 대비 {drawdown_from_peak:.2f}%)"

        return False, None, None
