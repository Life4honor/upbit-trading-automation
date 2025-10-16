"""
볼린저밴드 리버설 전략 (평균회귀)
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple
from datetime import datetime

from ..base_strategy import BaseStrategy


class BollingerReversalStrategy(BaseStrategy):
    """
    볼린저밴드 리버설 전략 (평균회귀)

    특징:
    - 과매도 구간에서 반등 포착
    - 높은 승률 기대
    - 작은 손절, 빠른 익절

    진입:
    - 가격이 볼린저밴드 하단 돌파 후 반등
    - RSI < 30 (과매도)
    - 거래량 > 평균 (패닉셀 후 반등)
    - 양봉 출현

    청산:
    - BB 중심선 도달 또는 +2% 익절
    - -1.5% 손절
    - BB 하단 재돌파 손절
    """

    def __init__(self, config: Dict):
        """
        초기화

        Args:
            config: 전략 설정
        """
        super().__init__(config)

        # 볼린저밴드 파라미터
        self.bb_period = config.get('bb_period', 20)
        self.bb_std = config.get('bb_std', 2.0)
        self.bb_width_min = config.get('bb_width_min', 2.0)  # 최소 BB 폭 (%)

        # 진입 조건
        self.rsi_period = config.get('rsi_period', 14)
        self.rsi_oversold = config.get('rsi_oversold', 30)  # RSI 과매도 기준
        self.volume_threshold = config.get('volume_threshold', 1.2)
        self.require_reversal_candle = config.get('require_reversal_candle', True)  # 양봉 필수

        # 청산 조건
        self.target_bb_position = config.get('target_bb_position', 0.5)  # BB 중심선 (0.5)
        self.target_profit_pct = config.get('target_profit_pct', 2.0)  # 고정 목표 +2%
        self.stop_loss_pct = config.get('stop_loss_pct', -1.5)  # 고정 손절 -1.5%
        self.time_stop_minutes = config.get('time_stop_minutes', 60)  # 시간 손절

        # RSI 과매수 익절
        self.rsi_overbought = config.get('rsi_overbought', 70)

    def check_entry_conditions(self, market_data: Dict) -> Tuple[bool, str]:
        """
        매수 조건 체크

        Args:
            market_data: 시장 데이터
                - current_price: 현재가
                - prev_close: 이전 종가
                - bb_upper, bb_middle, bb_lower: 볼린저밴드
                - bb_width: BB 폭
                - rsi_5m: RSI
                - volume_ratio: 거래량 배율
                - latest_candle: 최근 캔들

        Returns:
            (진입 가능 여부, 사유)
        """
        current_price = market_data['current_price']
        prev_close = market_data.get('prev_close', current_price)

        # 1. 볼린저밴드 데이터 확인
        if not all(k in market_data for k in ['bb_upper', 'bb_middle', 'bb_lower', 'bb_width']):
            return False, "볼린저밴드 데이터 없음"

        bb_upper = market_data['bb_upper']
        bb_middle = market_data['bb_middle']
        bb_lower = market_data['bb_lower']
        bb_width = market_data['bb_width']

        # 2. BB Width 체크 (변동성 충분)
        if bb_width < self.bb_width_min:
            return False, f"변동성 부족 (BB Width: {bb_width:.2f}% < {self.bb_width_min}%)"

        # 3. 반등 패턴 감지
        # 이전 종가: 하단 아래, 현재가: 하단 위 (반등)
        if not (prev_close < bb_lower and current_price > bb_lower):
            # 또는 현재가가 하단 근처 (±0.2%) 에 있는 경우도 허용
            bb_lower_tolerance = bb_lower * 1.002  # +0.2%
            if current_price > bb_lower_tolerance:
                return False, "BB 하단 반등 패턴 없음"

        # 4. RSI 과매도 확인
        rsi = market_data.get('rsi_5m', 50)
        if rsi >= self.rsi_oversold:
            return False, f"RSI 과매도 아님 ({rsi:.1f} >= {self.rsi_oversold})"

        # 5. 거래량 확인
        volume_ratio = market_data.get('volume_ratio', 0)
        if volume_ratio < self.volume_threshold:
            return False, f"거래량 부족 ({volume_ratio:.2f}x < {self.volume_threshold}x)"

        # 6. 양봉 확인 (반등 신호)
        if self.require_reversal_candle:
            candle = market_data.get('latest_candle')
            if candle and candle['close'] <= candle['open']:
                return False, "양봉 아님 (반등 신호 없음)"

        # BB 위치 계산
        if bb_upper > bb_lower:
            bb_position = (current_price - bb_lower) / (bb_upper - bb_lower)
            return True, f"BB 리버설 진입 (RSI: {rsi:.1f}, BB 위치: {bb_position:.1%})"
        else:
            return True, "BB 리버설 진입"

    def check_exit_conditions(self, position: Dict, market_data: Dict,
                              holding_minutes: float) -> Tuple[bool, str, str]:
        """
        매도 조건 체크

        Args:
            position: 포지션 정보
                - entry_price: 진입가
            market_data: 현재 시장 데이터
            holding_minutes: 보유 시간 (분)

        Returns:
            (청산 여부, 청산 유형, 사유)
        """
        current_price = market_data['current_price']
        entry_price = position['entry_price']
        profit_rate = (current_price - entry_price) / entry_price * 100

        # 볼린저밴드 데이터
        bb_upper = market_data.get('bb_upper', 0)
        bb_middle = market_data.get('bb_middle', 0)
        bb_lower = market_data.get('bb_lower', 0)

        # 1. 목표 익절: BB 중심선 도달
        if bb_middle > 0 and current_price >= bb_middle:
            return True, 'TAKE_PROFIT', f"BB 중심선 도달 (+{profit_rate:.2f}%)"

        # 2. 목표 익절: 고정 수익률
        if profit_rate >= self.target_profit_pct:
            return True, 'TAKE_PROFIT', f"목표 달성 (+{profit_rate:.2f}%)"

        # 3. 손절: 고정 손절가
        if profit_rate <= self.stop_loss_pct:
            return True, 'STOP_LOSS', f"손절 ({profit_rate:.2f}%)"

        # 4. 손절: BB 하단 재돌파 (반등 실패)
        if bb_lower > 0 and current_price < bb_lower:
            return True, 'STOP_LOSS', f"BB 하단 재돌파 ({profit_rate:.2f}%)"

        # 5. 시간 손절 (장기 보유, 손실 또는 저수익)
        if holding_minutes >= self.time_stop_minutes:
            if profit_rate <= 0:
                return True, 'STOP_LOSS', f"시간 손절 ({profit_rate:.2f}%)"
            elif profit_rate < 0.5:  # 60분 이상 보유했는데 수익 0.5% 미만
                return True, 'TAKE_PROFIT', f"시간 초과 익절 (+{profit_rate:.2f}%)"

        # 6. RSI 과매수 익절 (반등 완료)
        rsi = market_data.get('rsi_5m', 50)
        if rsi > self.rsi_overbought and profit_rate > 0.5:
            return True, 'TAKE_PROFIT', f"RSI 과매수 익절 (+{profit_rate:.2f}%, RSI: {rsi:.1f})"

        # 7. BB 상단 근접 익절 (80% 이상)
        if bb_upper > bb_lower and bb_lower > 0:
            bb_position = (current_price - bb_lower) / (bb_upper - bb_lower)
            if bb_position >= 0.8 and profit_rate > 1.0:
                return True, 'TAKE_PROFIT', f"BB 상단 근접 익절 (+{profit_rate:.2f}%, 위치: {bb_position:.1%})"

        return False, None, None
