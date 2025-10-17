"""
그리드 트레이딩 전략
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, List
from datetime import datetime

from ..base_strategy import BaseStrategy


class GridTradingStrategy(BaseStrategy):
    """
    그리드 트레이딩 전략

    특징:
    - 횡보장에서 수익 극대화
    - 일정 간격으로 여러 개의 매수/매도 주문
    - 낮은 변동성 구간에서 효과적

    진입:
    - 변동성이 낮은 횡보장 감지 (ATR < 평균)
    - 그리드 하단 도달 시 매수

    청산:
    - 개별 포지션 손절 -1.5%
    - 그리드 상단 도달 시 매도
    - 총 손실 -3% 도달 시 전량 청산
    """

    def __init__(self, config: Dict):
        """
        초기화

        Args:
            config: 전략 설정
        """
        super().__init__(config)

        # 그리드 파라미터
        self.grid_levels = config.get('grid_levels', 5)  # 그리드 개수
        self.grid_spacing = config.get('grid_spacing', 1.0)  # 각 그리드 간격 (%)
        self.max_positions = config.get('max_positions', 3)  # 동시 보유 최대 개수

        # 변동성 파라미터
        self.atr_period = config.get('atr_period', 14)
        self.max_atr_threshold = config.get('max_atr_threshold', 0.8)  # 평균 ATR 대비 최대 비율

        # 청산 파라미터
        self.single_position_stop_loss = config.get('single_position_stop_loss', -1.5)  # 개별 포지션 손절 (%)
        self.total_stop_loss = config.get('total_stop_loss', 0)  # 총 손실 한도 (%) (0 이면 비활성화)
        self.single_grid_profit = config.get('single_grid_profit', 1.0)  # 개별 그리드 수익률 (%)
        self.long_hold_minutes = config.get('long_hold_minutes', 0)  # 장기 보유 시간 (분, 0 이면 비활성화)
        self.long_hold_loss_threshold = config.get('long_hold_loss_threshold', -1.0)  # 장기 보유 손절 임계값 (%)

        # 그리드 재초기화 파라미터
        self.grid_reset_hours = config.get('grid_reset_hours', 24)  # 주기적 재초기화 (시간, 0이면 비활성화)
        self.bb_period = config.get('bb_period', 20)  # 볼린저 밴드 기간
        self.bb_std = config.get('bb_std', 2.0)  # 볼린저 밴드 표준편차
        self.bb_width_change_threshold = config.get('bb_width_change_threshold', 30.0)  # 밴드폭 변화율 임계값 (%)

        # 볼린저 밴드 매수 조건 파라미터
        self.use_bb_entry_filter = config.get('use_bb_entry_filter', True)  # BB 매수 필터 사용 여부
        self.bb_entry_position_max = config.get('bb_entry_position_max', 0.4)  # BB 최대 위치 (0.4 = 하위 40%)
        self.bb_width_multiplier_narrow = config.get('bb_width_multiplier_narrow', 1.0)  # 좁은 밴드폭 기준 배수
        self.bb_width_multiplier_wide = config.get('bb_width_multiplier_wide', 1.5)  # 넓은 밴드폭 기준 배수

        # 그리드 상태 (런타임)
        self.grid_prices = []  # 그리드 가격 레벨
        self.base_price = None  # 그리드 기준 가격
        self.grid_initialized_at = None  # 그리드 초기화 시각
        self.last_bb_width = None  # 이전 볼린저 밴드 폭

    def initialize_grid(self, current_price: float, timestamp: datetime = None):
        """
        그리드 가격 레벨 초기화

        Args:
            current_price: 현재가
            timestamp: 초기화 시각 (None이면 현재 시각)
        """
        self.base_price = current_price
        self.grid_prices = []
        self.grid_initialized_at = timestamp or datetime.now()

        # 현재가 기준으로 위아래로 그리드 생성
        for i in range(-(self.grid_levels // 2), (self.grid_levels // 2) + 1):
            price = current_price * (1 + (i * self.grid_spacing / 100))
            self.grid_prices.append(price)

        self.grid_prices.sort()

    def get_nearest_grid_level(self, price: float) -> Tuple[int, float]:
        """
        가장 가까운 그리드 레벨 찾기

        Args:
            price: 현재가

        Returns:
            (레벨 인덱스, 그리드 가격)
        """
        if not self.grid_prices:
            return -1, 0.0

        nearest_idx = min(range(len(self.grid_prices)),
                         key=lambda i: abs(self.grid_prices[i] - price))
        return nearest_idx, self.grid_prices[nearest_idx]

    def check_bb_entry_condition(self, market_data: Dict) -> Tuple[bool, str]:
        """
        볼린저 밴드 기반 매수 조건 체크 (동적)

        밴드폭에 따라 적정 매수 거리를 동적으로 조정:
        - 좁은 밴드폭 (< 4%): 하위 40% 이내에서만 매수
        - 보통 밴드폭 (4-8%): 하위 50% 이내에서만 매수
        - 넓은 밴드폭 (> 8%): 하위 60% 이내에서만 매수

        Args:
            market_data: 시장 데이터
                - current_price: 현재가
                - bb_upper: 볼린저 밴드 상단
                - bb_lower: 볼린저 밴드 하단

        Returns:
            (진입 가능 여부, 사유)
        """
        if not self.use_bb_entry_filter:
            return True, "BB 필터 비활성화"

        current_price = market_data['current_price']
        bb_upper = market_data.get('bb_upper')
        bb_lower = market_data.get('bb_lower')

        # BB 데이터 없으면 통과
        if not bb_upper or not bb_lower or bb_upper <= bb_lower:
            return True, "BB 데이터 없음"

        # 1. 현재가의 BB 위치 계산 (0 = 하단, 1 = 상단)
        bb_position = (current_price - bb_lower) / (bb_upper - bb_lower)

        # 2. BB 폭 계산 (현재가 대비 %)
        bb_width_pct = (bb_upper - bb_lower) / current_price * 100

        # 3. 밴드폭에 따른 동적 임계값 계산
        if bb_width_pct < 4.0:
            # 좁은 밴드폭 (횡보장) -> 보수적 진입
            max_position = self.bb_entry_position_max * self.bb_width_multiplier_narrow
            width_type = "좁음"
        elif bb_width_pct < 8.0:
            # 보통 밴드폭 -> 적당한 진입
            max_position = self.bb_entry_position_max * 1.25
            width_type = "보통"
        else:
            # 넓은 밴드폭 (변동성 높음) -> 더 여유있게
            max_position = self.bb_entry_position_max * self.bb_width_multiplier_wide
            width_type = "넓음"

        # 최대값 제한 (너무 높아지지 않도록)
        max_position = min(max_position, 0.65)

        # 4. 판정
        if bb_position > max_position:
            return False, (
                f"BB 위치 과도 ({bb_position:.1%} > {max_position:.1%}, "
                f"폭: {bb_width_pct:.1f}% [{width_type}])"
            )

        return True, (
            f"BB 하단 근처 ({bb_position:.1%}, 폭: {bb_width_pct:.1f}% [{width_type}])"
        )

    def should_reset_grid(self, market_data: Dict) -> Tuple[bool, str]:
        """
        그리드 재초기화 여부 판단

        Args:
            market_data: 시장 데이터

        Returns:
            (재초기화 필요 여부, 사유)
        """
        current_price = market_data['current_price']
        current_time = market_data.get('timestamp')

        # 1. 첫 진입 - 항상 초기화
        if not self.grid_prices:
            return True, "첫 그리드 초기화"

        # 2. 주기적 재초기화 체크 (설정된 경우)
        if self.grid_reset_hours > 0 and self.grid_initialized_at and current_time:
            hours_since_init = (current_time - self.grid_initialized_at).total_seconds() / 3600
            if hours_since_init >= self.grid_reset_hours:
                return True, f"주기적 재초기화 ({hours_since_init:.1f}시간 경과)"

        # 3. 볼린저 밴드 폭 변화 체크
        bb_upper = market_data.get('bb_upper')
        bb_lower = market_data.get('bb_lower')

        if bb_upper and bb_lower:
            current_bb_width = (bb_upper - bb_lower) / current_price * 100  # 현재가 대비 밴드폭 (%)

            if self.last_bb_width is not None:
                # 밴드폭 변화율 계산
                width_change_pct = abs(current_bb_width - self.last_bb_width) / self.last_bb_width * 100

                if width_change_pct >= self.bb_width_change_threshold:
                    self.last_bb_width = current_bb_width
                    return True, f"볼린저 밴드폭 급변 ({width_change_pct:.1f}% 변화)"

            self.last_bb_width = current_bb_width

        # 4. 가격 이탈 체크 (기존 로직 - 더 넓게 완화)
        min_grid = min(self.grid_prices)
        max_grid = max(self.grid_prices)

        if current_price < min_grid * 0.85 or current_price > max_grid * 1.15:
            return True, f"가격 이탈 (그리드: ₩{min_grid:,.0f}~₩{max_grid:,.0f})"

        return False, ""

    def check_entry_conditions(self, market_data: Dict) -> Tuple[bool, str]:
        """
        매수 조건 체크

        Args:
            market_data: 시장 데이터
                - current_price: 현재가
                - timestamp: 현재 시각
                - atr: ATR 값
                - atr_ma: ATR 평균
                - volatility: 변동성
                - active_positions: 현재 보유 중인 포지션 수
                - bb_upper: 볼린저 밴드 상단
                - bb_lower: 볼린저 밴드 하단

        Returns:
            (진입 가능 여부, 사유)
        """
        current_price = market_data['current_price']

        # 1. 최대 포지션 체크
        active_positions = market_data.get('active_positions', 0)
        if active_positions >= self.max_positions:
            return False, f"최대 포지션 도달 ({active_positions}/{self.max_positions})"

        # 2. 변동성 체크 (낮은 변동성 = 횡보장)
        atr = market_data.get('atr', 0)
        atr_ma = market_data.get('atr_ma', 0)

        if atr_ma > 0:
            atr_ratio = atr / atr_ma
            if atr_ratio > self.max_atr_threshold:
                return False, f"변동성 너무 높음 (ATR 비율: {atr_ratio:.2f})"

        # 3. 볼린저 밴드 위치 체크 (박스권 상단 진입 방지)
        bb_ok, bb_reason = self.check_bb_entry_condition(market_data)
        if not bb_ok:
            return False, bb_reason

        # 4. 그리드 재초기화 체크
        should_reset, reset_reason = self.should_reset_grid(market_data)
        if should_reset:
            timestamp = market_data.get('timestamp')
            self.initialize_grid(current_price, timestamp)

        # 5. 그리드 하단 도달 체크
        # 현재가가 그리드 레벨 근처인지 확인 (±0.2% 허용)
        nearest_idx, nearest_grid = self.get_nearest_grid_level(current_price)

        if nearest_idx < 0:
            return False, "그리드 레벨 없음"

        # 현재가가 그리드 가격의 하단에 있는지 확인
        price_diff_pct = (current_price - nearest_grid) / nearest_grid * 100

        # 그리드 하단(-0.2% ~ 0%) 범위에 있을 때 매수
        if not (-0.2 <= price_diff_pct <= 0.1):
            return False, f"그리드 레벨 미도달 (차이: {price_diff_pct:+.2f}%)"

        # 6. 중간 그리드 이하에서만 매수 (상단에서는 매수 안 함)
        mid_idx = len(self.grid_prices) // 2
        if nearest_idx > mid_idx:
            return False, f"그리드 상단 ({nearest_idx}/{len(self.grid_prices)})"

        return True, f"그리드 매수 (레벨 {nearest_idx}, ₩{nearest_grid:,.0f})"

    def check_exit_conditions(self, position: Dict, market_data: Dict,
                              holding_minutes: float) -> Tuple[bool, str, str]:
        """
        매도 조건 체크

        Args:
            position: 포지션 정보
                - entry_price: 진입가
                - entry_grid_level: 진입 그리드 레벨
            market_data: 현재 시장 데이터
            holding_minutes: 보유 시간 (분)

        Returns:
            (청산 여부, 청산 유형, 사유)
        """
        current_price = market_data['current_price']
        entry_price = position['entry_price']
        profit_rate = (current_price - entry_price) / entry_price * 100

        # 1. 개별 포지션 손절 (최우선)
        if profit_rate <= self.single_position_stop_loss:
            return True, 'STOP_LOSS', f"개별 포지션 손절 ({profit_rate:.2f}%)"

        # 2. 개별 그리드 목표 익절
        if profit_rate >= self.single_grid_profit:
            return True, 'TAKE_PROFIT', f"그리드 익절 (+{profit_rate:.2f}%)"

        # 3. 총 손실 한도 (포트폴리오 전체)
        total_profit_rate = market_data.get('total_profit_rate', 0)
        if total_profit_rate <= self.total_stop_loss and self.total_stop_loss != 0:
            return True, 'STOP_LOSS', f"총 손실 한도 도달 ({total_profit_rate:.2f}%)"

        # 4. 그리드 상단 도달 시 익절 (그리드 시스템 기반)
        entry_grid_level = position.get('entry_grid_level', -1)
        if entry_grid_level >= 0 and self.grid_prices:
            # 진입 레벨보다 위의 그리드 레벨 도달 시
            target_level = entry_grid_level + 1

            if target_level < len(self.grid_prices):
                target_price = self.grid_prices[target_level]

                if current_price >= target_price:
                    return True, 'TAKE_PROFIT', f"다음 그리드 도달 (+{profit_rate:.2f}%)"

        # 5. 변동성 급증 시 청산 (횡보장 이탈)
        atr = market_data.get('atr', 0)
        atr_ma = market_data.get('atr_ma', 0)

        if atr_ma > 0:
            atr_ratio = atr / atr_ma
            # ATR이 평균의 1.5배 이상이면 횡보장 이탈로 판단
            if atr_ratio > 1.5:
                if profit_rate > 0.5:
                    return True, 'TAKE_PROFIT', f"변동성 급증 익절 (+{profit_rate:.2f}%)"
                if profit_rate < -0.3:
                    return True, 'TAKE_PROFIT', f"변동성 급증 손절 (-{profit_rate:.2f}%)"

        # 6. 장기 보유 손절 (설정된 시간 이상, 일정 손실 중)
        # long_hold_minutes가 0이면 비활성화
        if self.long_hold_minutes > 0:
            if holding_minutes >= self.long_hold_minutes and profit_rate < self.long_hold_loss_threshold:
                return True, 'STOP_LOSS', f"장기 보유 손절 ({profit_rate:.2f}%)"

        return False, None, None

    def reset_grid(self):
        """그리드 초기화"""
        self.grid_prices = []
        self.base_price = None
