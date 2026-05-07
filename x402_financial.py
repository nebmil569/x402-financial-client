"""
x402 Financial Data API — Python Client
======================================
A lightweight Python client for the x402 Financial Data API.
Pay with USDC on Base (eip155:8453) per request. No API keys.

Supports all 67+ endpoints including bank statement parsing (9 Singapore banks),
SGX stock data, CPF/SRS/FIRE calculators, tax, property, and more.

Usage:
    from x402_financial import X402Financial
    client = X402Financial()
    
    # Auto-discovers best available endpoint
    result = client.salary_net(gross_annual=80000)
    result = client.sgx_stock("DBS")
    result = client.fire(age=30, annual_income=80000)

GitHub: https://github.com/nebmil569/x402-financial-data-api
PyPI: https://pypi.org/project/x402-financial
"""

import base64
import json
import time
import requests
from typing import Optional, List, Dict, Any, Union

BASE_URLS = [
    "https://x402-financial-data-3crjleocd-nebmil569s-projects.vercel.app",  # latest preview (v1.5.9)
    "https://x402-financial-data-4qmi9jmvk-nebmil569s-projects.vercel.app",  # latest preview (v1.5.9)
    "https://apinew-nine.vercel.app",  # stable production (v1.5.8)
    "https://x402-financial-api.life.conway.tech",  # Conway legacy
]
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
    
    Auto-discovers best available endpoint on init. Handles x402 v2 payment
    protocol automatically — pay with USDC on Base.
    
    Usage:
        client = X402Financial(wallet_seed=bytes_or_hex)
        result = client.salary_net(gross_annual=80000)
        result = client.sgx_stock("DBS")
        result = client.invest_dca(monthly_investment=500, years=10)
    """
    
    def __init__(
        self,
        wallet_seed: Optional[Union[str, bytes]] = None,
        base_url: Optional[str] = None,
        timeout: int = 30,
        api_key: Optional[str] = None,
    ):
        """
        Initialize the client. Auto-discovers best available API endpoint.
        
        Args:
            wallet_seed: Wallet private key (bytes or hex str).
                         If not provided, uses environment WALLET_SEED.
            base_url: Override API base URL (optional, default: auto-discover)
            timeout: Request timeout in seconds
            api_key: Optional API key for x402 header
        """
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        if api_key:
            self._session.headers["X-API-Key"] = api_key
        
        # Multi-endpoint fallback discovery
        if base_url:
            self.base_url = base_url.rstrip('/')
            self._deploy_url = self.base_url
            self._discover()
        else:
            discovered = False
            # Priority: newer preview deployments first, then stable production
            url_priority = [
                ("https://x402-financial-api.life.conway.tech", "conway_v1.5.5"),
                ("https://x402-financial-data-3crjleocd-nebmil569s-projects.vercel.app", "preview_v1.5.9"),
                ("https://x402-financial-data-4qmi9jmvk-nebmil569s-projects.vercel.app", "preview_v1.5.9"),
                ("https://apinew-nine.vercel.app", "prod_v1.5.8"),
            ]
            for url, label in url_priority:
                try:
                    resp = self._session.get(f"{url}/health", timeout=5)
                    if resp.status_code == 200:
                        data = resp.json()
                        version = data.get("version", "unknown")
                        # Use the URL that actually responds (prefer newer deployments)
                        self.base_url = url
                        self._deploy_url = url
                        self._version = version
                        # api_base_url from health may be legacy — trust our direct URL more
                        self._endpoints = {}
                        self._prices = {}
                        self._discover()
                        discovered = True
                        break
                except Exception:
                    continue
            
            if not discovered:
                self.base_url = "https://x402-financial-api.life.conway.tech"
                self._deploy_url = self.base_url
                self._version = "unknown"
                self._endpoints = {}
                self._prices = {}
        
        # Wallet
        self.wallet_seed = None
        if wallet_seed:
            seed_hex = wallet_seed if isinstance(wallet_seed, str) else wallet_seed.hex()
            self.wallet_seed = bytes.fromhex(seed_hex.lstrip('0x'))
    
    def _discover(self):
        """Fetch and cache endpoint manifest (normalize full URLs to paths)."""
        try:
            resp = self._session.get(f"{self.base_url}/x402.json", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for ep in data.get("endpoints", []):
                    full_url = ep.get("url", "")
                    if full_url:
                        # Extract path from full URL (e.g. "https://host/path" -> "/path")
                        # Handle Vercel preview URLs (full URL as url field)
                        parsed = full_url.split(self.base_url, 1)
                        path = parsed[1] if len(parsed) > 1 else full_url
                        if not path.startswith('/'):
                            path = '/' + path
                        ep["_path"] = path  # normalized path key
                        self._endpoints[path] = ep
                self._prices = {
                    ep.get("_path", ep.get("url", "")): ep.get("price_usd", ep.get("pricing", {}).get("amount", "0"))
                    for ep in data.get("endpoints", [])
                }
        except Exception:
            pass
    
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
            
            if not self.wallet_seed:
                error = payment_spec.get("error", {})
                accepts = error.get("accepts", error.get("error", {}).get("accepts", []))
                if accepts:
                    req = accepts[0]
                    raise X402PaymentError(
                        f"Payment required: {req.get('amount')} USDC on {req.get('network','base')}",
                        required_amount=req.get("amount"),
                        network=req.get("network", NETWORK),
                        asset=ASSET
                    )
                raise X402PaymentError("Payment required but no wallet configured")
            
            # Extract payment requirements from 402 response
            error = payment_spec.get("error", {})
            x402_err = error.get("error", error)
            accepts = x402_err.get("accepts", [])
            
            if not accepts:
                raise X402PaymentError("Payment required but no payment spec in 402 response")
            
            pay_spec = accepts[0]
            amount = pay_spec.get("amount")
            pay_to = pay_spec.get("pay_to", WALLET)
            network = pay_spec.get("network", NETWORK)
            scheme = pay_spec.get("scheme", "exact")
            
            if scheme != "exact":
                raise X402PaymentError(f"Unsupported payment scheme: {scheme}")
            
            # Sign payment using Coinbase SDK
            try:
                from coinbase.types import SignedContent
                from coinbase.advanced_api.exchange import sign_content
                from coinbase.crypto import CryptoKeyPair
                from coinbase.advanced_api.key_storage import InMemoryStorage
                
                key = CryptoKeyPair.from_seed(self.wallet_seed)
                storage = InMemoryStorage({key.address: key})
                
                # Build payment payload
                payment_payload = {
                    "payment": {
                        "amount": amount,
                        "network": network,
                        "pay_to": pay_to,
                        "asset": ASSET,
                    }
                }
                
                payload_json = json.dumps(payment_payload, separators=(',', ':'))
                payload_bytes = payload_json.encode('utf-8')
                
                from coinbase.crypto import sign_message
                signature = sign_message(payload_bytes, key)
                sig_hex = signature.hex() if isinstance(signature, bytes) else signature
                
                token_payload = {
                    "data": {
                        "payment": {
                            "amount": amount,
                            "network": network,
                            "pay_to": pay_to,
                            "asset": ASSET,
                            "signature": sig_hex,
                            "signer": key.address,
                        }
                    }
                }
                
                auth_token = base64.b64encode(
                    json.dumps(token_payload, separators=(',', ':')).encode('utf-8')
                ).decode('utf-8')
                
                headers["Authorization"] = f"Bearer {auth_token}"
                
            except ImportError:
                raise X402PaymentError(
                    "coinbase-mdp-sdk not installed. Run: pip install coinbase-mdp-sdk",
                    required_amount=amount,
                    network=network,
                    asset=ASSET
                )
            
            # Retry with payment
            if method == "GET":
                resp = self._session.request("GET", url, params=data, headers=headers, timeout=self.timeout)
            else:
                resp = self._session.request(method, url, json=data, headers=headers, timeout=self.timeout)
        
        if resp.status_code != 200:
            raise Exception(f"API error {resp.status_code}: {resp.text[:300]}")
        
        return resp.json()
    
    @property
    def endpoints(self) -> List[str]:
        """List all available endpoint paths (normalized, e.g. '/parse/{bank}')."""
        return sorted(getattr(self, '_endpoints', {}).keys())
    
    @property
    def api_version(self) -> str:
        """API version (discovered on init)."""
        return getattr(self, '_version', 'unknown')

    # =====================
    # BANK PARSING
    # =====================
    
    def parse_statement(self, bank: str, pdf_data: Union[str, bytes], bank_type: str = "bank") -> dict:
        """
        Parse a bank statement PDF. Supports 9 Singapore banks.
        
        Args:
            bank: Bank identifier (dbs, posb, ocbc, uob, citi, maybank, standchart, trust, boc)
            pdf_data: base64-encoded PDF or raw bytes
            bank_type: 'bank' or 'credit_card' (default: 'bank')
        
        Example:
            result = client.parse_statement("dbs", pdf_base64)
        """
        if isinstance(pdf_data, bytes):
            pdf_data = base64.b64encode(pdf_data).decode('utf-8')
        return self._make_request("POST", f"/parse/{bank}", {
            "data": pdf_data,
            "bank_type": bank_type,
        })
    
    def extract_transactions(self, transactions: List[Dict]) -> dict:
        """
        AI-powered transaction entity extraction + categorization.
        
        Args:
            transactions: List of dicts with at least {'description': str}
        
        Returns merchant names, categories, locations, entity types.
        """
        return self._make_request("POST", "/extract/transactions", {"transactions": transactions})
    
    def summarize(self, transactions: List[Dict]) -> dict:
        """
        Generate AI financial summary from transactions.
        
        Returns: spending breakdown, recurring charges, monthly trends, savings rate.
        """
        return self._make_request("POST", "/summary", {"transactions": transactions})
    
    def spending_report(self, transactions: List[Dict]) -> dict:
        """Monthly spending report by category."""
        return self._make_request("POST", "/report/spending", {"transactions": transactions})
    
    def cash_flow(self, transactions: List[Dict]) -> dict:
        """Cash flow report — income vs expenses."""
        return self._make_request("POST", "/report/cash_flow", {"transactions": transactions})
    
    def subscriptions(self, transactions: List[Dict]) -> dict:
        """Detect recurring subscriptions and generate billing calendar."""
        return self._make_request("POST", "/report/subscriptions", {"transactions": transactions})
    
    # =====================
    # SGX STOCK DATA
    # =====================
    
    def sgx_stock(self, symbol: str) -> dict:
        """
        SGX stock fundamentals — price, PE, dividend, market cap, 52w range.
        
        Args:
            symbol: SGX ticker (e.g., 'DBS', 'OCBC', 'UOB', 'D05', 'BN4')
        """
        return self._make_request("POST", "/sgx/stock", {"symbol": symbol.upper()})
    
    def sgx_price(self, symbol: str) -> dict:
        """Real-time SGX stock price from Yahoo Finance."""
        return self._make_request("POST", "/sgx/price", {"symbol": symbol.upper()})
    
    def sgx_dividend(self, symbol: str) -> dict:
        """Dividend data: annual DPS, yield, frequency, next ex-date/pay_date."""
        return self._make_request("POST", "/sgx/dividend", {"symbol": symbol.upper()})
    
    def sgx_portfolio(self, symbols: List[str]) -> dict:
        """Multi-stock portfolio summary with total value, dividends, fundamentals."""
        return self._make_request("POST", "/sgx/portfolio", {"symbols": [s.upper() for s in symbols]})
    
    def sgx_screen(self, min_dividend_yield: float = 3.0, sort_by: str = "yield") -> dict:
        """Screen SGX stocks by dividend yield. Returns filtered list with fundamentals."""
        return self._make_request("POST", "/sgx/screen", {
            "min_dividend_yield": min_dividend_yield,
            "sort_by": sort_by,
        })
    
    def sgx_search(self, query: str) -> dict:
        """Search SGX stock database by company name or ticker."""
        return self._make_request("POST", "/sgx/search", {"query": query})
    
    # =====================
    # SALARY & TAX
    # =====================
    
    def salary_net(self, gross_annual: float, is_local_employee: bool = True) -> dict:
        """
        Calculate Singapore net salary (take-home after CPF, SDL, IT).
        
        Args:
            gross_annual: Annual gross salary in SGD
            is_local_employee: True for Singapore citizens/PR (CPF), False for foreigners
        """
        return self._make_request("POST", "/salary/net", {
            "gross_annual": gross_annual,
            "is_local_employee": is_local_employee,
        })
    
    def salary_benchmark(self, occupation: str, age_group: str = "25-29",
                         sector: str = "all", city: str = "singapore") -> dict:
        """Singapore salary market rates by occupation (MOM-backed comparables)."""
        return self._make_request("POST", "/salary/benchmark", {
            "occupation": occupation,
            "age_group": age_group,
            "sector": sector,
            "city": city,
        })
    
    def tax_income(self, gross_annual: float, year_of_assessment: int = 2026,
                   cpf_contributions: float = 0, donations: float = 0,
                   course_fees: float = 0, srs_contributions: float = 0,
                   mortgage_interest: float = 0, rental_income: float = 0,
                   taxable_income_from_other: float = 0, tax_savings: float = 0) -> dict:
        """
        Singapore income tax calculator (YA 2025/2026).
        Includes CPF, donations, course fees, SRS top-ups, mortgage interest deductions.
        """
        return self._make_request("POST", "/tax/income", {
            "gross_annual": gross_annual,
            "year_of_assessment": year_of_assessment,
            "cpf_contributions": cpf_contributions,
            "donations": donations,
            "course_fees": course_fees,
            "srs_contributions": srs_contributions,
            "mortgage_interest": mortgage_interest,
            "rental_income": rental_income,
            "taxable_income_from_other": taxable_income_from_other,
            "tax_savings": tax_savings,
        })
    
    def tax_corporate(self, chargeable_income: float) -> dict:
        """Singapore corporate tax calculator (17% flat rate)."""
        return self._make_request("POST", "/tax/corporate", {"chargeable_income": chargeable_income})
    
    # =====================
    # CPF & RETIREMENT
    # =====================
    
    def cpf_calculator(self, age: int, basic_salary: float,
                       bonus: float = 0, full_cpf: bool = True) -> dict:
        """
        CPF contribution calculator for Singapore residents.
        
        Args:
            age: Employee age (55 or below for full contributions)
            basic_salary: Monthly basic salary (SGD)
            bonus: Monthly bonus (SGD)
            full_cpf: True if both employer/employee contributions apply
        """
        return self._make_request("POST", "/cpf/calculator", {
            "age": age,
            "basic_salary": basic_salary,
            "bonus": bonus,
            "full_cpf": full_cpf,
        })
    
    def cpf_contributions(self, basic_salary: float, age: int,
                          bonus: float = 0) -> dict:
        """ CPF contribution breakdown (employee + employer shares)."""
        return self._make_request("POST", "/cpf/contributions", {
            "basic_salary": basic_salary,
            "age": age,
            "bonus": bonus,
        })
    
    def cpf_topup(self, age: int, cpf_balance: float, annual_income: float,
                  ciws_topup: float = 0) -> dict:
        """CPF Retirement Sum Top-Up (RSTU) calculator — tax relief benefits."""
        return self._make_request("POST", "/cpf/topup", {
            "age": age,
            "cpf_balance": cpf_balance,
            "annual_income": annual_income,
            "ciws_topup": ciws_topup,
        })
    
    def srs_calculator(self, age: int, annual_income: float,
                       cpf_savings: float = 0, retirement_age: int = 65) -> dict:
        """
        SRS (Supplementary Retirement Scheme) calculator.
        Tax deduction on contributions, projected growth, retirement withdrawal tax.
        """
        return self._make_request("POST", "/srs/calculator", {
            "age": age,
            "annual_income": annual_income,
            "cpf_savings": cpf_savings,
            "retirement_age": retirement_age,
        })
    
    def fire(self, age: int, annual_income: float, savings_rate: float = 0.5,
             current_investments: float = 0, target_retirement_age: int = 55) -> dict:
        """
        Singapore FIRE (Financial Independence / Retire Early) calculator.
        Combines CPF, SRS, and investment projections into a FIRE readiness score.
        
        Args:
            age: Current age
            annual_income: Annual gross income (SGD)
            savings_rate: Fraction saved each year (0.0–1.0)
            current_investments: Investable assets outside CPF/SRS (SGD)
            target_retirement_age: Target retirement age (default 55)
        """
        return self._make_request("POST", "/fire", {
            "age": age,
            "annual_income": annual_income,
            "savings_rate": savings_rate,
            "current_investments": current_investments,
            "target_retirement_age": target_retirement_age,
        })
    
    def savings_rates(self) -> dict:
        """Compare savings account interest rates across Singapore banks."""
        return self._make_request("GET", "/savings/rates", {})
    
    def savings_optimize(self, monthly_income: float, expenses: Dict[str, float],
                         goals: List[Dict] = None) -> dict:
        """Personalized savings optimization with goal-based recommendations."""
        return self._make_request("POST", "/savings/optimize", {
            "monthly_income": monthly_income,
            "expenses": expenses,
            "goals": goals or [],
        })
    
    # =====================
    # INVESTMENT
    # =====================
    
    def invest_dca(self, monthly_investment: float, years: int,
                   expected_return: float = 0.08, compare: str = "cpf_oa") -> dict:
        """
        Dollar Cost Averaging simulator — compare IWLU ETF vs CPF OA vs SSB.
        
        Args:
            monthly_investment: SGD amount to invest monthly
            years: Investment horizon
            expected_return: Expected annual return (default 8%)
            compare: Comparison mode — 'cpf_oa', 'ssb', 'all'
        """
        return self._make_request("POST", "/invest/dca", {
            "monthly_investment": monthly_investment,
            "years": years,
            "expected_return": expected_return,
            "compare": compare,
        })
    
    def invest_grow(self, initial_amount: float, monthly_topup: float = 0,
                    years: int = 10, expected_return: float = 0.08) -> dict:
        """
        Investment growth calculator — lump sum + recurring topup scenarios.
        Compares CPF OA vs SA vs liquid investments.
        """
        return self._make_request("POST", "/invest/grow", {
            "initial_amount": initial_amount,
            "monthly_topup": monthly_topup,
            "years": years,
            "expected_return": expected_return,
        })
    
    # =====================
    # PROPERTY
    # =====================
    
    def bto_affordability(self, annual_household_income: float,
                          flat_type: str = "4-room", location: str = "any") -> dict:
        """
        BTO affordability calculator — estimated loan, monthly payment, eligible subsidy.
        
        Args:
            annual_household_income: Combined annual household income (SGD)
            flat_type: '2-room', '3-room', '4-room', '5-room', '3Gen'
            location: 'north', 'northeast', 'east', 'west', 'central' or 'any'
        """
        return self._make_request("POST", "/bto/affordability", {
            "annual_household_income": annual_household_income,
            "flat_type": flat_type,
            "location": location,
        })
    
    def hdb_resale(self, town: str, flat_type: str = "4-room",
                   storey_range: str = "10-19", lease: str = "99-year") -> dict:
        """
        HDB resale price estimate for a given town and flat type.
        Uses recent transactions and market benchmarks.
        """
        return self._make_request("POST", "/hdb/resale", {
            "town": town,
            "flat_type": flat_type,
            "storey_range": storey_range,
            "lease": lease,
        })
    
    def property_tax(self, annual_value: float, owner_occupied: bool = True,
                     property_type: str = "condo") -> dict:
        """Singapore property tax calculator (AV-based, progressive rates)."""
        return self._make_request("POST", "/property/tax", {
            "annual_value": annual_value,
            "owner_occupied": owner_occupied,
            "property_type": property_type,
        })
    
    def rental_yield(self, property_price: float, monthly_rent: float,
                     property_type: str = "condo", district: str = "CCR") -> dict:
        """
        Singapore property rental yield calculator.
        Returns gross yield, net yield (after fees), benchmark vs market averages.
        """
        return self._make_request("POST", "/property/rental-yield", {
            "property_price": property_price,
            "monthly_rent": monthly_rent,
            "property_type": property_type,
            "district": district,
        })
    
    def mortgage_compare(self, property_price: float, loan_amount: float,
                         loan_tenure_years: int = 20, interest_rate: float = 2.5,
                         existing_loan: float = 0) -> dict:
        """Compare mortgage options and estimate monthly payments."""
        return self._make_request("POST", "/mortgage/compare", {
            "property_price": property_price,
            "loan_amount": loan_amount,
            "loan_tenure_years": loan_tenure_years,
            "interest_rate": interest_rate,
            "existing_loan": existing_loan,
        })
    
    def absd(self, citizenship: str, property_count: int,
             is_buyer_edm: bool = False) -> dict:
        """
        ABSD (Additional Buyer's Stamp Duty) calculator.
        
        Args:
            citizenship: 'singaporean', 'pr', 'foreigner', 'entity'
            property_count: Number of properties owned (including the one being purchased)
            is_buyer_edm: True if buying from developer (enjoys remission)
        """
        return self._make_request("POST", "/absd/calculator", {
            "citizenship": citizenship,
            "property_count": property_count,
            "is_buyer_edm": is_buyer_edm,
        })
    
    def condo_maintenance(self, property_type: str = "condo", floor_area: float = 100,
                          storey: int = 15) -> dict:
        """Estimate monthly condo maintenance fees (SGD psf basis)."""
        return self._make_request("POST", "/condo/maintenance", {
            "property_type": property_type,
            "floor_area": floor_area,
            "storey": storey,
        })
    
    # =====================
    # UTILITIES & SINGAPORE
    # =====================
    
    def utilities_estimate(self, house_type: str = "hdb-4room",
                           electricity_usage_kwh: float = 400) -> dict:
        """Estimate monthly utilities (electricity, water, gas) for Singapore homes."""
        return self._make_request("POST", "/utilities/estimate", {
            "house_type": house_type,
            "electricity_usage_kwh": electricity_usage_kwh,
        })
    
    def electricity_compare(self, consumption_kwh: float = 400,
                            tenure_months: int = 12) -> dict:
        """Compare electricity plans across Singapore retailers (EMA data)."""
        return self._make_request("POST", "/electricity/compare", {
            "consumption_kwh": consumption_kwh,
            "tenure_months": tenure_months,
        })
    
    def school_nearby(self, postal_code: str, level: str = "primary",
                       radius_km: float = 2.0) -> dict:
        """
        Find nearby schools (primary or secondary) by Singapore postal code.
        Returns school names, distances, affiliation, and PSLE cutoff scores.
        """
        return self._make_request("POST", "/school/nearby", {
            "postal_code": postal_code,
            "level": level,
            "radius_km": radius_km,
        })
    
    def hawker_nearby(self, postal_code: str, radius_km: float = 1.0) -> dict:
        """Find nearby hawker centres by Singapore postal code."""
        return self._make_request("POST", "/hawker/nearby", {
            "postal_code": postal_code,
            "radius_km": radius_km,
        })
    
    def holidays(self, year: int = 2026) -> dict:
        """List Singapore public holidays for a given year."""
        return self._make_request("GET", f"/holidays/singapore?year={year}", {})
    
    def coe_prices(self) -> dict:
        """Latest COE premiums for each category (A/B/C/D/E/F) from LTA data."""
        return self._make_request("GET", "/coe/prices", {})
    
    def car_loan(self, purchase_price: float = 100000,
                 loan_amount: float = 80000, loan_tenure_months: int = 60,
                 interest_rate: float = 2.78, coe_expiry_date: str = "2030-05-31") -> dict:
        """CAR LOAN & PARF calculator — monthly repayment + PARF estimate."""
        return self._make_request("POST", "/car/loan", {
            "purchase_price": purchase_price,
            "loan_amount": loan_amount,
            "loan_tenure_months": loan_tenure_months,
            "interest_rate": interest_rate,
            "coe_expiry_date": coe_expiry_date,
        })
    
    def goal_plan(self, goal_type: str, target_amount: float,
                  current_savings: float = 0, monthly_contribution: float = 0,
                  years_to_goal: int = 5) -> dict:
        """
        Personalized financial goal planner.
        
        goal_type: emergency_fund, home_down_payment, retirement, education, 
                  wedding, car, vacation, investment, custom
        """
        return self._make_request("POST", "/goal/plan", {
            "goal_type": goal_type,
            "target_amount": target_amount,
            "current_savings": current_savings,
            "monthly_contribution": monthly_contribution,
            "years_to_goal": years_to_goal,
        })
    
    def business_lookup(self, uen: str) -> dict:
        """Singapore UEN/Business profile lookup — entity name, type, status, address."""
        return self._make_request("POST", "/business/lookup", {"uen": uen})
    
    def ssb_rates(self, year: int = 2026) -> dict:
        """Singapore Savings Bond interest rates — latest MAS issue."""
        return self._make_request("GET", f"/ssb/rates?year={year}", {})
    
    def ssb_calculator(self, investment_amount: float, hold_until_year: int = 10) -> dict:
        """SSB maturity value calculator with year-by-year interest breakdown."""
        return self._make_request("POST", "/ssb/calculator", {
            "investment_amount": investment_amount,
            "hold_until_year": hold_until_year,
        })
    
    def retirement_community(self, location: str = "any",
                              budget: int = 500000, flat_type: str = "2-room") -> dict:
        """Find Singapore retirement communities (HDB, condo, landed)."""
        return self._make_request("POST", "/retirement/community", {
            "location": location,
            "budget": budget,
            "flat_type": flat_type,
        })
    
    def financial_health_score(self, age: int, monthly_income: float,
                               monthly_expenses: float, cpf_balance: float,
                               investments: float = 0, debts: float = 0) -> dict:
        """Singapore financial health score (0-100) with personalized recommendations."""
        return self._make_request("POST", "/financial/health", {
            "age": age,
            "monthly_income": monthly_income,
            "monthly_expenses": monthly_expenses,
            "cpf_balance": cpf_balance,
            "investments": investments,
            "debts": debts,
        })
    
    def forex_convert(self, from_currency: str, to_currency: str,
                       amount: float) -> dict:
        """Currency conversion using live forex rates."""
        return self._make_request("POST", "/forex/convert", {
            "from": from_currency,
            "to": to_currency,
            "amount": amount,
        })
    
    def invoice(self, amount: float, currency: str = "SGD",
                description: str = "", pay_to: str = "") -> dict:
        """Generate a payment request / invoice using x402 protocol."""
        return self._make_request("POST", "/invoice", {
            "amount": amount,
            "currency": currency,
            "description": description,
            "pay_to": pay_to,
        })
    
    # =====================
    # UTILITY
    # =====================
    
    def health(self) -> dict:
        """Check API health and available endpoints."""
        return self._make_request("GET", "/health", {})
    
    def __repr__(self):
        return f"<X402Financial base_url={self.base_url} version={self._version}>"


# ── Quick demo / test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("x402 Financial Python Client")
    print("=" * 50)
    
    client = X402Financial()
    print(f"Auto-discovered API: {client.base_url}")
    print(f"Version: {client.api_version}")
    print(f"Endpoints available: {len(client.endpoints)}")
    print()
    print("Available methods:")
    for name in sorted(dir(client)):
        if not name.startswith('_') and callable(getattr(client, name)):
            print(f"  .{name}(...)")
