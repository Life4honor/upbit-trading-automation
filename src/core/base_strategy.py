"""
기본 전략 추상 클래스
모든 트레이딩 전략의 베이스
"""

from abc import ABC, abstractmethod
from typing import Dict, Tuple, Optional
from datetime import datetime
import pandas as pd
import numpy as np


class BaseStrategy(ABC):
    """
    트레이딩 전략 추상 클래스

    모든 전략은 이 클래스를 상속받아 구현
    - check_entry_conditions(): 매수 조건 체크
    - check_exit_conditions(): 매도 조건 체크
    """

    def __init__(self, config: Dict):
        """
        초기화

        Args:
            config: 전략 설정 딕셔너리
        """
        self.config = config

        # 공통 파라미터
        self.target_profit = config.get('target_profit', 1.0)
        self.stop_loss = config.get('stop_loss', -1.0)
        self.fee_rate = config.get('fee_rate', 0.05)
        self.cooldown_minutes = config.get('cooldown_minutes', 0)
        self.max_trades_per_day = config.get('max_trades_per_day', None)

        # 시간대 필터
        self.use_time_filter = config.get('use_time_filter', False)
        self.time_filter_mode = config.get('time_filter_mode', 'optimal')
        self.exclude_weekdays = config.get('exclude_weekdays', [])
        self.preferred_weekdays = config.get('preferred_weekdays', None)
        self.allowed_hours = config.get('allowed_hours', list(range(24)))

    @abstractmethod
    def check_entry_conditions(self, market_data: Dict) -> Tuple[bool, str]:
        """
        매수 조건 체크 (전략별 구현 필요)

        Args:
            market_data: 시장 데이터
                - current_price: 현재가
                - latest_candle: 최근 캔들 (open, high, low, close, volume)
                - rsi_5m, rsi_15m, rsi_1h: RSI 값들
                - sma_7, sma_25, sma_99: 이동평균선
                - volume_ma: 거래량 평균
                - bid_ask_ratio: 호가 비율
                - 기타 전략별 필요 데이터

        Returns:
            (진입 가능 여부, 사유)
        """
        pass

    @abstractmethod
    def check_exit_conditions(self, position: Dict, market_data: Dict,
                              holding_minutes: float) -> Tuple[bool, str, str]:
        """
        매도 조건 체크 (전략별 구현 필요)

        Args:
            position: 포지션 정보
                - entry_price: 진입가
                - entry_time: 진입 시간
                - quantity: 수량
                - 기타 전략별 저장 데이터
            market_data: 현재 시장 데이터
            holding_minutes: 보유 시간 (분)

        Returns:
            (청산 여부, 청산 유형, 사유)
            청산 유형: 'TAKE_PROFIT' 또는 'STOP_LOSS'
        """
        pass

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

    # ==========================================
    # 공통 기술 지표 계산 메서드
    # ==========================================

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
    def calculate_ema(prices: pd.Series, period: int) -> float:
        """지수이동평균 계산"""
        ema = prices.ewm(span=period, adjust=False).mean()
        return ema.iloc[-1] if len(ema) > 0 else prices.iloc[-1]

    @staticmethod
    def calculate_bollinger_bands(prices: pd.Series, period: int = 20,
                                   std_dev: float = 2.0) -> Tuple[float, float, float]:
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
    def calculate_bb_width(prices: pd.Series, period: int = 20,
                           std_dev: float = 2.0) -> float:
        """
        볼린저 밴드 폭 계산 (변동성 지표)

        Returns:
            BB Width = (Upper - Lower) / Middle * 100
        """
        upper, middle, lower = BaseStrategy.calculate_bollinger_bands(prices, period, std_dev)
        if middle > 0:
            return (upper - lower) / middle * 100
        return 0.0

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
        """
        ATR (Average True Range) 계산

        Args:
            df: OHLC 데이터프레임 (high, low, close 컬럼 필요)
            period: ATR 계산 기간

        Returns:
            ATR 값
        """
        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()

        return atr.iloc[-1] if len(atr) > 0 else 0.0

    @staticmethod
    def calculate_macd(prices: pd.Series, fast: int = 12, slow: int = 26,
                       signal: int = 9) -> Tuple[float, float, float]:
        """
        MACD 계산

        Returns:
            (macd, signal, histogram)
        """
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        histogram = macd - signal_line

        if len(macd) > 0:
            return macd.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]
        return 0.0, 0.0, 0.0

    @staticmethod
    def calculate_volatility(prices: pd.Series, period: int = 20) -> float:
        """
        변동성 계산 (표준편차)

        Returns:
            변동성 (%)
        """
        returns = prices.pct_change()
        volatility = returns.rolling(window=period).std() * 100
        return volatility.iloc[-1] if len(volatility) > 0 else 0.0

    def get_strategy_name(self) -> str:
        """전략 이름 반환"""
        return self.__class__.__name__
