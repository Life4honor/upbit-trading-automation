"""
Upbit API 래퍼 (인증 + 거래)
"""

import hashlib
import jwt
import requests
import uuid
from typing import Dict, List, Optional
from urllib.parse import urlencode, unquote


class UpbitAPI:
    """Upbit REST API 클라이언트"""
    
    BASE_URL = "https://api.upbit.com/v1"
    
    def __init__(self, access_key: str, secret_key: str):
        """
        초기화
        
        Args:
            access_key: Upbit API Access Key
            secret_key: Upbit API Secret Key
        """
        self.access_key = access_key
        self.secret_key = secret_key
    
    def _get_headers(self, query: Dict = None) -> Dict:
        """인증 헤더 생성"""
        payload = {
            'access_key': self.access_key,
            'nonce': str(uuid.uuid4()),
        }
        
        if query:
            query_string = unquote(urlencode(query, doseq=True)).encode("utf-8")
            m = hashlib.sha512()
            m.update(query_string)
            query_hash = m.hexdigest()
            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'
        
        jwt_token = jwt.encode(payload, self.secret_key)
        
        return {
            'Authorization': f'Bearer {jwt_token}',
            'Content-Type': 'application/json'
        }
    
    def _request(self, method: str, endpoint: str, params: Dict = None, 
                 auth: bool = False) -> Optional[Dict]:
        """API 요청"""
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            if auth:
                headers = self._get_headers(params)
                if method == 'GET':
                    response = requests.get(url, headers=headers, params=params)
                else:
                    response = requests.post(url, headers=headers, json=params)
            else:
                headers = {'Accept': 'application/json'}
                response = requests.get(url, headers=headers, params=params)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"❌ API 오류: {e}")
            if hasattr(e.response, 'text'):
                print(f"응답: {e.response.text}")
            return None
    
    # ==========================================
    # 시세 정보 (인증 불필요)
    # ==========================================
    
    def get_current_price(self, market: str) -> Optional[float]:
        """현재가 조회"""
        data = self._request('GET', '/ticker', {'markets': market})
        if data and len(data) > 0:
            return data[0]['trade_price']
        return None
    
    def get_orderbook(self, market: str) -> Optional[Dict]:
        """호가 정보 조회"""
        data = self._request('GET', '/orderbook', {'markets': market})
        if data and len(data) > 0:
            return data[0]
        return None
    
    # ==========================================
    # 계정 정보 (인증 필요)
    # ==========================================
    
    def get_accounts(self) -> Optional[List[Dict]]:
        """전체 계좌 조회"""
        return self._request('GET', '/accounts', auth=True)
    
    def get_balance(self, currency: str = 'KRW') -> Optional[float]:
        """특정 통화 잔고 조회"""
        accounts = self.get_accounts()
        if not accounts:
            return None
        
        for account in accounts:
            if account['currency'] == currency:
                return float(account['balance'])
        
        return 0.0
    
    def get_position(self, market: str) -> Optional[Dict]:
        """
        특정 코인 보유 현황
        
        Returns:
            {
                'currency': 'BTC',
                'balance': 0.01234,
                'avg_buy_price': 170000000,
                'locked': 0.0
            }
        """
        currency = market.split('-')[1]
        accounts = self.get_accounts()
        
        if not accounts:
            return None
        
        for account in accounts:
            if account['currency'] == currency:
                return {
                    'currency': currency,
                    'balance': float(account['balance']),
                    'avg_buy_price': float(account['avg_buy_price']),
                    'locked': float(account['locked'])
                }
        
        return None
    
    # ==========================================
    # 주문 (인증 필요)
    # ==========================================
    
    def buy_market(self, market: str, price: float) -> Optional[Dict]:
        """
        시장가 매수
        
        Args:
            market: 마켓 코드 (예: 'KRW-BTC')
            price: 매수 금액 (KRW)
        
        Returns:
            주문 결과
        """
        params = {
            'market': market,
            'side': 'bid',
            'price': str(price),
            'ord_type': 'price'
        }
        
        result = self._request('POST', '/orders', params, auth=True)
        
        if result:
            print(f"✅ 매수 주문 체결: {market}")
            print(f"   금액: ₩{price:,.0f}")
            print(f"   주문ID: {result.get('uuid', 'N/A')}")
        
        return result
    
    def sell_market(self, market: str, volume: float) -> Optional[Dict]:
        """
        시장가 매도
        
        Args:
            market: 마켓 코드 (예: 'KRW-BTC')
            volume: 매도 수량
        
        Returns:
            주문 결과
        """
        params = {
            'market': market,
            'side': 'ask',
            'volume': str(volume),
            'ord_type': 'market'
        }
        
        result = self._request('POST', '/orders', params, auth=True)
        
        if result:
            print(f"✅ 매도 주문 체결: {market}")
            print(f"   수량: {volume}")
            print(f"   주문ID: {result.get('uuid', 'N/A')}")
        
        return result


def load_api_keys(path: str = "config/api_keys.json") -> Dict:
    """
    API 키 로드
    
    파일 형식:
    {
        "access_key": "your_access_key",
        "secret_key": "your_secret_key"
    }
    """
    import json
    from pathlib import Path
    
    key_file = Path(path)
    
    if not key_file.exists():
        raise FileNotFoundError(
            f"API 키 파일이 없습니다: {path}\n"
            f"다음 형식으로 생성하세요:\n"
            f'{{\n'
            f'  "access_key": "YOUR_ACCESS_KEY",\n'
            f'  "secret_key": "YOUR_SECRET_KEY"\n'
            f'}}'
        )
    
    with open(key_file, 'r') as f:
        keys = json.load(f)
    
    if 'access_key' not in keys or 'secret_key' not in keys:
        raise ValueError("API 키 파일에 access_key와 secret_key가 필요합니다")
    
    return keys
