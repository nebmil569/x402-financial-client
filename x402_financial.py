"""
x402 Financial Data API — Python Client
======================================
A lightweight Python client for the x402 Financial Data API.
Pay with USDC on Base (eip155:8453) per request. No API keys.

Usage:
    from x402_financial import X402Financial
    client = X402Financial()
    
    # Parse a bank statement
    result = client.parse_statement("dbs", pdf_base64)
    
    # Salary net calculation
    result = client.salary_net(gross_annual=80000)
    
    # SGX stock lookup
    result = client.sgx_stock("DBS")

GitHub: https://github.com/nebmil569/x402-financial-data-api
"""

import base64
import hashlib
import json
import time
import requests
from typing import Optional, List, Dict, Any, Union

# Coinbase x402 payment library
try:
    from coinbase.types import SignedContent, UnsignedTransaction, SignedTransaction
    from coinbase.advanced_api.exchange import sign_content, verify_content
    COINBASE_SDK = True
except ImportError:
    COINBASE_SDK = False

BASE_URL = "https://x402-financial-api.life.conway.tech"
NETWORK = "eip155:8453"
ASSET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # USDC on Base
WALLET = "0x50F9D979b825670A9936D992F5db8AEd9497208A"


class X402PaymentError(Exception):
    """Raised when x402 payment fails"""
    def __init__(self, message, required_amount=None, network=None, asset=None):
        super().__init__(message)
        self.required_amount = required_amount
        self.network = network
        self.asset = asset


class X402Financial:
    """
    Python client for x402 Financial Data API.
    
    Automatically handles x402 v2 payment protocol — pay with USDC on Base.
    
    Usage:
        client = X402Financial(wallet_seed=bytes_or_hex)
        result = client.salary_net(gross_annual=80000)
    """
    
    def __init__(
        self,
        wallet_seed: Optional[Union[str, bytes]] = None,
        base_url: str = BASE_URL,
        timeout: int = 30,
    ):
        """
        Initialize the client.
        
        Args:
            wallet_seed: Wallet private key (bytes or hex str).
                         If not provided, uses environment WALLET_SEED.
            base_url: API base URL (default: Conway production)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        
        # Load wallet
        if wallet_seed is None:
            import os
            wallet_seed = os.environ.get("WALLET_SEED")
        
        if wallet_seed is None:
            raise ValueError(
                "wallet_seed required. Get one at https://keys.coinbase.com "
                "or set WALLET_SEED environment variable."
            )
        
        self.wallet_seed = wallet_seed if isinstance(wallet_seed, bytes) else bytes.fromhex(wallet_seed.lstrip('0x'))
        
        # Discover API capabilities
        self._endpoints = {}
        self._prices = {}
        self._discover()
    
    def _discover(self):
        """Fetch /prices to discover available endpoints"""
        try:
            resp = self._session.get(f"{self.base_url}/prices", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                for ep in data.get("paid_endpoints", []):
                    self._endpoints[ep["path"]] = ep
                self._prices = {ep["path"]: ep["price"] for ep in data.get("paid_endpoints", [])}
        except Exception:
            pass  # Non-fatal — we'll discover lazily
    
    def _make_request(self, method: str, path: str, data: dict = None) -> dict:
        """
        Make an x402-enabled request.
        
        1. Make the request (will get 402 if payment required)
        2. Parse 402 response for payment requirements
        3. Sign and execute payment
        4. Retry with payment header
        """
        url = f"{self.base_url}{path}"
        headers = {}
        
        # First attempt
        if method == "GET":
            resp = self._session.request("GET", url, params=data, timeout=self.timeout)
        else:
            resp = self._session.request(method, url, json=data, timeout=self.timeout)
        
        # Handle 402 Payment Required
        if resp.status_code == 402:
            payment_spec = resp.json()
            
            if not COINBASE_SDK:
                raise X402PaymentError(
                    "Payment required. Install coinbase-sdk: pip install coinbase-mdp-sdk",
                    required_amount=payment_spec.get("error", {}).get("accepts", [{}])[0].get("amount"),
                    network=NETWORK,
                    asset=ASSET
                )
            
            # Extract payment requirements from 402 response
            error = payment_spec.get("error", {})
            x402_err = error.get("error", error)  # nested structure
            accepts = x402_err.get("accepts", x402_err.get("accepts", []))
            
            if not accepts:
                raise X402PaymentError("Payment required but no payment spec in 402 response")
            
            pay_spec = accepts[0]
            amount = pay_spec.get("amount")  # in smallest units (USDC = 6 decimals)
            pay_to = pay_spec.get("pay_to", WALLET)
            network = pay_spec.get("network", NETWORK)
            scheme = pay_spec.get("scheme", "exact")
            
            if scheme != "exact":
                raise X402PaymentError(f"Unsupported payment scheme: {scheme}")
            
            # Build x402 payment token
            from coinbase.advanced_api.key_storage import InMemoryStorage
            from coinbase.crypto import CryptoKeyPair
            
            key = CryptoKeyPair.from_seed(self.wallet_seed)
            storage = InMemoryStorage({key.address: key})
            
            # Create payment payload
            payment_payload = {
                "payment": {
                    "amount": amount,
                    "network": network,
                    "pay_to": pay_to,
                }
            }
            
            # For x402 v2, we need to sign the payment
            payload_json = json.dumps(payment_payload, separators=(',', ':'))
            payload_bytes = payload_json.encode('utf-8')
            
            # Sign using the wallet key
            from coinbase.crypto import sign_message
            signature = sign_message(payload_bytes, key)
            
            # Build the x402 token (base64-encoded JSON)
            token_payload = {
                "data": {
                    "payment": {
                        "amount": amount,
                        "network": network,
                        "signature": signature.hex() if isinstance(signature, bytes) else signature,
                        "signer": key.address,
                    }
                }
            }
            
            auth_token = base64.b64encode(
                json.dumps(token_payload, separators=(',', ':')).encode('utf-8')
            ).decode('utf-8')
            
            headers["Authorization"] = f"Bearer {auth_token}"
            
            # Retry with payment
            if method == "GET":
                resp = self._session.request("GET", url, params=data, headers=headers, timeout=self.timeout)
            else:
                resp = self._session.request(method, url, json=data, headers=headers, timeout=self.timeout)
        
        if resp.status_code != 200:
            raise Exception(f"API error {resp.status_code}: {resp.text[:200]}")
        
        return resp.json()
    
    # =====================
    # BANK PARSING
    # =====================
    
    def parse_statement(self, bank: str, pdf_data: Union[str, bytes], bank_type: str = "bank") -> dict:
        """
        Parse a bank statement PDF.
        
        Args:
            bank: Bank ID (dbs, posb, ocbc, uob, citi, maybank, standchart, trust, boc)
            pdf_data: PDF file as base64 string or bytes
            bank_type: "bank" or "credit_card" (auto-detected if omitted)
        
        Returns:
            Parsed statement with transactions
        """
        if isinstance(pdf_data, bytes):
            pdf_data = base64.b64encode(pdf_data).decode('utf-8')
        
        return self._make_request("POST", f"/parse/{bank}", {
            "data": pdf_data,
            "type": bank_type
        })
    
    def extract_transactions(self, transactions: List[Dict]) -> dict:
        """AI entity extraction + categorization from raw transactions"""
        return self._make_request("POST", "/extract/transactions", {
            "transactions": transactions
        })
    
    # =====================
    # SGX STOCKS
    # =====================
    
    def sgx_stock(self, symbol: str) -> dict:
        """Complete SGX stock profile — price, dividends, PE, EPS, market cap"""
        return self._make_request("POST", "/sgx/stock", {"symbol": symbol.upper()})
    
    def sgx_price(self, symbol: str) -> dict:
        """Real-time SGX stock price"""
        return self._make_request("POST", "/sgx/price", {"symbol": symbol.upper()})
    
    def sgx_dividend(self, symbol: str) -> dict:
        """SGX stock dividend data"""
        return self._make_request("POST", "/sgx/dividend", {"symbol": symbol.upper()})
    
    def sgx_portfolio(self, symbols: List[str]) -> dict:
        """Batch lookup up to 20 SGX stocks"""
        return self._make_request("POST", "/sgx/portfolio", {
            "symbols": [s.upper() for s in symbols]
        })
    
    def sgx_screen(self, min_dividend_yield: float = 3.0, sort_by: str = "yield") -> dict:
        """Dividend screener for top SGX stocks"""
        return self._make_request("POST", "/sgx/screen", {
            "min_dividend_yield": min_dividend_yield,
            "sort_by": sort_by
        })
    
    # =====================
    # SALARY & TAX
    # =====================
    
    def salary_net(self, gross_annual: float, is_local_employee: bool = True, 
                   bonus_pct: float = 0) -> dict:
        """
        Singapore take-home salary calculator.
        
        Args:
            gross_annual: Annual gross salary in SGD
            is_local_employee: True for Singapore citizens/PR, False for foreigners
            bonus_pct: Annual bonus as percentage of salary
        
        Returns:
            Breakdown of gross, CPF, tax, SDL, and net take-home
        
        Example:
            >>> client.salary_net(80000)
            {'gross_monthly': 6666.67, 'cpf_employee': 1200, 'cpf_employer': 1200,
             'income_tax': 465, 'sdl': 109.33, 'net_monthly': 4884.0, ...}
        """
        return self._make_request("POST", "/salary/net", {
            "gross_annual": gross_annual,
            "is_local_employee": is_local_employee,
            "bonus_pct": bonus_pct
        })
    
    def salary_benchmark(self, occupation: str, age_group: str = "25-29",
                          education_level: str = "degree") -> dict:
        """MOM income percentile rankings"""
        return self._make_request("POST", "/salary/benchmark", {
            "occupation": occupation,
            "age_group": age_group,
            "education_level": education_level
        })
    
    def tax_income(self, gross_annual: float, year_of_assessment: int = 2026) -> dict:
        """Singapore personal income tax calculator"""
        return self._make_request("POST", "/tax/income", {
            "gross_annual": gross_annual,
            "year_of_assessment": year_of_assessment
        })
    
    def tax_corporate(self, chargeable_income: float) -> dict:
        """Singapore corporate tax estimator (PTE scheme)"""
        return self._make_request("POST", "/tax/corporate", {
            "chargeable_income": chargeable_income
        })
    
    # =====================
    # CPF & RETIREMENT
    # =====================
    
    def cpf_calculator(self, age: int, basic_salary: float,
                       cpf_contribution_rate: float = 37) -> dict:
        """Project CPF balances (OA/SA/RA) at retirement"""
        return self._make_request("POST", "/cpf/calculator", {
            "age": age,
            "basic_salary": basic_salary,
            "cpf_contribution_rate": cpf_contribution_rate
        })
    
    def cpf_contributions(self, basic_salary: float, age: int,
                           extra_ceiling: float = 0) -> dict:
        """Calculate CPF employee + employer contributions"""
        return self._make_request("POST", "/cpf/contributions", {
            "basic_salary": basic_salary,
            "age": age,
            "extra_ceiling": extra_ceiling
        })
    
    def cpf_topup(self, age: int, cpf_balance: float, annual_income: float) -> dict:
        """CPF top-up optimizer"""
        return self._make_request("POST", "/cpf/topup", {
            "age": age,
            "cpf_balance": cpf_balance,
            "annual_income": annual_income
        })
    
    def srs_calculator(self, age: int, annual_income: float,
                        contribution_amount: float, years_to_retirement: int = 20) -> dict:
        """Singapore SRS calculator"""
        return self._make_request("POST", "/srs/calculator", {
            "age": age,
            "annual_income": annual_income,
            "contribution_amount": contribution_amount,
            "years_to_retirement": years_to_retirement
        })
    
    def fire(self, age: int, annual_income: float, savings_rate: float = 0.5,
             target_retirement_age: int = 55) -> dict:
        """Singapore FIRE calculator"""
        return self._make_request("POST", "/fire", {
            "age": age,
            "annual_income": annual_income,
            "savings_rate": savings_rate,
            "target_retirement_age": target_retirement_age
        })
    
    # =====================
    # INVESTMENTS
    # =====================
    
    def invest_dca(self, monthly_investment: float, years: int) -> dict:
        """
        Singapore DCA simulator — IWLU vs CPF OA vs SSB.
        
        Compares dollar-cost averaging into:
        - IWLU (iShares MSCI World UCITS ETF) — ~7% historical return
        - CPF OA (Ordinary Account) — 2.5% p.a. guaranteed
        - Singapore Savings Bonds — ~3% p.a.
        
        Args:
            monthly_investment: Amount in SGD to invest each month
            years: Investment horizon
        
        Returns:
            Year-by-year projection table and ranking of the 3 approaches
        
        Example:
            >>> client.invest_dca(500, 10)
            {'iwlu': {'final_value': 87000, 'total_contributed': 60000, ...},
             'cpf_oa': {...}, 'ssb': {...}, 'ranking': ['iwlu', 'ssb', 'cpf_oa']}
        """
        return self._make_request("POST", "/invest/dca", {
            "monthly_investment": monthly_investment,
            "years": years
        })
    
    def invest_grow(self, initial_amount: float, monthly_topup: float = 0,
                    expected_return: float = 7, years: int = 10) -> dict:
        """Investment growth calculator"""
        return self._make_request("POST", "/invest/grow", {
            "initial_amount": initial_amount,
            "monthly_topup": monthly_topup,
            "expected_return": expected_return,
            "years": years
        })
    
    def sgx_search(self, query: str) -> dict:
        """Search SGX stocks by name or symbol"""
        return self._make_request("POST", "/sgx/search", {"query": query})
    
    # =====================
    # PROPERTY & HOUSING
    # =====================
    
    def bto_affordability(self, annual_household_income: float,
                          flat_type: str = "4-room") -> dict:
        """
        BTO flat affordability calculator.
        
        Returns HDB vs bank loan eligibility, monthly mortgage,
        grants (EHG up to $80k), BSD, TDSR, and affordability verdict.
        """
        return self._make_request("POST", "/bto/affordability", {
            "annual_household_income": annual_household_income,
            "flat_type": flat_type
        })
    
    def hdb_resale(self, town: str, flat_type: str = "4-room",
                   floor_level: int = 10, lease_remaining: int = 88) -> dict:
        """Estimate HDB resale flat prices across 23 Singapore towns"""
        return self._make_request("POST", "/hdb/resale", {
            "town": town,
            "flat_type": flat_type,
            "floor_level": floor_level,
            "lease_remaining": lease_remaining
        })
    
    def property_tax(self, annual_value: float, owner_occupied: bool = True) -> dict:
        """Singapore property tax calculator (IRAS 2024 rates)"""
        return self._make_request("POST", "/property/tax", {
            "annual_value": annual_value,
            "ownership_type": "owner-occupied" if owner_occupied else "non-owner"
        })
    
    def absd(self, citizenship: str, property_count: int,
             purchase_price: float, is_pr: bool = False) -> dict:
        """ABSD/BSD calculator for Singapore property purchases"""
        return self._make_request("POST", "/property/absd", {
            "citizenship": citizenship,
            "property_count": property_count,
            "is_buyer_permanent_resident": is_pr,
            "purchase_price": purchase_price
        })
    
    def mortgage_compare(self, loan_amount: float, loan_tenure: int,
                         interest_rate: float) -> dict:
        """Compare HDB vs bank mortgage"""
        return self._make_request("POST", "/mortgage/compare", {
            "loan_amount": loan_amount,
            "loan_tenure": loan_tenure,
            "interest_rate": interest_rate
        })
    
    def refinance(self, current_loan_amount: float, current_interest_rate: float,
                   remaining_tenure: int, new_interest_rate: float,
                   lock_in_status: str = "expired") -> dict:
        """Singapore mortgage refinance analyzer"""
        return self._make_request("POST", "/refinance", {
            "current_loan_amount": current_loan_amount,
            "current_interest_rate": current_interest_rate,
            "remaining_tenure": remaining_tenure,
            "new_interest_rate": new_interest_rate,
            "lock_in_status": lock_in_status
        })
    
    # =====================
    # REPORTS
    # =====================
    
    def summary(self, transactions: List[Dict], person_name: str = "",
                statement_period: str = "") -> dict:
        """Financial summary from transactions"""
        return self._make_request("POST", "/summary", {
            "transactions": transactions,
            "person_name": person_name,
            "statement_period": statement_period
        })
    
    def report_spending(self, transactions: List[Dict],
                        person_name: str = "", currency: str = "SGD") -> dict:
        """Detailed expense report with chart-ready data"""
        return self._make_request("POST", "/report/spending", {
            "transactions": transactions,
            "person_name": person_name,
            "currency": currency
        })
    
    def report_cash_flow(self, transactions: List[Dict],
                         person_name: str = "", currency: str = "SGD") -> dict:
        """Cash flow analysis"""
        return self._make_request("POST", "/report/cash-flow", {
            "transactions": transactions,
            "person_name": person_name,
            "currency": currency
        })
    
    def report_subscriptions(self, transactions: List[Dict]) -> dict:
        """Detect active subscriptions and annual costs"""
        return self._make_request("POST", "/report/subscriptions", {
            "transactions": transactions
        })
    
    # =====================
    # UTILITIES
    # =====================
    
    def cost_estimate(self, annual_income: float,
                      age: int = 30, household_size: int = 4) -> dict:
        """Singapore CPI/purchasing power calculator"""
        return self._make_request("POST", "/cost/estimate", {
            "annual_income": annual_income,
            "age": age,
            "household_size": household_size
        })
    
    def electricity_compare(self, monthly_kwh: float,
                             housing_type: str = "hdb-4-room") -> dict:
        """Compare Singapore electricity retailer plans"""
        return self._make_request("POST", "/electricity/compare", {
            "monthly_kwh": monthly_kwh,
            "housing_type": housing_type
        })
    
    def coe_prices(self) -> dict:
        """Latest Singapore COE premiums for all 5 categories"""
        return self._make_request("POST", "/coe", {})
    
    def ssb_rates(self) -> dict:
        """Latest Singapore Savings Bonds rates"""
        return self._make_request("GET", "/ssb/rates")
    
    def forex_convert(self, from_currency: str, to_currency: str,
                      amount: float) -> dict:
        """Currency conversion"""
        return self._make_request("POST", "/forex/convert", {
            "from_currency": from_currency,
            "to_currency": to_currency,
            "amount": amount
        })
    
    def holidays(self, year: int = None) -> dict:
        """Singapore public holidays"""
        if year:
            return self._make_request("GET", "/holidays/singapore", {"year": year})
        return self._make_request("GET", "/holidays/singapore")
    
    # =====================
    # UTILITY
    # =====================
    
    def health(self) -> dict:
        """Check API health and version"""
        resp = self._session.get(f"{self.base_url}/health", timeout=5)
        return resp.json() if resp.status_code == 200 else {}
    
    def prices(self) -> dict:
        """Get full API price catalog"""
        resp = self._session.get(f"{self.base_url}/prices", timeout=5)
        return resp.json() if resp.status_code == 200 else {}
    
    @property
    def endpoints(self) -> Dict[str, dict]:
        """All discovered paid endpoints with their metadata"""
        return self._endpoints
    
    @property
    def supported_banks(self) -> List[str]:
        return ["dbs", "posb", "ocbc", "uob", "citi", "maybank", "standchart", "trust", "boc"]


def main():
    """Quick demo — check API health and show endpoint catalog"""
    import os
    
    client = X402Financial(
        wallet_seed=os.environ.get("WALLET_SEED"),
        base_url="https://x402-financial-api.life.conway.tech"
    )
    
    health = client.health()
    print(f"API: {client.base_url}")
    print(f"Version: {health.get('version')}")
    print(f"Endpoints: {len(client.endpoints)} paid + 6 free")
    print()
    print("Try: client.salary_net(80000) or client.invest_dca(500, 10)")


if __name__ == "__main__":
    main()
