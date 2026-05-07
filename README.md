# x402 Financial — Python Client

A Python client for the **x402 Financial Data API** — Singapore's most comprehensive financial data API powered by the x402 payment protocol (Coinbase).

**Pay with USDC on Base (eip155:8453) per request. No API keys. No subscriptions.**

## Table of Contents

- [Why This API?](#why-this-api)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [API Coverage](#api-coverage)
- [How x402 Payments Work](#how-x402-payments-work)
- [For AI Agents](#for-ai-agents)
- [Links](#links)

---

## Why This API?

Most financial APIs require monthly subscriptions, API keys, and charge flat fees regardless of usage. The x402 Financial Data API charges **per request** in USDC — you pay only for what you use.

**Target users:**
- AI agents and assistants that need Singapore financial data on-demand
- Developers building personal finance tools (no commitment required)
- Automated workflows that need occasional financial calculations

**Unique value for Singapore:**
- Bank statement parsing for 9 Singapore banks (DBS, POSB, OCBC, UOB, Citi, Maybank, StanChart, Trust, BOC)
- SGX stock data (real-time prices, dividends, fundamentals)
- Singapore-specific: CPF calculators, IRAS tax, HDB/BTO, COE, SRS, FIRE
- DCA comparison: IWLU vs CPF OA vs Singapore Savings Bonds

No other API offers this combination of Singapore-specific financial data with per-request pricing.

---

## Quick Start

```bash
pip install x402-financial
```

```python
from x402_financial import X402Financial

# Initialize with wallet seed (from https://keys.coinbase.com)
client = X402Financial(wallet_seed="0x...")

# Check API health
health = client.health()
print(f"API version: {health['version']}")

# Singapore take-home salary
result = client.salary_net(gross_annual=80000)
print(f"Monthly take-home: ${result['net_monthly']:,.2f}")

# Investment comparison: IWLU vs CPF OA vs SSB
result = client.invest_dca(monthly_investment=500, years=10)
print(f"Best approach: {result['ranking'][0]}")

# SGX stock profile
result = client.sgx_stock("DBS")
print(f"DBS: ${result['price']} (PE: {result['pe_ratio']})")

# Parse bank statement
with open("statement.pdf", "rb") as f:
    result = client.parse_statement("dbs", f.read())
print(f"Found {result['transaction_count']} transactions")
```

## Installation

```bash
pip install x402-financial
```

For automatic x402 payment support (handles payment signing automatically):
```bash
pip install x402-financial[coinbase]
```

Or set the `WALLET_SEED` environment variable:
```bash
export WALLET_SEED="0x..."
```

**Get a wallet seed at:** https://keys.coinbase.com

---

## API Coverage

| Category | Endpoints | Price |
|----------|-----------|-------|
| **Bank Parsing** | /parse/{bank} (9 banks) | $0.02 |
| **SGX Stocks** | /sgx/stock, /sgx/price, /sgx/dividend, /sgx/portfolio, /sgx/screen | $0.005–$0.03 |
| **Salary & Tax** | /salary/net, /salary/benchmark, /tax/income, /tax/corporate | $0.01–$0.02 |
| **CPF & Retirement** | /cpf/calculator, /cpf/contributions, /cpf/topup, /srs/calculator, /fire | $0.01–$0.02 |
| **Investments** | /invest/dca, /invest/grow, /forex/convert, /ssb/rates, /ssb/calculator | $0.005–$0.01 |
| **Property** | /bto/affordability, /hdb/resale, /property/tax, /property/absd, /mortgage/compare | $0.01–$0.02 |
| **Reports** | /summary, /report/spending, /report/cash-flow, /report/subscriptions | $0.01 |
| **Utilities** | /cost/estimate, /electricity/compare, /coe, /holidays/singapore | $0.005–$0.01 |

**Free endpoints:**
- `GET /health` — API health check
- `GET /merchant/clean` — Clean a transaction description
- `GET /holidays/singapore` — Singapore public holidays

### Python Methods (39 total)

```python
# Bank statement parsing
client.parse_statement("dbs", pdf_bytes)      # 9 Singapore banks
client.extract_transactions(tx_list)           # AI entity extraction

# SGX stock data
client.sgx_stock("DBS")                        # Price, PE, EPS, market cap
client.sgx_dividend("DBS")                     # Dividend yield, annual dividend
client.sgx_price("UOB")                        # Real-time price from Yahoo Finance

# CPF & retirement
client.cpf_contributions(age=35, monthly_basic=5000)   # Employee + employer
client.cpf_calculator(age=30, basic_salary=6000)        # OA/SA/RA at retirement
client.cpf_topup(annual_income=80000, extra=2000)      # Top-up optimizer
client.fire(age=30, annual_expenses=40000)              # FIRE readiness

# Investments
client.invest_dca(monthly_investment=500, years=10)   # IWLU vs CPF OA vs SSB
client.invest_grow(initial=10000, monthly=500, years=20) # Compound growth
client.ssb_calculator(amount=10000, tenure=3)           # Singapore Savings Bonds
client.ssb_rates()                                     # Current SSB rates

# Salary & tax
client.salary_net(gross_annual=80000)          # Singapore take-home
client.tax_income(annual_income=80000)        # IRAS income tax

# Property
client.bto_affordability(income=8000, loan_taken=0)    # BTO affordability
client.hdb_resale(town="Tampines", flat_type="4room")  # HDB resale prices
client.property_absd(price=1000000, buyer_type="citizen")
client.mortgage_compare(loan_amount=400000, tenure=20)

# Reports (all take transaction list)
client.summary(transactions)                   # Financial summary
client.report_spending(transactions)           # Expense breakdown
client.report_cash_flow(transactions)          # Cash flow analysis
client.report_subscriptions(transactions)      # Recurring charges detection

# Utilities
client.electricity_compare()                   # Singapore power retailer comparison
client.coe_prices()                            # Latest COE premiums
client.holidays(year=2026)                     # Singapore public holidays
client.cost_estimate(category="food")         # Singapore CPI/purchasing power
```

---

## How x402 Payments Work

1. You make a request without payment → API returns HTTP 402 with payment requirements
2. The `X402Financial` client extracts the payment spec (amount, network, asset)
3. It signs the payment with your wallet seed using Coinbase's SDK
4. It retries the request with the signed payment header
5. You get the data — the API receives automatic USDC payment

```python
# What happens under the hood:
# 1. Request without payment
# 2. API responds: HTTP 402 { "x402Version": 2, "resource": {...}, "accepts": [...] }
# 3. Client signs payment with WALLET_SEED
# 4. Client retries with Authorization: Bearer <payment_token>
# 5. API returns data + executes USDC transfer automatically
```

No need to manage API keys, subscriptions, or billing cycles.

---

## For AI Agents

```python
# AI agent usage pattern:
from x402_financial import X402Financial

client = X402Financial(wallet_seed=os.environ["WALLET_SEED"])

# Agents can discover all paid endpoints dynamically:
endpoints = client.endpoints()
for ep in endpoints:
    print(f"{ep['method']} {ep['path']} — {ep['price']}")

# Or just call what you need — pricing is transparent
result = client.cpf_calculator(age=35, basic_salary=6500)
```

AI agents can pay for financial data on-demand without pre-purchasing API credits.

---

## Links

- **API**: https://x402-financial-api.life.conway.tech
- **x402 Protocol**: https://x402.org
- **Wallet**: https://keys.coinbase.com
- **GitHub (API)**: https://github.com/nebmil569/x402-financial-data-api
- **GitHub (Client)**: https://github.com/nebmil569/x402-financial-client

## License

MIT