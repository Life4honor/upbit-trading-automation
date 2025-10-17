"""
통합 트레이더 (백테스트 + 실거래)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
from pathlib import Path
import time
import requests

from .api import UpbitAPI
from .base_strategy import BaseStrategy
from .strategies import GridTradingStrategy


def create_strategy(config: Dict) -> BaseStrategy:
    """
    전략 팩토리: config의 strategy_type에 따라 전략 인스턴스 생성

    Args:
        config: 전략 설정 (strategy_type 포함)

    Returns:
        전략 인스턴스

    Raises:
        ValueError: 알 수 없는 전략 타입
    """
    strategy_type = config.get('strategy_type', 'grid_trading')

    strategy_map = {
        'grid_trading': GridTradingStrategy,
    }

    if strategy_type not in strategy_map:
        raise ValueError(f"알 수 없는 전략 타입: {strategy_type}. 사용 가능: grid_trading")

    return strategy_map[strategy_type](config)


class UnifiedTrader:
    """
    통합 트레이더
    - 백테스트: 과거 데이터로 시뮬레이션
    - 실거래: 실시간 자동매매
    """

    BASE_URL = "https://api.upbit.com/v1"

    def __init__(self, config: Dict, market: str, mode: str = 'backtest',
                 api: Optional[UpbitAPI] = None):
        """
        초기화

        Args:
            config: 전략 설정
            market: 마켓 코드 (예: 'KRW-BTC')
            mode: 'backtest' 또는 'live'
            api: UpbitAPI 인스턴스 (실거래 시 필요)
        """
        self.config = config
        self.market = market
        self.mode = mode
        self.api = api
        self.currency = market.split('-')[1]

        # 전략 (팩토리 패턴)
        self.strategy = create_strategy(config)

        # 자본 설정 (모드별 분리)
        if mode == 'backtest':
            # 백테스트: 100만원 고정
            self.initial_capital = 1_000_000
            self.capital = self.initial_capital
            # trade_amount: config에서 지정하거나, 초기 자본의 80%로 자동 계산
            self.trade_amount = config.get('trade_amount', int(self.initial_capital * 0.80))
        else:
            # 실거래: 업비트 API로 실제 자산 조회
            if not api:
                raise ValueError("실거래 모드는 UpbitAPI 인스턴스가 필요합니다")

            # 현재 KRW 잔고 조회
            krw_balance = api.get_balance('KRW')

            # 보유 중인 코인 가치 조회
            crypto_balance = api.get_balance(self.currency)
            if crypto_balance > 0:
                current_price = api.get_current_price(market)
                crypto_value = crypto_balance * current_price
            else:
                crypto_value = 0

            # 총 자산 = KRW 잔고 + 코인 가치
            total_balance = krw_balance + crypto_value

            self.initial_capital = total_balance
            self.capital = self.initial_capital

            # trade_amount: config에서 지정하거나, KRW 잔고의 80%로 자동 계산
            default_trade_amount = int(krw_balance * 0.80)
            self.trade_amount = min(
                config.get('trade_amount', default_trade_amount),
                int(krw_balance)  # KRW 잔고를 초과할 수 없음
            )
        
        # 상태
        self.positions = []  # 다중 포지션 관리 (그리드 트레이딩용)
        self.trades = []
        self.daily_stats = []
        self.today_trade_count = 0
        self.last_trade_time = None
        self.current_date = None
        self.is_running = False
        
        # 설정
        self.fee_rate = config.get('fee_rate', 0.05)
        self.check_interval = config.get('check_interval', 60)
        
        # ID
        now = datetime.now()
        self.session_id = now.strftime("%Y%m%d_%H%M%S")

        # 출력 디렉토리 (코인별/날짜별 구조)
        base_dir = Path("logs" if mode == 'live' else "backtest_reports")

        # 코인 이름 추출 (예: KRW-BTC -> BTC)
        coin_name = self.market.split('-')[1]

        # 날짜 디렉토리 구조: YYYY/MM/DD
        date_path = now.strftime("%Y/%m/%d")

        # 최종 경로: backtest_reports/BTC/2025/10/15/
        self.output_dir = base_dir / coin_name / date_path
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    # ==========================================
    # 데이터 수집 (공통)
    # ==========================================
    
    def fetch_candles(self, unit: int, count: int = 200, to: str = None) -> pd.DataFrame:
        """분봉 데이터 조회"""
        endpoint = f"{self.BASE_URL}/candles/minutes/{unit}"
        params = {'market': self.market, 'count': count}
        if to:
            params['to'] = to
        
        try:
            response = requests.get(endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                return pd.DataFrame()
            
            df = pd.DataFrame(data)
            df = df[['candle_date_time_kst', 'opening_price', 'high_price',
                     'low_price', 'trade_price', 'candle_acc_trade_volume']]
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601')
            df = df.set_index('timestamp').sort_index()

            return df
            
        except Exception as e:
            self.log(f"❌ 데이터 조회 오류: {e}")
            return pd.DataFrame()
    
    def fetch_bulk_data(self, unit: int, days: int) -> pd.DataFrame:
        """대량 데이터 수집 (백테스트용)"""
        self.log(f"📥 {unit}분봉 데이터 다운로드 중... ({days}일)")
        
        candles_per_day = (24 * 60) // unit
        total_candles = days * candles_per_day
        fetch_count = (total_candles // 200) + 1
        
        all_data = []
        to_time = None
        
        for i in range(fetch_count):
            df = self.fetch_candles(unit, count=200, to=to_time)
            if df.empty:
                break
            
            all_data.append(df)
            to_time = df.index[0].isoformat()
            
            progress = min(100, ((i + 1) / fetch_count) * 100)
            print(f"진행률: {progress:.0f}%", end='\r')
            
            time.sleep(0.11)  # API 제한
            
            if len(all_data) * 200 >= total_candles:
                break
        
        print()
        
        if not all_data:
            return pd.DataFrame()
        
        df = pd.concat(all_data)
        df = df[~df.index.duplicated(keep='first')].sort_index()
        self.log(f"✅ {len(df)}개 캔들 다운로드 완료")
        
        return df
    
    def analyze_market(self, data_5m: pd.DataFrame = None,
                       data_15m: pd.DataFrame = None,
                       data_1h: pd.DataFrame = None) -> Dict:
        """
        시장 분석
        백테스트: 기존 데이터 사용
        실거래: 실시간 데이터 조회
        """
        if self.mode == 'backtest':
            # 백테스트는 전달받은 데이터 사용
            current_price = data_5m.iloc[-1]['close']

            rsi_5m = self.strategy.calculate_rsi(data_5m['close'])
            rsi_15m = self.strategy.calculate_rsi(data_15m['close'])
            sma_7 = self.strategy.calculate_sma(data_5m['close'], 7)
            sma_25 = self.strategy.calculate_sma(data_5m['close'], 25)
            sma_99 = self.strategy.calculate_sma(data_5m['close'], 99)

            # 거래량 평균 (최근 20개 캔들)
            volume_ma = data_5m['volume'].tail(20).mean() if len(data_5m) >= 20 else 0

            # 볼린저 밴드 계산
            bb_upper, bb_middle, bb_lower = self.strategy.calculate_bollinger_bands(data_5m['close'], 20, 2.0)
            bb_width = self.strategy.calculate_bb_width(data_5m['close'], 20, 2.0)

            # ATR 계산 (그리드 트레이딩 등에서 사용)
            atr = self.strategy.calculate_atr(data_5m, period=14)
            # ATR 평균: 최근 20개 ATR 값의 평균 (간단하게)
            if len(data_5m) >= 34:  # 14 + 20
                atr_values = []
                for i in range(20):
                    start_idx = len(data_5m) - 34 + i
                    atr_val = self.strategy.calculate_atr(data_5m.iloc[start_idx:start_idx+14], period=14)
                    atr_values.append(atr_val)
                atr_ma = sum(atr_values) / len(atr_values)
            else:
                atr_ma = atr

            result = {
                'current_price': current_price,
                'timestamp': data_5m.index[-1],  # 현재 시각 추가 (그리드 재초기화용)
                'rsi_5m': rsi_5m,
                'rsi_15m': rsi_15m,
                'sma_7': sma_7,
                'sma_25': sma_25,
                'sma_99': sma_99,
                'bb_upper': bb_upper,
                'bb_middle': bb_middle,
                'bb_lower': bb_lower,
                'bb_width': bb_width,
                'atr': atr,
                'atr_ma': atr_ma,
                'latest_candle': data_5m.iloc[-1],
                'volume_ma': volume_ma,
                'active_positions': len(self.positions)  # 현재 보유 포지션 수 추가
            }

            # 1시간 봉 RSI 추가 (옵션)
            if data_1h is not None and not data_1h.empty:
                rsi_1h = self.strategy.calculate_rsi(data_1h['close'])
                result['rsi_1h'] = rsi_1h

            return result

        else:
            # 실거래는 실시간 데이터 조회
            data_5m = self.fetch_candles(5, 50)
            data_15m = self.fetch_candles(15, 50)
            data_1h = self.fetch_candles(60, 50)  # 1시간 봉 추가

            if data_5m.empty or data_15m.empty:
                return {'error': '데이터 없음'}

            current_price = self.api.get_current_price(self.market)

            rsi_5m = self.strategy.calculate_rsi(data_5m['close'])
            rsi_15m = self.strategy.calculate_rsi(data_15m['close'])
            sma_7 = self.strategy.calculate_sma(data_5m['close'], 7)
            sma_25 = self.strategy.calculate_sma(data_5m['close'], 25)
            sma_99 = self.strategy.calculate_sma(data_5m['close'], 99)

            # 거래량 평균
            volume_ma = data_5m['volume'].tail(20).mean() if len(data_5m) >= 20 else 0

            # 볼린저 밴드 계산
            bb_upper, bb_middle, bb_lower = self.strategy.calculate_bollinger_bands(data_5m['close'], 20, 2.0)
            bb_width = self.strategy.calculate_bb_width(data_5m['close'], 20, 2.0)

            # ATR 계산 (그리드 트레이딩 등에서 사용)
            atr = self.strategy.calculate_atr(data_5m, period=14)
            # ATR 평균: 최근 20개 ATR 값의 평균 (간단하게)
            if len(data_5m) >= 34:  # 14 + 20
                atr_values = []
                for i in range(20):
                    start_idx = len(data_5m) - 34 + i
                    atr_val = self.strategy.calculate_atr(data_5m.iloc[start_idx:start_idx+14], period=14)
                    atr_values.append(atr_val)
                atr_ma = sum(atr_values) / len(atr_values)
            else:
                atr_ma = atr

            # 호가 비율 (매수세/매도세)
            try:
                orderbook = self.api.get_orderbook(self.market)
                if orderbook:
                    bid_volume = sum([item['size'] for item in orderbook['orderbook_units'][:5]])
                    ask_volume = sum([item['size'] for item in orderbook['orderbook_units'][:5]])
                    bid_ask_ratio = bid_volume / ask_volume if ask_volume > 0 else 1.0
                else:
                    bid_ask_ratio = None
            except:
                bid_ask_ratio = None

            result = {
                'current_price': current_price,
                'timestamp': datetime.now(),  # 현재 시각 추가 (그리드 재초기화용)
                'rsi_5m': rsi_5m,
                'rsi_15m': rsi_15m,
                'sma_7': sma_7,
                'sma_25': sma_25,
                'sma_99': sma_99,
                'bb_upper': bb_upper,
                'bb_middle': bb_middle,
                'bb_lower': bb_lower,
                'bb_width': bb_width,
                'atr': atr,
                'atr_ma': atr_ma,
                'latest_candle': data_5m.iloc[-1],
                'volume_ma': volume_ma,
                'active_positions': len(self.positions)  # 현재 보유 포지션 수 추가
            }

            # 1시간 봉 RSI 추가
            if not data_1h.empty:
                rsi_1h = self.strategy.calculate_rsi(data_1h['close'])
                result['rsi_1h'] = rsi_1h

            if bid_ask_ratio is not None:
                result['bid_ask_ratio'] = bid_ask_ratio

            return result
    
    # ==========================================
    # 거래 제어 (공통)
    # ==========================================
    
    def can_trade(self, timestamp: datetime) -> bool:
        """거래 가능 여부"""
        if self.current_date != timestamp.date():
            self.current_date = timestamp.date()
            self.today_trade_count = 0

        # None = 무제한 거래
        if self.strategy.max_trades_per_day is not None:
            if self.today_trade_count >= self.strategy.max_trades_per_day:
                return False

        if self.last_trade_time:
            elapsed = (timestamp - self.last_trade_time).total_seconds() / 60
            if elapsed < self.strategy.cooldown_minutes:
                return False

        return True
    
    def execute_buy(self, analysis: Dict, timestamp: datetime) -> bool:
        """매수 실행 (동적 목표 수익률 적용)"""
        if self.mode == 'backtest':
            # 시뮬레이션 매수
            entry_price = analysis['current_price']

            # 그리드 트레이딩용 자본 분산
            strategy_type = self.config.get('strategy_type', 'scalping')
            if strategy_type == 'grid_trading':
                max_positions = self.config.get('max_positions', 3)
                position_amount = self.trade_amount / max_positions  # 자본을 max_positions로 분할
                amount = min(self.capital, position_amount)
            else:
                # 기존 전략은 전액 사용
                amount = min(self.capital, self.trade_amount)

            fee = amount * (self.fee_rate / 100)

            # 동적 목표 수익률 계산 (전략이 지원하는 경우만)
            dynamic_target = None
            if hasattr(self.strategy, 'calculate_dynamic_target'):
                dynamic_target = self.strategy.calculate_dynamic_target(analysis)

            # 호가 데이터 계산
            bid_ask_ratio = analysis.get('bid_ask_ratio')
            total_bid_size = analysis.get('total_bid_size', 0)
            total_ask_size = analysis.get('total_ask_size', 0)
            bid_imbalance = None
            if total_bid_size + total_ask_size > 0:
                bid_imbalance = total_bid_size / (total_bid_size + total_ask_size)

            # 그리드 레벨 정보 저장 (그리드 트레이딩용)
            entry_grid_level = -1
            if strategy_type == 'grid_trading' and hasattr(self.strategy, 'get_nearest_grid_level'):
                entry_grid_level, _ = self.strategy.get_nearest_grid_level(entry_price)

            position = {
                'entry_time': timestamp,
                'entry_price': entry_price,
                'entry_rsi_5m': analysis['rsi_5m'],
                'entry_rsi_15m': analysis['rsi_15m'],
                'entry_rsi_1h': analysis.get('rsi_1h'),
                'entry_sma_7': analysis.get('sma_7'),
                'entry_sma_25': analysis.get('sma_25'),
                'entry_sma_99': analysis.get('sma_99'),
                'entry_volume': analysis['latest_candle']['volume'] if 'latest_candle' in analysis else None,
                'entry_volume_ma': analysis.get('volume_ma'),
                'entry_volume_surge_ratio': (analysis['latest_candle']['volume'] / analysis['volume_ma']) if 'volume_ma' in analysis and analysis['volume_ma'] > 0 else None,
                'entry_bid_ask_ratio': bid_ask_ratio,
                'entry_bid_imbalance': bid_imbalance,
                'amount': amount - fee,
                'quantity': (amount - fee) / entry_price,
                'fee': fee,
                'target_profit': dynamic_target,  # 동적 목표 저장
                'entry_grid_level': entry_grid_level  # 그리드 레벨 정보
            }

            # 다중 포지션 관리
            self.positions.append(position)

            self.capital -= amount
            self.today_trade_count += 1
            self.last_trade_time = timestamp

            target_info = f"목표: {dynamic_target:.2f}%" if dynamic_target is not None else ""
            position_count = len(self.positions)
            self.log(f"✅ 매수 #{position_count}: ₩{entry_price:,.0f} (수량: {position['quantity']:.8f}) {target_info}")
            return True

        else:
            # 실제 매수
            krw_balance = self.api.get_balance('KRW')

            # 그리드 트레이딩용 자본 분산
            strategy_type = self.config.get('strategy_type', 'scalping')
            if strategy_type == 'grid_trading':
                max_positions = self.config.get('max_positions', 3)
                position_amount = self.trade_amount / max_positions  # 자본을 max_positions로 분할
                buy_amount = min(krw_balance, position_amount)
            else:
                # 기존 전략은 전액 사용
                buy_amount = min(krw_balance, self.trade_amount)

            if krw_balance < buy_amount:
                self.log(f"⚠️ 잔고 부족: ₩{krw_balance:,.0f}")
                return False

            self.log(f"🔵 매수 시도: {self.market} @ ₩{analysis['current_price']:,.0f} (₩{buy_amount:,.0f})")

            result = self.api.buy_market(self.market, buy_amount)

            if result:
                # 동적 목표 수익률 계산 (전략이 지원하는 경우만)
                dynamic_target = None
                if hasattr(self.strategy, 'calculate_dynamic_target'):
                    dynamic_target = self.strategy.calculate_dynamic_target(analysis)

                # 호가 데이터 계산
                bid_ask_ratio = analysis.get('bid_ask_ratio')
                total_bid_size = analysis.get('total_bid_size', 0)
                total_ask_size = analysis.get('total_ask_size', 0)
                bid_imbalance = None
                if total_bid_size + total_ask_size > 0:
                    bid_imbalance = total_bid_size / (total_bid_size + total_ask_size)

                # 그리드 레벨 정보 저장 (그리드 트레이딩용)
                entry_price = analysis['current_price']
                entry_grid_level = -1
                if strategy_type == 'grid_trading' and hasattr(self.strategy, 'get_nearest_grid_level'):
                    entry_grid_level, _ = self.strategy.get_nearest_grid_level(entry_price)

                position = {
                    'entry_time': timestamp,
                    'entry_price': entry_price,
                    'entry_rsi_5m': analysis['rsi_5m'],
                    'entry_rsi_15m': analysis['rsi_15m'],
                    'entry_rsi_1h': analysis.get('rsi_1h'),
                    'entry_sma_7': analysis.get('sma_7'),
                    'entry_sma_25': analysis.get('sma_25'),
                    'entry_sma_99': analysis.get('sma_99'),
                    'entry_volume': analysis['latest_candle']['volume'] if 'latest_candle' in analysis else None,
                    'entry_volume_ma': analysis.get('volume_ma'),
                    'entry_volume_surge_ratio': (analysis['latest_candle']['volume'] / analysis['volume_ma']) if 'volume_ma' in analysis and analysis['volume_ma'] > 0 else None,
                    'entry_bid_ask_ratio': bid_ask_ratio,
                    'entry_bid_imbalance': bid_imbalance,
                    'amount': buy_amount,
                    'order_id': result.get('uuid'),
                    'target_profit': dynamic_target,  # 동적 목표 저장
                    'entry_grid_level': entry_grid_level  # 그리드 레벨 정보
                }

                # 다중 포지션 관리
                self.positions.append(position)

                self.today_trade_count += 1
                self.last_trade_time = timestamp

                target_info = f"목표: {dynamic_target:.2f}%" if dynamic_target is not None else ""
                position_count = len(self.positions)
                self.log(f"✅ 매수 #{position_count}: ₩{entry_price:,.0f} (금액: ₩{buy_amount:,.0f}) {target_info}")
                return True

            return False
    
    def execute_sell(self, analysis: Dict, timestamp: datetime, reason: str, position_idx: int = 0) -> bool:
        """
        매도 실행

        Args:
            analysis: 시장 데이터
            timestamp: 현재 시각
            reason: 청산 사유
            position_idx: 청산할 포지션 인덱스 (기본값 0 = 첫 번째 포지션)
        """
        if self.mode == 'backtest':
            # 포지션 없으면 종료
            if not self.positions or position_idx >= len(self.positions):
                return False

            position = self.positions[position_idx]

            # 시뮬레이션 매도
            exit_price = analysis['current_price']
            sell_amount = position['quantity'] * exit_price
            fee = sell_amount * (self.fee_rate / 100)
            net_amount = sell_amount - fee

            profit = net_amount - position['amount']
            profit_rate = (profit / position['amount']) * 100
            holding_time = (timestamp - position['entry_time']).total_seconds() / 60

            self.capital += net_amount

            # 호가 데이터 계산 (매도 시)
            bid_ask_ratio = analysis.get('bid_ask_ratio')
            total_bid_size = analysis.get('total_bid_size', 0)
            total_ask_size = analysis.get('total_ask_size', 0)
            bid_imbalance = None
            if total_bid_size + total_ask_size > 0:
                bid_imbalance = total_bid_size / (total_bid_size + total_ask_size)

            trade = {
                'timestamp': timestamp,
                'entry_time': position['entry_time'],
                'entry_price': position['entry_price'],
                'exit_price': exit_price,
                'profit': profit,
                'profit_rate': profit_rate,
                'holding_time': holding_time,
                'reason': reason,
                # 매수 시점 데이터
                'entry_rsi_5m': position.get('entry_rsi_5m', position.get('entry_rsi')),  # 하위 호환성
                'entry_rsi_15m': position.get('entry_rsi_15m'),
                'entry_rsi_1h': position.get('entry_rsi_1h'),
                'entry_sma_7': position.get('entry_sma_7'),
                'entry_sma_25': position.get('entry_sma_25'),
                'entry_sma_99': position.get('entry_sma_99'),
                'entry_volume': position.get('entry_volume'),
                'entry_volume_ma': position.get('entry_volume_ma'),
                'entry_volume_surge_ratio': position.get('entry_volume_surge_ratio'),
                'entry_bid_ask_ratio': position.get('entry_bid_ask_ratio'),
                'entry_bid_imbalance': position.get('entry_bid_imbalance'),
                # 매도 시점 데이터
                'exit_rsi_5m': analysis['rsi_5m'],
                'exit_rsi_15m': analysis.get('rsi_15m'),
                'exit_rsi_1h': analysis.get('rsi_1h'),
                'exit_sma_7': analysis.get('sma_7'),
                'exit_sma_25': analysis.get('sma_25'),
                'exit_sma_99': analysis.get('sma_99'),
                'exit_volume': analysis['latest_candle']['volume'] if 'latest_candle' in analysis else None,
                'exit_volume_ma': analysis.get('volume_ma'),
                'exit_volume_surge_ratio': (analysis['latest_candle']['volume'] / analysis['volume_ma']) if 'volume_ma' in analysis and analysis['volume_ma'] > 0 else None,
                'exit_bid_ask_ratio': bid_ask_ratio,
                'exit_bid_imbalance': bid_imbalance,
                # 목표 수익률
                'target_profit': position.get('target_profit')
            }

            self.trades.append(trade)
            self.update_daily_stats(timestamp.date(), trade)

            # 해당 포지션 제거
            self.positions.pop(position_idx)
            self.last_trade_time = timestamp

            remaining_positions = len(self.positions)
            self.log(f"✅ 매도 #{position_idx+1}: ₩{exit_price:,.0f} | {profit_rate:+.2f}% (₩{profit:+,.0f}) | {reason} (잔여: {remaining_positions})")
            return True

        else:
            # 실제 매도
            # 포지션 없으면 종료
            if not self.positions or position_idx >= len(self.positions):
                self.log(f"⚠️ 포지션 없음")
                return False

            position = self.positions[position_idx]

            position_info = self.api.get_position(self.market)

            if not position_info or position_info['balance'] == 0:
                self.log(f"⚠️ 보유량 없음")
                # 포지션 정보와 실제 잔고 불일치 시 포지션 제거
                self.positions.pop(position_idx)
                return False

            # 실거래에서는 전량 매도 (부분 매도는 복잡하므로 단순화)
            volume = position_info['balance']

            self.log(f"🔴 매도 시도 #{position_idx+1}: {volume:.8f} ({reason})")

            result = self.api.sell_market(self.market, volume)

            if result:
                entry_price = position['entry_price']
                exit_price = analysis['current_price']
                profit_rate = (exit_price - entry_price) / entry_price * 100
                profit_amount = (exit_price - entry_price) * volume
                holding_time = (timestamp - position['entry_time']).total_seconds() / 60

                # 호가 데이터 계산 (매도 시)
                bid_ask_ratio = analysis.get('bid_ask_ratio')
                total_bid_size = analysis.get('total_bid_size', 0)
                total_ask_size = analysis.get('total_ask_size', 0)
                bid_imbalance = None
                if total_bid_size + total_ask_size > 0:
                    bid_imbalance = total_bid_size / (total_bid_size + total_ask_size)

                trade = {
                    'timestamp': timestamp,
                    'entry_time': position['entry_time'],
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'profit': profit_amount,
                    'profit_rate': profit_rate,
                    'holding_time': holding_time,
                    'reason': reason,
                    'order_id': result.get('uuid'),
                    # 매수 시점 데이터
                    'entry_rsi_5m': position.get('entry_rsi_5m', position.get('entry_rsi')),  # 하위 호환성
                    'entry_rsi_15m': position.get('entry_rsi_15m'),
                    'entry_rsi_1h': position.get('entry_rsi_1h'),
                    'entry_sma_7': position.get('entry_sma_7'),
                    'entry_sma_25': position.get('entry_sma_25'),
                    'entry_sma_99': position.get('entry_sma_99'),
                    'entry_volume': position.get('entry_volume'),
                    'entry_volume_ma': position.get('entry_volume_ma'),
                    'entry_volume_surge_ratio': position.get('entry_volume_surge_ratio'),
                    'entry_bid_ask_ratio': position.get('entry_bid_ask_ratio'),
                    'entry_bid_imbalance': position.get('entry_bid_imbalance'),
                    # 매도 시점 데이터
                    'exit_rsi_5m': analysis['rsi_5m'],
                    'exit_rsi_15m': analysis.get('rsi_15m'),
                    'exit_rsi_1h': analysis.get('rsi_1h'),
                    'exit_sma_7': analysis.get('sma_7'),
                    'exit_sma_25': analysis.get('sma_25'),
                    'exit_sma_99': analysis.get('sma_99'),
                    'exit_volume': analysis['latest_candle']['volume'] if 'latest_candle' in analysis else None,
                    'exit_volume_ma': analysis.get('volume_ma'),
                    'exit_volume_surge_ratio': (analysis['latest_candle']['volume'] / analysis['volume_ma']) if 'volume_ma' in analysis and analysis['volume_ma'] > 0 else None,
                    'exit_bid_ask_ratio': bid_ask_ratio,
                    'exit_bid_imbalance': bid_imbalance,
                    # 목표 수익률
                    'target_profit': position.get('target_profit')
                }

                self.trades.append(trade)
                self.update_daily_stats(timestamp.date(), trade)

                # 해당 포지션 제거
                self.positions.pop(position_idx)
                self.last_trade_time = timestamp

                remaining_positions = len(self.positions)
                self.log(f"✅ 매도 #{position_idx+1}: ₩{exit_price:,.0f} | {profit_rate:+.2f}% (₩{profit_amount:+,.0f}) | {reason} (잔여: {remaining_positions})")
                return True

            return False
    
    # ==========================================
    # 백테스트
    # ==========================================
    
    def run_backtest(self, days: int = 7) -> Dict:
        """백테스트 실행"""
        self.log("=" * 60)
        self.log(f"🚀 백테스트: {self.market} ({days}일)")
        self.log("=" * 60)
        
        # 데이터 수집
        data_5m = self.fetch_bulk_data(5, days)
        if data_5m.empty:
            return {'error': '5분봉 데이터 없음'}
        
        data_15m = self.fetch_bulk_data(15, days)
        if data_15m.empty:
            return {'error': '15분봉 데이터 없음'}
        
        data_1h = self.fetch_bulk_data(60, days)
        if data_1h.empty:
            return {'error': '1시간봉 데이터 없음'}

        self.log(f"📊 기간: {data_5m.index[0]} ~ {data_5m.index[-1]}")

        # 지표 계산
        self.log("📈 기술적 지표 계산 중...")
        data_5m['rsi'] = data_5m['close'].rolling(14).apply(
            lambda x: self.strategy.calculate_rsi(x) if len(x) == 14 else np.nan
        )
        data_15m['rsi'] = data_15m['close'].rolling(14).apply(
            lambda x: self.strategy.calculate_rsi(x) if len(x) == 14 else np.nan
        )
        data_1h['rsi'] = data_1h['close'].rolling(14).apply(
            lambda x: self.strategy.calculate_rsi(x) if len(x) == 14 else np.nan
        )

        # 15분봉 및 1시간봉 RSI를 5분봉에 병합
        data_5m = data_5m.join(data_15m[['rsi']].rename(columns={'rsi': 'rsi_15m'}), how='left')
        data_5m = data_5m.join(data_1h[['rsi']].rename(columns={'rsi': 'rsi_1h'}), how='left')
        data_5m['rsi_15m'] = data_5m['rsi_15m'].ffill()
        data_5m['rsi_1h'] = data_5m['rsi_1h'].ffill()
        data_5m = data_5m.dropna()
        
        self.log(f"✅ 유효 데이터: {len(data_5m):,}개")
        
        # 시뮬레이션
        self.log("🔄 거래 시뮬레이션...")

        # 디버그: 조건 실패 카운트
        condition_failures = {}
        check_count = 0

        for idx in range(len(data_5m)):
            if idx % 100 == 0:
                print(f"{idx:,}/{len(data_5m):,}", end='\r')

            timestamp = data_5m.index[idx]

            if not self.strategy.is_trading_hours(timestamp):
                continue

            # 현재까지 데이터로 분석
            current_5m = data_5m.iloc[:idx+1]
            current_15m = data_15m[data_15m.index <= timestamp]
            current_1h = data_1h[data_1h.index <= timestamp]

            if len(current_5m) < 30 or len(current_15m) < 30:
                continue

            analysis = self.analyze_market(current_5m, current_15m, current_1h)

            # 포지션 보유 중 - 각 포지션 개별 체크 (역순으로 순회하여 안전하게 삭제)
            for i in range(len(self.positions) - 1, -1, -1):
                position = self.positions[i]
                holding_minutes = (timestamp - position['entry_time']).total_seconds() / 60
                should_sell, _, reason = self.strategy.check_exit_conditions(
                    position, analysis, holding_minutes
                )

                if should_sell:
                    self.execute_sell(analysis, timestamp, reason, position_idx=i)

            # 추가 매수 가능 여부 체크
            if self.can_trade(timestamp):
                check_count += 1
                should_buy, reason = self.strategy.check_entry_conditions(analysis)

                if should_buy:
                    self.execute_buy(analysis, timestamp)
                else:
                    # 실패 이유 카운트
                    if reason not in condition_failures:
                        condition_failures[reason] = 0
                    condition_failures[reason] += 1
        
        print()

        # 디버그: 조건 실패 통계 출력
        if check_count > 0:
            self.log("=" * 60)
            self.log(f"📊 매수 조건 체크: {check_count:,}회")
            self.log("=" * 60)
            if condition_failures:
                # 실패 이유별 정렬
                sorted_failures = sorted(condition_failures.items(), key=lambda x: x[1], reverse=True)
                for reason, count in sorted_failures:
                    percentage = (count / check_count) * 100
                    self.log(f"  {reason}: {count:,}회 ({percentage:.1f}%)")
            self.log("=" * 60)

        # 미청산 포지션 전량 청산
        if self.positions:
            self.log(f"⚠️ 미청산 포지션 {len(self.positions)}개 청산")
            analysis = self.analyze_market(data_5m, data_15m, data_1h)
            # 역순으로 청산
            for i in range(len(self.positions) - 1, -1, -1):
                self.execute_sell(analysis, data_5m.index[-1], "기간 종료", position_idx=i)

        # 결과 분석
        results = self.analyze_results(days)
        self.save_results(results)

        return results
    
    # ==========================================
    # 실거래
    # ==========================================
    
    def _log_grid_trading(self, analysis: Dict, timestamp: datetime):
        """그리드 트레이딩 전략용 로그"""
        current_price = analysis['current_price']

        # 다중 포지션 정보
        position_info = ""
        if self.positions:
            total_profit_rate = 0
            avg_entry_price = 0

            for pos in self.positions:
                avg_entry_price += pos['entry_price']
                profit_rate = (current_price - pos['entry_price']) / pos['entry_price'] * 100
                total_profit_rate += profit_rate

            avg_entry_price /= len(self.positions)
            avg_profit_rate = total_profit_rate / len(self.positions)
            profit_emoji = "📈" if avg_profit_rate > 0 else "📉"

            position_info = f" | 포지션: {len(self.positions)}개 | {profit_emoji} 평균 {avg_profit_rate:+.2f}% (평단: ₩{avg_entry_price:,.0f})"

        # ATR 정보
        atr_info = ""
        if 'atr' in analysis and 'atr_ma' in analysis:
            atr = analysis['atr']
            atr_ma = analysis['atr_ma']
            if atr_ma > 0:
                atr_ratio = atr / atr_ma
                atr_emoji = "🟢" if atr_ratio < 0.8 else "🟡" if atr_ratio < 1.2 else "🔴"
                atr_info = f" | {atr_emoji} ATR {atr_ratio:.2f}x"

        # 볼린저 밴드 정보
        bb_info = ""
        if 'bb_upper' in analysis and 'bb_lower' in analysis:
            bb_upper = analysis['bb_upper']
            bb_lower = analysis['bb_lower']
            bb_position = (current_price - bb_lower) / (bb_upper - bb_lower) * 100
            bb_width_pct = (bb_upper - bb_lower) / current_price * 100
            bb_info = f" | BB {bb_position:.0f}% (폭: {bb_width_pct:.1f}%)"

        # 그리드 정보
        grid_info = ""
        if hasattr(self.strategy, 'grid_prices') and self.strategy.grid_prices:
            grid_count = len(self.strategy.grid_prices)
            min_grid = min(self.strategy.grid_prices)
            max_grid = max(self.strategy.grid_prices)
            grid_position = (current_price - min_grid) / (max_grid - min_grid) * 100
            grid_info = f" | 그리드: {grid_position:.0f}% ({grid_count}단계)"

        self.log(
            f"📊 ₩{current_price:,.0f}{position_info}{atr_info}{bb_info}{grid_info}"
        )

    def _log_scalping(self, analysis: Dict, timestamp: datetime):
        """RSI 스캘핑 등 기존 전략용 로그"""
        current_price = analysis['current_price']

        # 포지션 정보 (기존 전략은 단일 포지션)
        position_info = ""
        if self.positions:
            # 첫 번째 포지션만 표시 (기존 전략과의 호환성)
            position = self.positions[0]
            entry_price = position['entry_price']
            profit_rate = (current_price - entry_price) / entry_price * 100
            profit_emoji = "📈" if profit_rate > 0 else "📉"
            holding_time = (timestamp - position['entry_time']).total_seconds() / 60
            position_info = f" | {profit_emoji} {profit_rate:+.2f}% (평단 ₩{entry_price:,.0f}) | 보유 {holding_time:.0f}분"

        # 이동평균선 정보
        sma_info = ""
        if 'sma_7' in analysis and 'sma_25' in analysis:
            sma_7 = analysis['sma_7']
            sma_25 = analysis['sma_25']
            price_vs_sma7 = (current_price - sma_7) / sma_7 * 100
            price_vs_sma25 = (current_price - sma_25) / sma_25 * 100
            sma_info = f" | SMA7 {price_vs_sma7:+.1f}% | SMA25 {price_vs_sma25:+.1f}%"

        # 1시간봉 RSI 정보
        rsi_1h_info = ""
        if 'rsi_1h' in analysis:
            rsi_1h_info = f" | RSI 1h: {analysis['rsi_1h']:.1f}"

        # 호가 비율 정보
        orderbook_info = ""
        if 'bid_ask_ratio' in analysis:
            ratio = analysis['bid_ask_ratio']
            ratio_emoji = "🔵" if ratio > 1.0 else "🔴"
            orderbook_info = f" | {ratio_emoji} 호가 {ratio:.2f}"

        self.log(
            f"📊 ₩{current_price:,.0f}{position_info} | "
            f"RSI 5m: {analysis['rsi_5m']:.1f} | "
            f"RSI 15m: {analysis['rsi_15m']:.1f}{rsi_1h_info}{sma_info}{orderbook_info}"
        )

    def run_live(self):
        """실거래 실행"""
        if not self.api:
            raise ValueError("실거래 모드는 UpbitAPI 인스턴스가 필요합니다")

        self.is_running = True
        self.log("=" * 60)
        self.log(f"🤖 자동매매 시작: {self.market}")
        self.log("=" * 60)

        # 현재 자산 정보 출력
        krw_balance = self.api.get_balance('KRW')
        crypto_balance = self.api.get_balance(self.currency)
        if crypto_balance > 0:
            current_price = self.api.get_current_price(self.market)
            crypto_value = crypto_balance * current_price
            self.log(f"💰 KRW 잔고: ₩{krw_balance:,.0f}")
            self.log(f"💎 {self.currency} 보유: {crypto_balance:.8f} (₩{crypto_value:,.0f})")
            self.log(f"💵 총 자산: ₩{self.initial_capital:,.0f}")
        else:
            self.log(f"💰 KRW 잔고: ₩{krw_balance:,.0f}")
            self.log(f"💵 총 자산: ₩{self.initial_capital:,.0f}")

        self.log(f"🎯 거래 금액: ₩{self.trade_amount:,.0f}")
        self.log(f"⏱️ 체크 주기: {self.check_interval}초")
        self.log("=" * 60)
        self.log("Ctrl+C로 중지")
        
        try:
            while self.is_running:
                timestamp = datetime.now()
                
                # 시장 분석
                analysis = self.analyze_market()
                
                if 'error' in analysis:
                    self.log(f"⚠️ 분석 실패: {analysis['error']}")
                    time.sleep(self.check_interval)
                    continue
                
                # 전략별 로그 표시
                strategy_type = self.strategy.config.get('strategy_type', 'scalping')

                if strategy_type == 'grid_trading':
                    # 그리드 트레이딩 전용 로그
                    self._log_grid_trading(analysis, timestamp)
                else:
                    # 기존 RSI 스캘핑 등 다른 전략용 로그
                    self._log_scalping(analysis, timestamp)
                
                # 포지션 보유 중 - 각 포지션 개별 체크 (역순으로 순회하여 안전하게 삭제)
                for i in range(len(self.positions) - 1, -1, -1):
                    position = self.positions[i]
                    holding_minutes = (timestamp - position['entry_time']).total_seconds() / 60
                    should_sell, _, reason = self.strategy.check_exit_conditions(
                        position, analysis, holding_minutes
                    )

                    if should_sell:
                        self.execute_sell(analysis, timestamp, reason, position_idx=i)

                # 추가 매수 가능 여부 체크
                if self.can_trade(timestamp):
                    should_buy, _ = self.strategy.check_entry_conditions(analysis)

                    if should_buy:
                        self.execute_buy(analysis, timestamp)
                
                # 대기
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            self.log("")
            self.log("⚠️ 사용자 중지")
        
        finally:
            self.stop()
    
    def stop(self):
        """자동매매 중지"""
        self.is_running = False

        if self.positions:
            self.log(f"⚠️ 포지션 {len(self.positions)}개가 남아있습니다. 수동 정리 필요")

        self.log("=" * 60)
        self.log("🛑 종료")
        self.log(f"거래: {len(self.trades)}회 (오늘: {self.today_trade_count}회)")

        # 결과 저장 및 요약 출력
        if self.trades:
            results = self.analyze_results()

            # 결과 요약 (백테스트와 동일한 형식)
            self.log("=" * 60)
            self.log("📊 실거래 결과 요약")
            self.log("=" * 60)
            self.log(f"승률: {results['win_rate']:.1f}%")
            self.log(f"수익률: {results['total_profit_rate']:+.2f}%")
            self.log(f"거래: {results['total_trades']}회")
            self.log(f"MDD: {results['max_drawdown']:.2f}%")
            self.log(f"샤프: {results['sharpe_ratio']:.2f}")
            self.log("=" * 60)

            self.save_results(results)

        self.log("=" * 60)
    
    # ==========================================
    # 분석 및 리포트 (공통)
    # ==========================================
    
    def update_daily_stats(self, date, trade):
        """일일 통계"""
        stat = next((s for s in self.daily_stats if s['date'] == date), None)
        if not stat:
            stat = {'date': date, 'trades': 0, 'wins': 0, 'losses': 0, 'total_profit': 0}
            self.daily_stats.append(stat)
        
        stat['trades'] += 1
        if trade['profit_rate'] > 0:
            stat['wins'] += 1
        else:
            stat['losses'] += 1
        stat['total_profit'] += trade['profit_rate']
    
    def analyze_results(self, days: int = None) -> Dict:
        """결과 분석"""
        if not self.trades:
            return {'error': '거래 없음', 'total_trades': 0}

        df = pd.DataFrame(self.trades)

        total = len(df)
        wins = len(df[df['profit_rate'] > 0])
        losses = total - wins
        win_rate = (wins / total) * 100

        total_profit = df['profit'].sum()

        # 수익률 계산: 백테스트와 라이브 모두 동일한 방식으로
        if self.mode == 'backtest':
            # 백테스트: 최종 자본 기준
            total_rate = ((self.capital - self.initial_capital) / self.initial_capital) * 100
            final_capital = self.capital
        else:
            # 라이브: 실제 잔고 조회
            try:
                krw_balance = self.api.get_balance('KRW')
                crypto_balance = self.api.get_balance(self.currency)
                current_price = self.api.get_current_price(self.market)
                crypto_value = crypto_balance * current_price if crypto_balance else 0
                final_capital = krw_balance + crypto_value
            except Exception as e:
                # API 조회 실패 시 초기 자본 + 누적 손익으로 폴백
                self.log(f"⚠️ 잔고 조회 실패, 추정값 사용: {e}")
                final_capital = self.initial_capital + total_profit

            total_rate = ((final_capital - self.initial_capital) / self.initial_capital) * 100
        
        # MDD
        cum = df['profit'].cumsum()
        mdd = ((cum - cum.cummax()) / self.initial_capital * 100).min()
        
        # 샤프
        sharpe = (df['profit_rate'].mean() / df['profit_rate'].std() 
                 if df['profit_rate'].std() > 0 else 0)
        
        daily_df = pd.DataFrame(self.daily_stats) if self.daily_stats else pd.DataFrame()
        
        return {
            'mode': self.mode,
            'market': self.market,
            'session_id': self.session_id,
            'timestamp': datetime.now().isoformat(),
            'backtest_days': days,
            'config': self.config,
            'initial_capital': self.initial_capital,
            'final_capital': final_capital,
            'total_profit': total_profit,
            'total_profit_rate': total_rate,
            'total_trades': total,
            'winning_trades': wins,
            'losing_trades': losses,
            'win_rate': win_rate,
            'avg_profit_rate': df['profit_rate'].mean(),
            'avg_win': df[df['profit_rate']>0]['profit_rate'].mean() if wins>0 else 0,
            'avg_loss': df[df['profit_rate']<=0]['profit_rate'].mean() if losses>0 else 0,
            'max_drawdown': mdd,
            'sharpe_ratio': sharpe,
            'avg_holding_time': df['holding_time'].mean(),
            'avg_trades_per_day': daily_df['trades'].mean() if len(daily_df)>0 else 0,
            'profitable_days': len(daily_df[daily_df['total_profit']>0]) if len(daily_df)>0 else 0,
            'total_days': len(daily_df) if len(daily_df)>0 else 1,
            'trades': self.trades,
            'daily_stats': self.daily_stats
        }
    
    def save_results(self, results: Dict):
        """결과 저장 (JSON + Markdown)"""
        self.log("💾 결과 저장 중...")

        # 거래 없음 처리
        if 'error' in results:
            self.log(f"⚠️ {results['error']}")
            return

        prefix = "backtest" if self.mode == 'backtest' else "live"

        # JSON
        json_file = self.output_dir / f"{self.market}_{prefix}_{self.session_id}.json"
        json_data = results.copy()
        json_data['trades'] = [self._serialize(t) for t in json_data.get('trades', [])]
        json_data['daily_stats'] = [self._serialize(d) for d in json_data.get('daily_stats', [])]

        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        
        self.log(f"✅ JSON: {json_file.name}")
        
        # Markdown
        md_file = self.output_dir / f"{self.market}_{prefix}_{self.session_id}.md"
        md_content = self._generate_markdown(results)
        
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        self.log(f"✅ 리포트: {md_file.name}")
        
        # CSV (거래 내역)
        if results['trades']:
            csv_file = self.output_dir / f"{self.market}_{prefix}_{self.session_id}.csv"
            pd.DataFrame(results['trades']).to_csv(csv_file, index=False, encoding='utf-8-sig')
            self.log(f"✅ CSV: {csv_file.name}")
    
    def _generate_markdown(self, results: Dict) -> str:
        """마크다운 리포트 생성"""
        mode_str = "백테스트" if self.mode == 'backtest' else "실거래"
        
        md = [f"# 📊 {self.market} {mode_str} 결과"]
        md.append("")
        md.append(f"**모드**: {mode_str}")
        md.append(f"**세션 ID**: `{self.session_id}`")
        md.append(f"**생성**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if self.mode == 'backtest':
            md.append(f"**기간**: {results.get('backtest_days', 'N/A')}일")
        md.append("")
        md.append("---")
        md.append("")
        
        # 수익 요약
        md.append("## 💰 수익 요약")
        md.append("")
        md.append("| 항목 | 값 |")
        md.append("|------|------|")
        md.append(f"| 초기 자본 | ₩{results['initial_capital']:,.0f} |")
        md.append(f"| 최종 자본 | ₩{results['final_capital']:,.0f} |")
        # 총 손익은 최종 자본 - 초기 자본
        actual_profit = results['final_capital'] - results['initial_capital']
        md.append(f"| 총 손익 | ₩{actual_profit:,.0f} |")
        emoji = "📈" if results['total_profit_rate'] > 0 else "📉"
        md.append(f"| 수익률 (자본 대비) | {emoji} **{results['total_profit_rate']:+.2f}%** |")

        # 평균 거래 수익률 추가
        if results['total_trades'] > 0:
            avg_trade_profit = results['avg_profit_rate']
            avg_emoji = "📈" if avg_trade_profit > 0 else "📉"
            md.append(f"| 평균 거래 수익률 | {avg_emoji} {avg_trade_profit:+.2f}% |")
        md.append("")

        # 설명 추가
        if self.mode == 'backtest':
            md.append("> **수익률 설명**: '자본 대비'는 초기 자본 전체 대비 수익률, '평균 거래'는 각 거래의 평균 수익률입니다.")
        else:
            md.append("> **수익률 설명**: '자본 대비'는 초기 설정 자본 대비 수익률, '평균 거래'는 각 거래의 평균 수익률입니다.")
        md.append("")
        
        # 거래 통계
        md.append("## 📈 거래 통계")
        md.append("")
        md.append("| 항목 | 값 |")
        md.append("|------|------|")
        md.append(f"| 총 거래 | {results['total_trades']}회 |")
        md.append(f"| 승리 | {results['winning_trades']}회 |")
        md.append(f"| 패배 | {results['losing_trades']}회 |")
        win_emoji = "✅" if results['win_rate'] >= 70 else "⚠️" if results['win_rate'] >= 60 else "❌"
        md.append(f"| 승률 | {win_emoji} **{results['win_rate']:.1f}%** |")
        md.append(f"| 평균 수익률 | {results['avg_profit_rate']:.2f}% |")
        md.append(f"| 평균 보유 | {results['avg_holding_time']:.1f}분 |")
        md.append("")
        
        # 리스크
        md.append("## 📊 리스크")
        md.append("")
        md.append("| 항목 | 값 |")
        md.append("|------|------|")
        mdd_emoji = "✅" if results['max_drawdown'] > -3 else "⚠️" if results['max_drawdown'] > -5 else "❌"
        md.append(f"| MDD | {mdd_emoji} {results['max_drawdown']:.2f}% |")
        sharpe_emoji = "✅" if results['sharpe_ratio'] > 2 else "⚠️" if results['sharpe_ratio'] > 1 else "❌"
        md.append(f"| 샤프 비율 | {sharpe_emoji} {results['sharpe_ratio']:.2f} |")
        md.append("")
        
        # 거래 내역
        if results['trades']:
            md.append("## 📝 거래 내역 (요약)")
            md.append("")
            md.append("| 시간 | 진입 | 청산 | 수익률 | 보유 | 사유 |")
            md.append("|------|------|------|--------|------|------|")

            for trade in results['trades']:
                ts = pd.to_datetime(trade['timestamp']).strftime('%m-%d %H:%M')
                entry = f"₩{trade['entry_price']:,.0f}"
                exit_p = f"₩{trade['exit_price']:,.0f}"
                pr_emoji = "📈" if trade['profit_rate'] > 0 else "📉"
                pr = f"{pr_emoji} {trade['profit_rate']:+.2f}%"
                ht = f"{trade['holding_time']:.0f}분"
                reason = trade.get('reason', '-')
                md.append(f"| {ts} | {entry} | {exit_p} | {pr} | {ht} | {reason} |")

            md.append("")

            # 상세 거래 내역 (전체)
            md.append("## 📊 상세 거래 내역 (전체)")
            md.append("")
            for i, trade in enumerate(results['trades'], 1):
                ts = pd.to_datetime(trade['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                entry_ts = pd.to_datetime(trade['entry_time']).strftime('%Y-%m-%d %H:%M:%S')
                pr_emoji = "✅" if trade['profit_rate'] > 0 else "❌"

                md.append(f"### 거래 #{i} {pr_emoji}")
                md.append("")
                md.append("**기본 정보**")
                md.append("")
                md.append("| 항목 | 진입 | 청산 |")
                md.append("|------|------|------|")
                md.append(f"| 시간 | {entry_ts} | {ts} |")
                md.append(f"| 가격 | ₩{trade['entry_price']:,.0f} | ₩{trade['exit_price']:,.0f} |")
                md.append(f"| 수익률 | - | **{trade['profit_rate']:+.2f}%** |")
                md.append(f"| 보유시간 | - | {trade['holding_time']:.0f}분 |")
                md.append(f"| 청산사유 | - | {trade.get('reason', '-')} |")
                if trade.get('target_profit'):
                    md.append(f"| 목표수익률 | {trade['target_profit']:.2f}% | - |")
                md.append("")

                md.append("**기술적 지표**")
                md.append("")
                md.append("| 지표 | 진입 | 청산 | 변화 |")
                md.append("|------|------|------|------|")

                # RSI
                entry_rsi_5m = trade.get('entry_rsi_5m')
                exit_rsi_5m = trade.get('exit_rsi_5m')
                if entry_rsi_5m and exit_rsi_5m:
                    rsi_change = exit_rsi_5m - entry_rsi_5m
                    md.append(f"| RSI (5m) | {entry_rsi_5m:.1f} | {exit_rsi_5m:.1f} | {rsi_change:+.1f} |")

                entry_rsi_15m = trade.get('entry_rsi_15m')
                exit_rsi_15m = trade.get('exit_rsi_15m')
                if entry_rsi_15m and exit_rsi_15m:
                    rsi_change = exit_rsi_15m - entry_rsi_15m
                    md.append(f"| RSI (15m) | {entry_rsi_15m:.1f} | {exit_rsi_15m:.1f} | {rsi_change:+.1f} |")

                # 이동평균선
                entry_sma_7 = trade.get('entry_sma_7')
                exit_sma_7 = trade.get('exit_sma_7')
                if entry_sma_7 and exit_sma_7:
                    sma_change = (exit_sma_7 - entry_sma_7) / entry_sma_7 * 100
                    md.append(f"| SMA 7 | ₩{entry_sma_7:,.0f} | ₩{exit_sma_7:,.0f} | {sma_change:+.2f}% |")

                entry_sma_25 = trade.get('entry_sma_25')
                exit_sma_25 = trade.get('exit_sma_25')
                if entry_sma_25 and exit_sma_25:
                    sma_change = (exit_sma_25 - entry_sma_25) / entry_sma_25 * 100
                    md.append(f"| SMA 25 | ₩{entry_sma_25:,.0f} | ₩{exit_sma_25:,.0f} | {sma_change:+.2f}% |")

                md.append("")

                md.append("**거래량**")
                md.append("")
                md.append("| 지표 | 진입 | 청산 |")
                md.append("|------|------|------|")

                entry_volume = trade.get('entry_volume')
                exit_volume = trade.get('exit_volume')
                if entry_volume:
                    md.append(f"| 현재 거래량 | {entry_volume:,.2f} | {exit_volume:,.2f} |")

                entry_volume_surge = trade.get('entry_volume_surge_ratio')
                exit_volume_surge = trade.get('exit_volume_surge_ratio')
                if entry_volume_surge:
                    md.append(f"| 거래량 배율 | {entry_volume_surge:.2f}x | {exit_volume_surge:.2f}x |")

                md.append("")

                # 호가 정보 (데이터가 있을 때만 표시)
                entry_bid_ask = trade.get('entry_bid_ask_ratio')
                exit_bid_ask = trade.get('exit_bid_ask_ratio')
                entry_imbalance = trade.get('entry_bid_imbalance')
                exit_imbalance = trade.get('exit_bid_imbalance')

                has_orderbook_data = entry_bid_ask or entry_imbalance

                if has_orderbook_data:
                    md.append("**호가 정보**")
                    md.append("")
                    md.append("| 지표 | 진입 | 청산 |")
                    md.append("|------|------|------|")

                    if entry_bid_ask:
                        md.append(f"| 매수/매도 비율 | {entry_bid_ask:.2f} | {exit_bid_ask:.2f} |")

                    if entry_imbalance:
                        md.append(f"| 매수호가 비중 | {entry_imbalance:.1%} | {exit_imbalance:.1%} |")

                    md.append("")

            md.append("")
        
        # 설정
        md.append("## ⚙️ 설정")
        md.append("")
        md.append("```json")
        md.append(json.dumps(self.config, indent=2, ensure_ascii=False))
        md.append("```")
        
        return "\n".join(md)
    
    def _serialize(self, obj: Dict) -> Dict:
        """직렬화"""
        result = obj.copy()
        for key in ['timestamp', 'entry_time', 'date']:
            if key in result and hasattr(result[key], 'isoformat'):
                result[key] = result[key].isoformat()
        return result
    
    def log(self, message: str):
        """로그"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        print(log_message)

        # 파일 저장 (세션 ID 포함하여 같은 날 여러 실행 구분)
        log_file = self.output_dir / f"{self.market}_{self.mode}_{self.session_id}.log"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_message + '\n')