#!/usr/bin/env python3
"""
시간대별 거래량 분석 도구
비트코인, 이더리움의 시간대별 거래량 패턴 분석

사용법:
    uv run scripts/analyze_volume_by_time.py --days 30
    uv run scripts/analyze_volume_by_time.py --days 7 --coins BTC ETH XRP
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import time
from typing import Dict, List
import json

# 프로젝트 루트
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

import pandas as pd
import numpy as np
import requests


def parse_args():
    """명령줄 인자"""
    parser = argparse.ArgumentParser(
        description='⏰ 시간대별 거래량 분석',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='분석 기간 (일) (기본: 30)'
    )

    parser.add_argument(
        '--coins',
        nargs='+',
        default=['BTC', 'ETH'],
        help='분석할 코인 (기본: BTC ETH)'
    )

    return parser.parse_args()


def fetch_candles(market: str, unit: int, count: int = 200, to: str = None) -> pd.DataFrame:
    """분봉 데이터 조회"""
    BASE_URL = "https://api.upbit.com/v1"
    endpoint = f"{BASE_URL}/candles/minutes/{unit}"
    params = {'market': market, 'count': count}
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
                 'low_price', 'trade_price', 'candle_acc_trade_volume', 'candle_acc_trade_price']]
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'value']
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('timestamp').sort_index()

        return df

    except Exception as e:
        print(f"❌ 데이터 조회 오류: {e}")
        return pd.DataFrame()


def fetch_bulk_data(market: str, unit: int, days: int) -> pd.DataFrame:
    """대량 데이터 수집"""
    print(f"📥 {market} {unit}분봉 데이터 다운로드 중... ({days}일)")

    candles_per_day = (24 * 60) // unit
    total_candles = days * candles_per_day
    fetch_count = (total_candles // 200) + 1

    all_data = []
    to_time = None

    for i in range(fetch_count):
        df = fetch_candles(market, unit, count=200, to=to_time)
        if df.empty:
            break

        all_data.append(df)
        to_time = df.index[0].isoformat()

        progress = min(100, ((i + 1) / fetch_count) * 100)
        print(f"  진행률: {progress:.0f}%", end='\r')

        time.sleep(0.11)  # API 제한

        if len(all_data) * 200 >= total_candles:
            break

    print()

    if not all_data:
        return pd.DataFrame()

    df = pd.concat(all_data)
    df = df[~df.index.duplicated(keep='first')].sort_index()
    print(f"✅ {len(df):,}개 캔들 다운로드 완료")

    return df


def analyze_hourly_volume(df: pd.DataFrame, coin: str) -> Dict:
    """시간대별 거래량 분석"""
    # 시간대 추출
    df['hour'] = df.index.hour
    df['weekday'] = df.index.dayofweek  # 0=월요일, 6=일요일
    df['date'] = df.index.date

    # 시간대별 평균 거래량 (원화 기준)
    hourly_volume = df.groupby('hour')['value'].mean()

    # 시간대별 평균 거래량 (코인 수량 기준)
    hourly_volume_coin = df.groupby('hour')['volume'].mean()

    # 요일별 평균 거래량
    weekday_volume = df.groupby('weekday')['value'].mean()

    # 시간대별 변동성 (가격 변동폭)
    df['volatility'] = (df['high'] - df['low']) / df['low'] * 100
    hourly_volatility = df.groupby('hour')['volatility'].mean()

    # 시간대별 거래 횟수
    hourly_count = df.groupby('hour').size()

    # 피크 시간대 찾기 (상위 5개)
    top_hours = hourly_volume.nlargest(5)
    bottom_hours = hourly_volume.nsmallest(5)

    return {
        'coin': coin,
        'period_days': (df.index[-1] - df.index[0]).days,
        'total_candles': len(df),
        'hourly_volume_krw': hourly_volume.to_dict(),
        'hourly_volume_coin': hourly_volume_coin.to_dict(),
        'hourly_volatility': hourly_volatility.to_dict(),
        'hourly_count': hourly_count.to_dict(),
        'weekday_volume': weekday_volume.to_dict(),
        'top_hours': {int(hour): float(vol) for hour, vol in top_hours.items()},
        'bottom_hours': {int(hour): float(vol) for hour, vol in bottom_hours.items()},
        'avg_volume_krw': hourly_volume.mean(),
        'max_volume_krw': hourly_volume.max(),
        'min_volume_krw': hourly_volume.min(),
    }


def print_analysis(results: List[Dict]):
    """분석 결과 출력"""
    print()
    print("=" * 100)
    print("⏰ 시간대별 거래량 분석 결과")
    print("=" * 100)
    print()

    weekday_names = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']

    for result in results:
        coin = result['coin']
        print(f"📊 {coin}")
        print("-" * 100)
        print(f"분석 기간: {result['period_days']}일 ({result['total_candles']:,}개 캔들)")
        print(f"평균 시간당 거래액: ₩{result['avg_volume_krw']:,.0f}")
        print()

        # 거래량 상위 5 시간대
        print("🔥 거래량 TOP 5 시간대:")
        print(f"{'시간':<10} {'평균 거래액':>20} {'비율':>15}")
        print("-" * 50)
        for hour, volume in result['top_hours'].items():
            percentage = (volume / result['avg_volume_krw']) * 100
            print(f"{hour:02d}:00-{hour:02d}:59 {volume:>20,.0f}원 {percentage:>14.1f}%")
        print()

        # 거래량 하위 5 시간대
        print("❄️  거래량 BOTTOM 5 시간대:")
        print(f"{'시간':<10} {'평균 거래액':>20} {'비율':>15}")
        print("-" * 50)
        for hour, volume in result['bottom_hours'].items():
            percentage = (volume / result['avg_volume_krw']) * 100
            print(f"{hour:02d}:00-{hour:02d}:59 {volume:>20,.0f}원 {percentage:>14.1f}%")
        print()

        # 요일별 거래량
        print("📅 요일별 평균 거래액:")
        print(f"{'요일':<10} {'평균 거래액':>20} {'비율':>15}")
        print("-" * 50)
        weekday_volume = result['weekday_volume']
        avg_weekday = sum(weekday_volume.values()) / len(weekday_volume)
        for day, volume in sorted(weekday_volume.items()):
            percentage = (volume / avg_weekday) * 100
            print(f"{weekday_names[day]:<10} {volume:>20,.0f}원 {percentage:>14.1f}%")
        print()

        # 24시간 히트맵 (간단 버전)
        print("📈 24시간 거래량 히트맵:")
        print("-" * 50)
        hourly_volume = result['hourly_volume_krw']
        max_vol = max(hourly_volume.values())

        # 6시간 단위로 출력
        for block in range(4):
            start_hour = block * 6
            end_hour = start_hour + 6
            print(f"{start_hour:02d}:00-{end_hour-1:02d}:59: ", end="")

            for hour in range(start_hour, end_hour):
                volume = hourly_volume.get(hour, 0)
                intensity = int((volume / max_vol) * 10)
                bar = "█" * intensity + "░" * (10 - intensity)
                print(f"{hour:02d}h[{bar}] ", end="")
            print()
        print()

        # 변동성 분석
        print("📊 시간대별 평균 변동성 (TOP 5):")
        print(f"{'시간':<10} {'평균 변동성':>15}")
        print("-" * 30)
        hourly_volatility = result['hourly_volatility']
        top_volatility = dict(sorted(hourly_volatility.items(), key=lambda x: x[1], reverse=True)[:5])
        for hour, vol in top_volatility.items():
            print(f"{hour:02d}:00-{hour:02d}:59 {vol:>14.2f}%")
        print()

        print("=" * 100)
        print()


def generate_recommendations(results: List[Dict]):
    """거래 추천 시간대 생성"""
    print()
    print("=" * 100)
    print("💡 거래 전략 추천")
    print("=" * 100)
    print()

    for result in results:
        coin = result['coin']
        top_hours = result['top_hours']
        hourly_volatility = result['hourly_volatility']

        print(f"📌 {coin} 추천 전략:")
        print("-" * 100)

        # 고거래량 + 고변동성 시간대 (스캘핑 최적)
        scalping_hours = []
        for hour in top_hours.keys():
            vol = hourly_volatility.get(hour, 0)
            if vol > np.mean(list(hourly_volatility.values())):
                scalping_hours.append((hour, top_hours[hour], vol))

        if scalping_hours:
            print()
            print("⚡ 스캘핑 최적 시간대 (고거래량 + 고변동성):")
            print(f"{'시간':<10} {'거래액':>20} {'변동성':>15}")
            print("-" * 50)
            for hour, volume, volatility in sorted(scalping_hours, key=lambda x: x[1], reverse=True):
                print(f"{hour:02d}:00-{hour:02d}:59 {volume:>20,.0f}원 {volatility:>14.2f}%")

        # 저거래량 시간대 (피해야 할 시간)
        print()
        print("⚠️  주의 시간대 (낮은 거래량, 슬리피지 위험):")
        bottom_hours = result['bottom_hours']
        for hour in sorted(bottom_hours.keys()):
            print(f"  - {hour:02d}:00-{hour:02d}:59")

        # 요일별 추천
        weekday_volume = result['weekday_volume']
        weekday_names = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']
        avg_weekday = sum(weekday_volume.values()) / len(weekday_volume)

        best_days = sorted(weekday_volume.items(), key=lambda x: x[1], reverse=True)[:3]
        worst_days = sorted(weekday_volume.items(), key=lambda x: x[1])[:2]

        print()
        print("📅 추천 요일:")
        for day, volume in best_days:
            percentage = (volume / avg_weekday) * 100
            print(f"  ✅ {weekday_names[day]} (평균 대비 {percentage:.1f}%)")

        print()
        print("📅 비추천 요일:")
        for day, volume in worst_days:
            percentage = (volume / avg_weekday) * 100
            print(f"  ❌ {weekday_names[day]} (평균 대비 {percentage:.1f}%)")

        print()
        print("=" * 100)
        print()


def save_results(results: List[Dict], days: int):
    """결과 저장"""
    output_dir = Path("analysis_reports")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSON 저장
    json_file = output_dir / f"volume_analysis_{timestamp}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            'analysis_date': timestamp,
            'analysis_days': days,
            'results': results
        }, f, indent=2, ensure_ascii=False)

    print(f"💾 결과 저장: {json_file}")

    # Markdown 리포트
    md_file = output_dir / f"volume_analysis_{timestamp}.md"
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(f"# 시간대별 거래량 분석 리포트\n\n")
        f.write(f"**분석일**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**분석 기간**: {days}일\n\n")
        f.write("---\n\n")

        for result in results:
            coin = result['coin']
            f.write(f"## {coin}\n\n")

            f.write("### 거래량 TOP 5 시간대\n\n")
            f.write("| 시간 | 평균 거래액 | 비율 |\n")
            f.write("|------|-------------|------|\n")
            for hour, volume in result['top_hours'].items():
                percentage = (volume / result['avg_volume_krw']) * 100
                f.write(f"| {hour:02d}:00-{hour:02d}:59 | ₩{volume:,.0f} | {percentage:.1f}% |\n")
            f.write("\n")

            f.write("### 요일별 거래액\n\n")
            weekday_names = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']
            f.write("| 요일 | 평균 거래액 |\n")
            f.write("|------|-------------|\n")
            weekday_volume = result['weekday_volume']
            for day, volume in sorted(weekday_volume.items()):
                f.write(f"| {weekday_names[day]} | ₩{volume:,.0f} |\n")
            f.write("\n")

            f.write("---\n\n")

    print(f"📄 리포트: {md_file}")


def main():
    """메인"""
    args = parse_args()

    print()
    print("=" * 100)
    print("⏰ 시간대별 거래량 분석")
    print("=" * 100)
    print(f"분석 기간: {args.days}일")
    print(f"분석 코인: {', '.join(args.coins)}")
    print("=" * 100)
    print()

    results = []

    for coin in args.coins:
        market = f"KRW-{coin}"
        print(f"🔍 {market} 분석 중...")

        # 5분봉 데이터 수집
        df = fetch_bulk_data(market, 5, args.days)

        if df.empty:
            print(f"❌ {market} 데이터 없음")
            continue

        # 분석
        result = analyze_hourly_volume(df, coin)
        results.append(result)

        print()

    if results:
        # 결과 출력
        print_analysis(results)

        # 추천 생성
        generate_recommendations(results)

        # 결과 저장
        save_results(results, args.days)

    else:
        print("❌ 분석할 데이터가 없습니다.")


if __name__ == "__main__":
    main()
