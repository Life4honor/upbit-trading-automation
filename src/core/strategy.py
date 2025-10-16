"""
초단타 스캘핑 전략 (백테스트 + 실거래 공통)
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional
from datetime import datetime


class ScalpingStrategy:
    """
    초단타 스캘핑 전략
    백테스트와 실거래에서 동일한 로직 사용
    """
    
    def __init__(self, config: Dict):
        """
        초기화

        Args:
            config: 전략 설정
        """
        # RSI 조건
        self.rsi_5m_min = config.get('rsi_5m_min', 60)
        self.rsi_5m_max = config.get('rsi_5m_max', 75)
        self.rsi_15m_min = config.get('rsi_15m_min', 50)
        self.rsi_15m_max = config.get('rsi_15m_max', 70)
        self.rsi_1h_min = config.get('rsi_1h_min', 45)
        self.rsi_1h_max = config.get('rsi_1h_max', 80)

        # 손익 기준
        self.target_profit = config.get('target_profit', 0.35)
        self.stop_loss = config.get('stop_loss', -0.28)

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
        self.min_volume_krw = config.get('min_volume_krw', 0)  # 절대 거래량 (원화)
        self.volume_1h_increasing = config.get('volume_1h_increasing', False)
        self.strong_rsi_threshold = config.get('strong_rsi_threshold', 70)  # 강한 RSI 기준
        self.bid_ask_imbalance_min = config.get('bid_ask_imbalance_min', 0.6)  # 호가 불균형 (매수호가 비중)

        # 기타
        self.cooldown_minutes = config.get('cooldown_minutes', 0)
        self.max_trades_per_day = config.get('max_trades_per_day', None)  # None = 무제한

        # 시간대 필터
        self.use_time_filter = config.get('use_time_filter', False)
        self.time_filter_mode = config.get('time_filter_mode', 'optimal')
        self.exclude_weekdays = config.get('exclude_weekdays', [])
        self.preferred_weekdays = config.get('preferred_weekdays', None)
        self.allowed_hours = config.get('allowed_hours', list(range(24)))

    @staticmethod
    def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
        """RSI 계산"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if len(rsi) > 0 else 50.0
    
    @staticmethod
    def calculate_sma(prices: pd.Series, period: int) -> float:
        """이동평균 계산"""
        sma = prices.rolling(window=period).mean()
        return sma.iloc[-1] if len(sma) > 0 else prices.iloc[-1]

    @staticmethod
    def calculate_bollinger_bands(prices: pd.Series, period: int = 20, std_dev: float = 2.0) -> Tuple[float, float, float]:
        """
        볼린저 밴드 계산

        Returns:
            (upper_band, middle_band, lower_band)
        """
        middle = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)

        if len(middle) > 0:
            return upper.iloc[-1], middle.iloc[-1], lower.iloc[-1]
        else:
            price = prices.iloc[-1]
            return price, price, price

    @staticmethod
    def calculate_bb_width(prices: pd.Series, period: int = 20, std_dev: float = 2.0) -> float:
        """
        볼린저 밴드 폭 계산 (변동성 지표)

        Returns:
            BB Width = (Upper - Lower) / Middle * 100
        """
        upper, middle, lower = ScalpingStrategy.calculate_bollinger_bands(prices, period, std_dev)
        if middle > 0:
            return (upper - lower) / middle * 100
        return 0.0

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
            rsi_score = 0.8 + (rsi_5m - 70) / 100  # 70+ → 0.8~1.0
        elif rsi_5m >= 60:  # 중강 상승
            rsi_score = 0.5 + (rsi_5m - 60) / 33  # 60-70 → 0.5~0.8
        else:  # 약한 상승
            rsi_score = rsi_5m / 120  # ~60 → 0.0~0.5

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
            imbalance_score = 0.9 + (bid_imbalance - 0.70) * 3.3  # 0.70+ → 0.9~1.0
        elif bid_imbalance >= 0.62:  # 강한 매수세
            imbalance_score = 0.6 + (bid_imbalance - 0.62) * 3.75  # 0.62-0.70 → 0.6~0.9
        else:  # 보통 매수세
            imbalance_score = bid_imbalance * 0.97  # ~0.62 → 0.0~0.6

        # 가중 평균 계산 (RSI 40%, 거래량 30%, 호가 30%)
        score = (rsi_score * 0.4) + (volume_score * 0.3) + (imbalance_score * 0.3)

        # 최종 목표 수익률 계산 (범위: dynamic_target_min ~ dynamic_target_max)
        dynamic_target = self.dynamic_target_min + (score * (self.dynamic_target_max - self.dynamic_target_min))

        # 범위 제한
        dynamic_target = max(self.dynamic_target_min, min(self.dynamic_target_max, dynamic_target))

        return round(dynamic_target, 2)
    
    def check_entry_conditions(self, market_data: Dict) -> Tuple[bool, str]:
        """
        매수 조건 체크 (고급 버전)

        Args:
            market_data: {
                'current_price': float,
                'rsi_5m': float,
                'rsi_15m': float,
                'rsi_1h': float (optional),
                'sma_7': float,
                'sma_25': float,
                'sma_99': float (optional),
                'bb_upper': float (optional),
                'bb_middle': float (optional),
                'bb_lower': float (optional),
                'bb_width': float (optional),
                'latest_candle': Series (open, high, low, close, volume),
                'volume_ma': float (optional),
                'volume_1h_ma': float (optional),
                'bid_ask_ratio': float (optional),
                'total_bid_size': float (optional),
                'total_ask_size': float (optional)
            }

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

            # 정배열: 현재가 > SMA7 > SMA25 > SMA99 (순서대로 체크)
            if len(smas) >= 2:
                # 가격이 가장 짧은 SMA보다 높아야 함
                if price <= smas[0]:
                    return False, f"정배열 미충족 (가격: {price:.0f} <= SMA{self.sma_periods[0]}: {smas[0]:.0f})"

                # 각 SMA는 다음 SMA보다 높아야 함 (짧은 기간 > 긴 기간)
                for i in range(len(smas) - 1):
                    if smas[i] <= smas[i + 1]:
                        return False, f"정배열 미충족 (SMA{self.sma_periods[i]}: {smas[i]:.0f} <= SMA{self.sma_periods[i+1]}: {smas[i+1]:.0f})"

        # 5. SMA 7 근접 체크
        if 'sma_7' in market_data:
            # 가격이 SMA 7 위에 있어야 하고, 너무 멀리 떨어지지 않아야 함
            if price < market_data['sma_7']:
                return False, f"SMA 7 아래 (가격: {price:.0f} < SMA7: {market_data['sma_7']:.0f})"

            sma_diff = (price - market_data['sma_7']) / market_data['sma_7'] * 100
            if sma_diff > 0.7:  # 0.7% 이상 벗어나면 제외
                return False, f"SMA 7 거리 초과 ({sma_diff:.2f}% > 0.7%)"

        # 6. 볼린저 밴드 조건
        if self.use_bollinger and all(k in market_data for k in ['bb_upper', 'bb_middle', 'bb_lower', 'bb_width']):
            bb_upper = market_data['bb_upper']
            bb_lower = market_data['bb_lower']
            bb_width = market_data['bb_width']

            # 6-1. 볼린저 밴드 폭 체크 (변동성 최소 기준)
            if bb_width < self.bb_width_min:
                return False, f"변동성 부족 (BB Width: {bb_width:.2f}% < {self.bb_width_min}%)"

            # 6-2. 볼린저 밴드 위치 체크
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
            # 8-1. 절대 거래량 체크 (원화 기준)
            if self.min_volume_krw > 0:
                volume_krw = candle['volume'] * candle['close']
                if volume_krw < self.min_volume_krw:
                    return False, f"절대 거래량 부족 (₩{volume_krw:,.0f} < ₩{self.min_volume_krw:,.0f})"

            # 8-2. 상대 거래량 체크 (평균 대비 배율)
            if 'volume_ma' in market_data and market_data['volume_ma'] > 0:
                volume_ratio = candle['volume'] / market_data['volume_ma']
                if volume_ratio < self.volume_surge_ratio:
                    return False, f"거래량 부족 ({volume_ratio:.2f}x < {self.volume_surge_ratio}x)"

            # 8-3. 1시간 거래량 증가 추세 (optional)
            if self.volume_1h_increasing and 'volume_1h_ma' in market_data:
                if market_data.get('volume_1h_current', 0) < market_data['volume_1h_ma']:
                    return False, "1시간 거래량 감소 추세"

        # 9. 호가 분석
        # 9-1. 호가 비율 체크
        if 'bid_ask_ratio' in market_data:
            if market_data['bid_ask_ratio'] < self.bid_ask_ratio_min:
                return False, f"매수세 부족 (비율: {market_data['bid_ask_ratio']:.2f})"

        # 9-2. 호가 불균형 체크
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
        매도 조건 체크 (동적 목표 수익률 적용)

        Args:
            position: {
                'entry_price': float,
                'entry_rsi': float,
                'entry_time': datetime,
                'target_profit': float (동적 목표)
            }
            market_data: 현재 시장 데이터
            holding_minutes: 보유 시간 (분)

        Returns:
            (청산 여부, 청산 유형, 사유)
        """
        current_price = market_data['current_price']
        entry_price = position['entry_price']
        profit_rate = (current_price - entry_price) / entry_price * 100

        # 포지션의 동적 목표 수익률 사용 (진입 시 계산된 값)
        target_profit = position.get('target_profit', self.target_profit)

        # 1. 목표 익절 (동적 목표 수익률 적용)
        if profit_rate >= target_profit:
            return True, 'TAKE_PROFIT', f"목표 익절 (+{profit_rate:.2f}%)"

        # 2. 과열 익절 (조정된 조건: 보유 8분 이상 + RSI > 75 + 수익 0.2% 이상)
        if holding_minutes >= 8 and market_data['rsi_5m'] > 75 and profit_rate >= 0.5:
            return True, 'TAKE_PROFIT', f"과열 익절 (+{profit_rate:.2f}%)"

        # 3.1 SMA 7 이탈 익절
        if current_price < market_data['sma_7'] * 0.998 and profit_rate > 0.05:
            return True, 'TAKE_PROFIT', f"SMA 이탈 익절 (+{profit_rate:.2f}%)"

        # 3.2 SMA 7 이탈 청산
        if current_price < market_data['sma_7'] * 0.997 and profit_rate <= 0.05:
            return True, 'TAKE_PROFIT', f"SMA 이탈 청산 ({profit_rate:.2f}%)"

        # 4. 손절가 도달
        if profit_rate <= self.stop_loss:
            return True, 'STOP_LOSS', f"손절 ({profit_rate:.2f}%)"

        # 5. RSI 급락 빠른 손절 (보유 5분 이내 + RSI 급락 + 손실)
        if holding_minutes <= 5:
            entry_rsi = position.get('entry_rsi_5m', position.get('entry_rsi', 50))  # 하위 호환성
            if market_data['rsi_5m'] < entry_rsi - 10 and profit_rate <= -0.3:
                return True, 'STOP_LOSS', f"급락 손절 ({profit_rate:.2f}%)"

        # 6. 빠른 손절 (하락 추세 감지 시)
        if holding_minutes >= 30:  # 30분 이상 보유
            if profit_rate < -0.2:  # -0.2% 이상 손실
                # RSI가 계속 하락 중
                if market_data['rsi_5m'] < position.get('entry_rsi_5m', 50) - 5:
                    return True, 'STOP_LOSS', f"하락 추세 손절 ({profit_rate:+.2f}%)"
        
        # 7. 장기 보유 손절 강화
        if holding_minutes >= 60:  # 2시간 이상 보유
            if profit_rate < 0:  # 손실 중이면
                return True, 'STOP_LOSS', f"장기 보유 손절 ({profit_rate:+.2f}%)"

        return False, None, None
    
    def is_trading_hours(self, timestamp: datetime) -> bool:
        """
        거래 가능 시간대 체크

        시간대별 거래량 분석 결과 기반:
        - 고거래량 시간대: 06-12시, 23-02시 (자정 포함)
        - 저거래량 시간대: 03-05시, 14-15시, 19-21시 (피해야 함)

        설정에서 비활성화 가능
        """
        # 시간대 필터 비활성화 시 24시간 거래
        if not self.use_time_filter:
            return True

        hour = timestamp.hour
        weekday = timestamp.weekday()  # 0=월요일, 6=일요일

        # 요일 필터 (설정 가능)
        if weekday in self.exclude_weekdays:
            return False

        # 선호 요일 (설정된 경우 해당 요일만 거래)
        if self.preferred_weekdays is not None and weekday not in self.preferred_weekdays:
            return False

        # 시간대 필터
        if self.time_filter_mode == 'optimal':
            # 최적 시간대만 (고거래량 + 고변동성)
            # BTC/ETH 공통: 오전 6-12시, 밤 11시-새벽 2시
            return (6 <= hour <= 12) or (hour >= 23) or (hour <= 2)

        elif self.time_filter_mode == 'safe':
            # 안전 시간대 (저거래량 시간 제외)
            # 새벽 3-5시, 오후 2-3시, 저녁 7-9시 제외
            excluded_hours = [3, 4, 5, 14, 15, 19, 20, 21]
            return hour not in excluded_hours

        elif self.time_filter_mode == 'peak':
            # 피크 시간대만 (최고 거래량)
            # 오전 6-9시, 자정-새벽 1시
            return (6 <= hour <= 9) or (hour == 0) or (hour == 23)

        elif self.time_filter_mode == 'custom':
            # 사용자 정의 시간대
            return hour in self.allowed_hours

        # 기본: 24시간 거래
        return True