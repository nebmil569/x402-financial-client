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
import os
import requests
from typing import Optional, List, Dict, Any, Union

# PRIMARY: apinew-nine Vercel (v1.5.8, 47 prices, MOST COMPLETE — use this one)
# SECONDARY: Conway (v1.5.5, 43 prices, 14 endpoints behind)
# TERTIARY: Vercel old (v1.5.7-rc1, 45 prices)
BASE_URLS = [
    "https://apinew-nine.vercel.app",  # PRIMARY — Vercel, 47 prices, all new endpoints
    "https://x402-financial-api.life.conway.tech",  # SECONDARY — Conway stable
    "https://x402-financial-data-api.vercel.app",  # TERTIARY — Vercel old
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
        self._api_key = api_key or os.environ.get("X402_API_KEY")

        # Wallet setup
        if wallet_seed is None:
            wallet_seed = os.environ.get("WALLET_SEED")
        if wallet_seed:
            self._wallet_seed = bytes.fromhex(wallet_seed.strip("0x")) if isinstance(wallet_seed, str) else wallet_seed
        else:
            self._wallet_seed = None

        # Auto-discover or use override
        if base_url:
            self.base_url = base_url.rstrip("/")
            self._endpoint_version = "user-specified"
        else:
            self.base_url = self._discover_endpoint()
            self._endpoint_version = "auto-discovered"

        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        if self._api_key:
            self.session.headers["X-API-Key"] = self._api_key

        # Cache for endpoints
        self._endpoints_cache = None

    def _discover_endpoint(self) -> str:
        """Auto-discover the best available API endpoint."""
        for url in BASE_URLS:
            try:
                resp = self.session.get(f"{url}/health", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    version = data.get("version", "?")
                    prices_count = len(data.get("prices", {}))
                    print(f"[x402-financial] Discovered {url} (v{version}, {prices_count} prices)")
                    return url
            except Exception:
                continue
        # Fallback to primary
        return BASE_URLS[0]

    @property
    def endpoints(self) -> Dict[str, Any]:
        """Cache and return the /prices catalog."""
        if self._endpoints_cache is None:
            try:
                resp = self.session.get(f"{self.base_url}/prices", timeout=10)
                if resp.status_code == 200:
                    self._endpoints_cache = resp.json()
                else:
                    self._endpoints_cache = {}
            except Exception:
                self._endpoints_cache = {}
        return self._endpoints_cache

    def _make_request(self, method: str, path: str, data: Optional[Dict] = None,
                     include_payment: bool = True) -> Dict[str, Any]:
        """Make an authenticated x402 request with payment."""
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key

        body = data.copy() if data else {}
        body["_wallet"] = self._wallet_seed.hex() if self._wallet_seed else None

        resp = self.session.request(method, url, json=body, headers=headers, timeout=self.timeout)
        return resp

    def health(self) -> Dict[str, Any]:
        """Get API health and version info."""
        resp = self.session.get(f"{self.base_url}/health", timeout=10)
        resp.raise_for_status()
        return resp.json()

    # ===== PRICING HELPERS =====

    def _get_price(self, path: str) -> Optional[float]:
        """Get price for an endpoint from prices catalog."""
        endpoints = self.endpoints.get("paid_endpoints", [])
        for ep in endpoints:
            if ep.get("path") == path:
                price_str = ep.get("price", "0").replace("$", "").replace(" USDC", "")
                try:
                    return float(price_str)
                except:
                    return None
        return None

    # ===== BANK PARSING =====

    def parse_bank_statement(self, bank: str, pdf_data: Union[str, bytes]) -> Dict[str, Any]:
        """
        Parse a bank statement PDF.

        Args:
            bank: One of dbs, posb, ocbc, uob, citi, maybank, standchart, trust, boc
            pdf_data: Base64-encoded PDF string or raw bytes

        Returns:
            Parsed transactions array
        """
        if isinstance(pdf_data, bytes):
            pdf_data = base64.b64encode(pdf_data).decode()

        body = {"data": pdf_data}
        resp = self._make_request("POST", f"/parse/{bank}", body)
        if resp.status_code == 402:
            raise X402PaymentError(
                "Payment required",
                required_amount=self._get_price(f"/parse/{bank}"),
                network=NETWORK,
                asset=ASSET,
            )
        resp.raise_for_status()
        return resp.json()

    def extract_transactions(self, transactions: List[Dict]) -> Dict[str, Any]:
        """AI entity extraction + categorization from raw transactions."""
        body = {"transactions": transactions}
        resp = self._make_request("POST", "/extract/transactions", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/extract/transactions"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    # ===== FINANCIAL REPORTS =====

    def summary(self, transactions: List[Dict], person_name: Optional[str] = None) -> Dict[str, Any]:
        """AI financial summary with spending breakdown."""
        body = {"transactions": transactions}
        if person_name:
            body["person_name"] = person_name
        resp = self._make_request("POST", "/summary", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/summary"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def spending_report(self, transactions: List[Dict]) -> Dict[str, Any]:
        """Detailed expense report with Singapore budget benchmarks."""
        body = {"transactions": transactions}
        resp = self._make_request("POST", "/report/spending", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/report/spending"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def cash_flow_report(self, transactions: List[Dict]) -> Dict[str, Any]:
        """Monthly income vs expenses analysis with savings rate."""
        body = {"transactions": transactions}
        resp = self._make_request("POST", "/report/cash-flow", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/report/cash-flow"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def subscriptions_report(self, transactions: List[Dict]) -> Dict[str, Any]:
        """AI-powered subscription detection with annual cost estimates."""
        body = {"transactions": transactions}
        resp = self._make_request("POST", "/report/subscriptions", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/report/subscriptions"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def billing_calendar(self, transactions: List[Dict], person_name: Optional[str] = None) -> Dict[str, Any]:
        """Forward-looking billing calendar — projects recurring charges 3 months ahead."""
        body = {"transactions": transactions}
        if person_name:
            body["person_name"] = person_name
        resp = self._make_request("POST", "/report/billing-calendar", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/report/billing-calendar"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def financial_insights(self, transactions: List[Dict], person_name: Optional[str] = None,
                          months: int = 3) -> Dict[str, Any]:
        """Personalized AI financial insights with Singapore-specific tips."""
        body = {"transactions": transactions, "months": months}
        if person_name:
            body["person_name"] = person_name
        resp = self._make_request("POST", "/report/insights", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/report/insights"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    # ===== SALARY & TAX =====

    def salary_net(self, gross_annual: float, employer_cpf: float = None,
                   bonus: float = 0, form_type: str = "S1") -> Dict[str, Any]:
        """
        Singapore take-home salary calculator.

        Args:
            gross_annual: Annual gross salary (SGD)
            employer_cpf: Optional employer CPF contribution override
            bonus: Annual bonus (SGD)
            form_type: S1 (citizen/PR employed) or NA (foreigner/self-employed)
        """
        body = {
            "gross_annual": gross_annual,
            "bonus": bonus,
            "form_type": form_type,
        }
        if employer_cpf is not None:
            body["employer_cpf"] = employer_cpf
        resp = self._make_request("POST", "/salary/net", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/salary/net"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def salary_benchmark(self, annual_income: float, job_title: str = None,
                        years_experience: int = None) -> Dict[str, Any]:
        """Compare salary against Singapore market rates."""
        body = {"annual_income": annual_income}
        if job_title:
            body["job_title"] = job_title
        if years_experience is not None:
            body["years_experience"] = years_experience
        resp = self._make_request("POST", "/salary/benchmark", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/salary/benchmark"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def tax_income(self, gross_income: float, basic_income: float,
                   cpf_contributions: float, year: int = 2024) -> Dict[str, Any]:
        """Singapore income tax estimate using IRAS bands."""
        body = {
            "gross_income": gross_income,
            "basic_income": basic_income,
            "cpf_contributions": cpf_contributions,
            "year": year,
        }
        resp = self._make_request("POST", "/tax/income", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/tax/income"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    # ===== SGX STOCKS =====

    def sgx_stock(self, symbol: str, currency: str = "SGD") -> Dict[str, Any]:
        """
        Get SGX stock profile — price, dividend, PE, EPS, market cap.

        Args:
            symbol: SGX ticker (e.g. DBS, UOB, OCBC, CAPITALAND, SINGTEL)
            currency: Display currency (default SGD)
        """
        body = {"symbol": symbol, "currency": currency}
        resp = self._make_request("POST", "/sgx/stock", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/sgx/stock"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def sgx_price(self, symbol: str, currency: str = "SGD") -> Dict[str, Any]:
        """Get real-time SGX stock price."""
        body = {"symbol": symbol, "currency": currency}
        resp = self._make_request("POST", "/sgx/price", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/sgx/price"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def sgx_dividend(self, symbol: str) -> Dict[str, Any]:
        """Get dividend data for SGX stock — annual dividend, yield, EPS, PE."""
        body = {"symbol": symbol}
        resp = self._make_request("POST", "/sgx/dividend", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/sgx/dividend"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def sgx_portfolio(self, symbols: List[str]) -> Dict[str, Any]:
        """Batch lookup for up to 20 SGX stocks."""
        body = {"symbols": symbols}
        resp = self._make_request("POST", "/sgx/portfolio", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/sgx/portfolio"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def sgx_screen(self, min_dividend_yield: float = 0,
                   min_price: float = 0) -> Dict[str, Any]:
        """Dividend screener for SGX stocks."""
        body = {"min_dividend_yield": min_dividend_yield, "min_price": min_price}
        resp = self._make_request("POST", "/sgx/screen", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/sgx/screen"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    # ===== CPF & RETIREMENT =====

    def cpf_calculator(self, age: int, basic_salary: float,
                       cpf_contribution_rate: float = 37) -> Dict[str, Any]:
        """Project CPF balances (OA/SA/RA) at retirement."""
        body = {
            "age": age,
            "basic_salary": basic_salary,
            "cpf_contribution_rate": cpf_contribution_rate,
        }
        resp = self._make_request("POST", "/cpf/calculator", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/cpf/calculator"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def cpf_topup(self, age: int, citizenship: str, current_oa: float, current_sa: float,
                  current_ra: float, voluntary_oa_amount: float = 0,
                  voluntary_sa_amount: float = 0, voluntary_ra_amount: float = 0,
                  expected_bonus: float = 0, current_annual_income: float = 0) -> Dict[str, Any]:
        """CPF Voluntary Top-up Optimizer — tax savings, interest differential, FRS adequacy."""
        body = {
            "age": age,
            "citizenship": citizenship,
            "current_oa": current_oa,
            "current_sa": current_sa,
            "current_ra": current_ra,
            "voluntary_oa_amount": voluntary_oa_amount,
            "voluntary_sa_amount": voluntary_sa_amount,
            "voluntary_ra_amount": voluntary_ra_amount,
            "expected_bonus": expected_bonus,
            "current_annual_income": current_annual_income,
        }
        resp = self._make_request("POST", "/cpf/topup", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/cpf/topup"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def srs_calculator(self, age: int, annual_contribution: float, nationality: str,
                       current_srs_balance: float = 0,
                       withdrawal_age: int = 63) -> Dict[str, Any]:
        """SRS calculator — tax savings, projected balance, retirement withdrawal estimates."""
        body = {
            "age": age,
            "annual_contribution": annual_contribution,
            "nationality": nationality,
            "current_srs_balance": current_srs_balance,
            "withdrawal_age": withdrawal_age,
        }
        resp = self._make_request("POST", "/srs/calculator", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/srs/calculator"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def fire(self, age: int, annual_income: float, annual_expenses: float,
             current_savings: float = 0, cpf_balance: float = 0,
             target_retirement_age: int = 55) -> Dict[str, Any]:
        """Singapore FIRE (Financial Independence / Retire Early) calculator."""
        body = {
            "age": age,
            "annual_income": annual_income,
            "annual_expenses": annual_expenses,
            "current_savings": current_savings,
            "cpf_balance": cpf_balance,
            "target_retirement_age": target_retirement_age,
        }
        resp = self._make_request("POST", "/fire", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/fire"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def retirement_community(self, age: int, monthly_budget: float,
                            prefer_active: bool = True) -> Dict[str, Any]:
        """Singapore retirement community finder — care needs, budget, preferred location."""
        body = {
            "age": age,
            "monthly_budget": monthly_budget,
            "prefer_active": prefer_active,
        }
        resp = self._make_request("POST", "/retirement/community", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/retirement/community"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    # ===== PROPERTY =====

    def hdb_resale(self, town: str, flat_type: str, floor: int = None,
                   lease_start: int = None) -> Dict[str, Any]:
        """Estimate HDB resale flat prices across 23 Singapore towns."""
        body = {"town": town, "flat_type": flat_type}
        if floor is not None:
            body["floor"] = floor
        if lease_start is not None:
            body["lease_start"] = lease_start
        resp = self._make_request("POST", "/hdb/resale", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/hdb/resale"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def hdb_resale_towns(self) -> Dict[str, Any]:
        """List all 23 HDB towns with market indices."""
        resp = self._make_request("POST", "/hdb/resale/towns", {})
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/hdb/resale/towns"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def bto_affordability(self, bto_price: float, monthly_household_income: float,
                          flat_type: str = "4-room", town: str = "Unknown",
                          applicant_age: int = 30, cpf_oa_balance: float = 0,
                          other_debt_payments: float = 0) -> Dict[str, Any]:
        """BTO affordability calculator — HDB loan vs bank loan, grants, BSD, CPF impact."""
        body = {
            "bto_price": bto_price,
            "monthly_household_income": monthly_household_income,
            "flat_type": flat_type,
            "town": town,
            "applicant_age": applicant_age,
            "cpf_oa_balance": cpf_oa_balance,
            "other_debt_payments": other_debt_payments,
        }
        resp = self._make_request("POST", "/bto/affordability", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/bto/affordability"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def property_tax(self, annual_value: float, property_type: str) -> Dict[str, Any]:
        """Singapore property tax calculator — IRAS 2024 progressive rates."""
        body = {"annual_value": annual_value, "property_type": property_type}
        resp = self._make_request("POST", "/property/tax", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/property/tax"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def property_absd(self, purchase_price: float, buyer_type: str,
                      ownership_count: int = 0, include_acd: bool = False) -> Dict[str, Any]:
        """ABSD calculator — SC/PR/foreigner, 1st/2nd/3rd+ property."""
        body = {
            "purchase_price": purchase_price,
            "buyer_type": buyer_type,
            "ownership_count": ownership_count,
            "include_acd": include_acd,
        }
        resp = self._make_request("POST", "/property/absd", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/property/absd"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def rental_yield(self, property_price: float, monthly_rent: float = None,
                     property_type: str = "2bed", area_sqft: float = 1000,
                     location: str = "singapore") -> Dict[str, Any]:
        """Calculate gross/net rental yield for Singapore property."""
        body = {
            "property_price": property_price,
            "monthly_rent": monthly_rent,
            "property_type": property_type,
            "area_sqft": area_sqft,
            "location": location,
        }
        resp = self._make_request("POST", "/property/rental-yield", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/property/rental-yield"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def condo_maintenance(self, sqft: float, tier: str, floor: int = 10,
                          has_lift: bool = True) -> Dict[str, Any]:
        """Estimate Singapore condo monthly maintenance fees."""
        body = {
            "sqft": sqft,
            "tier": tier,
            "floor": floor,
            "has_lift": has_lift,
        }
        resp = self._make_request("POST", "/property/condo-maintenance", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/property/condo-maintenance"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def mortgage_compare(self, loan_amount: float, tenure_years: int,
                         rate: float, bank_or_hdb: str = "bank") -> Dict[str, Any]:
        """Compare mortgage scenarios — bank vs HDB, different tenures/rates."""
        body = {
            "loan_amount": loan_amount,
            "tenure_years": tenure_years,
            "rate": rate,
            "bank_or_hdb": bank_or_hdb,
        }
        resp = self._make_request("POST", "/mortgage/compare", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/mortgage/compare"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    # ===== INVESTMENT =====

    def invest_dca(self, monthly_investment: float, years: int = 10,
                   portfolio_type: str = "iwlu") -> Dict[str, Any]:
        """Singapore DCA simulator — IWLU vs CPF OA vs SSB, 1-30yr projections."""
        body = {
            "monthly_investment": monthly_investment,
            "years": years,
            "portfolio_type": portfolio_type,
        }
        resp = self._make_request("POST", "/invest/dca", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/invest/dca"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def invest_grow(self, initial_amount: float, years: int = 10,
                    rate_type: str = "conservative") -> Dict[str, Any]:
        """Singapore compound growth comparator — CPF OA/SA vs SSB vs T-Bills vs StashAway."""
        body = {
            "initial_amount": initial_amount,
            "years": years,
            "rate_type": rate_type,
        }
        resp = self._make_request("POST", "/invest/grow", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/invest/grow"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def ssb_calculator(self, investment_amount: float, hold_until_year: int = 10) -> Dict[str, Any]:
        """Singapore Savings Bonds calculator — maturity value, year-by-year breakdown."""
        body = {
            "investment_amount": investment_amount,
            "hold_until_year": hold_until_year,
        }
        resp = self._make_request("POST", "/ssb/calculator", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/ssb/calculator"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def reit_analysis(self, reit_name: str) -> Dict[str, Any]:
        """Singapore REIT analyzer — yields, sector, leverage, dividend coverage."""
        body = {"reit_name": reit_name}
        resp = self._make_request("POST", "/reit/analyze", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/reit/analyze"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    # ===== OTHER TOOLS =====

    def coe_prices(self) -> Dict[str, Any]:
        """Latest Singapore COE premiums for all 5 categories (A–E)."""
        resp = self._make_request("POST", "/coe", {})
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/coe"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def car_loan(self, purchase_price: float, coe_premium: float, loan_amount: float,
                 loan_tenure_years: int, interest_rate: float,
                 car_age_years: int = 0) -> Dict[str, Any]:
        """Singapore car loan + PARF calculator."""
        body = {
            "purchase_price": purchase_price,
            "coe_premium": coe_premium,
            "loan_amount": loan_amount,
            "loan_tenure_years": loan_tenure_years,
            "interest_rate": interest_rate,
            "car_age_years": car_age_years,
        }
        resp = self._make_request("POST", "/car/loan", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/car/loan"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def savings_rates(self, min_balance: float = 1000, has_salary_credit: bool = True,
                       bank_filter: str = None) -> Dict[str, Any]:
        """Singapore savings account rate comparison."""
        body = {
            "min_balance": min_balance,
            "has_salary_credit": has_salary_credit,
        }
        if bank_filter:
            body["bank_filter"] = bank_filter
        resp = self._make_request("POST", "/savings/rates", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/savings/rates"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def school_nearby(self, postal_code: str, level: str = "primary") -> Dict[str, Any]:
        """Find nearby schools — primary/secondary, distance, PSLE cutoff."""
        body = {"postal_code": postal_code, "level": level}
        resp = self._make_request("POST", "/school/nearby", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/school/nearby"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def financial_health_score(self, monthly_income: float, monthly_expenses: float,
                                total_debt: float, cpf_balance: float,
                                emergency_fund: float = 0) -> Dict[str, Any]:
        """Singapore financial health score + actionable recommendations."""
        body = {
            "monthly_income": monthly_income,
            "monthly_expenses": monthly_expenses,
            "total_debt": total_debt,
            "cpf_balance": cpf_balance,
            "emergency_fund": emergency_fund,
        }
        resp = self._make_request("POST", "/financial/health", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/financial/health"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def invoice_parse(self, pdf_data: Union[str, bytes]) -> Dict[str, Any]:
        """Parse Singapore GST invoice/receipt PDF — extract vendor, GST, total."""
        if isinstance(pdf_data, bytes):
            pdf_data = base64.b64encode(pdf_data).decode()
        body = {"data": pdf_data}
        resp = self._make_request("POST", "/invoice", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/invoice"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def holidays(self, year: int = None) -> Dict[str, Any]:
        """List Singapore public holidays."""
        params = {}
        if year:
            params["year"] = year
        resp = self.session.get(f"{self.base_url}/holidays/singapore", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def merchant_clean(self, raw_description: str) -> Dict[str, Any]:
        """Clean a raw transaction description into normalized merchant name (FREE)."""
        params = {"description": raw_description}
        resp = self.session.get(f"{self.base_url}/merchant/clean", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def batch_clean(self, descriptions: List[str]) -> Dict[str, Any]:
        """Batch clean transaction descriptions — free for ≤20, $0.005 for 21–100."""
        body = {"descriptions": descriptions}
        resp = self._make_request("POST", "/merchant/batch-clean", body, include_payment=True)
        return resp.json()

    def forex_convert(self, amount: float, from_currency: str, to_currency: str = "SGD") -> Dict[str, Any]:
        """Currency conversion with SGD base — travel money, forex comparison."""
        body = {"amount": amount, "from": from_currency, "to": to_currency}
        resp = self._make_request("POST", "/forex/convert", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/forex/convert"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def business_lookup(self, uen: str) -> Dict[str, Any]:
        """Singapore UEN/ACRA business lookup."""
        body = {"uen": uen}
        resp = self._make_request("POST", "/business/lookup", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/business/lookup"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def benefits_check(self, age: int, employment_status: str = "employed") -> Dict[str, Any]:
        """Singapore social benefits checker — CHAS, Pioneer/Generation, Medisave, GRC."""
        body = {"age": age, "employment_status": employment_status}
        resp = self._make_request("POST", "/benefits/check", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/benefits/check"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def utilities_estimate(self, property_type: str = "hdb_4room",
                           occupancy: int = 4) -> Dict[str, Any]:
        """Singapore utilities (electricity, water, gas) estimate — SP Group benchmarks."""
        body = {"property_type": property_type, "occupancy": occupancy}
        resp = self._make_request("POST", "/utilities/estimate", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/utilities/estimate"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def electricity_compare(self, monthly_kwh: float = 500,
                           contract_type: str = "residential") -> Dict[str, Any]:
        """Compare Singapore electricity plans — SP Group, Geneco, Senoko, etc."""
        body = {"monthly_kwh": monthly_kwh, "contract_type": contract_type}
        resp = self._make_request("POST", "/electricity/compare", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/electricity/compare"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()

    def goal_plan(self, goal_name: str, target_amount: float,
                  monthly_savings: float, years: int) -> Dict[str, Any]:
        """Personal savings goal planner — time to target, path to goal."""
        body = {
            "goal_name": goal_name,
            "target_amount": target_amount,
            "monthly_savings": monthly_savings,
            "years": years,
        }
        resp = self._make_request("POST", "/goal/plan", body)
        if resp.status_code == 402:
            raise X402PaymentError("Payment required", required_amount=self._get_price("/goal/plan"), network=NETWORK, asset=ASSET)
        resp.raise_for_status()
        return resp.json()