# x402 Financial — Python Client

> **Install:** `pip install x402-financial`
> **Docs:** https://github.com/nebmil569/x402-financial-data-api
> **API:** https://x402-financial-api.life.conway.tech

A Python client for the **x402 Financial Data API** — Singapore's most comprehensive AI-ready financial data API, powered by the x402 payment protocol (Coinbase, Base chain).

**Pay per request in USDC. No API keys. No subscriptions. Cancel anytime.**

---

## Features

- **67+ endpoints** for Singapore financial data
- **9-bank statement parsing**: DBS, POSB, OCBC, UOB, Citi, Maybank, StanChart, Trust, BOC
- **SGX stocks**: real-time prices, dividends, PE ratios, portfolio lookup
- **Singapore-specific**: CPF, SRS, IRAS tax, HDB/BTO, COE, FIRE, property tax, ABSD
- **Investment tools**: DCA simulator, compound growth, Savings Bonds, REIT analyzer
- **x402 v2 payments**: auto-handled — just pass your wallet seed

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

# Singapore take-home salary ($80k gross)
result = client.salary_net(gross_annual=80000)
print(f"Monthly take-home: ${result['net_monthly']:,.2f}")

# SGX stock profile
stock = client.sgx_stock("DBS")
print(f"DBS price: ${stock['price']}, yield: {stock['dividend']['dividend_yield_pct']}%")

# HDB resale price estimate
hdb = client.hdb_resale(town="Tampines", flat_type="4-room", floor=15)
print(f"Estimated resale: ${hdb['estimated_price']:,.0f}")

# DCA investment comparison
dca = client.invest_dca(monthly_investment=500, years=10)
print(f"Best approach: {dca['ranking'][0]}")
```

---

## How x402 Payments Work

The x402 protocol uses HTTP headers for payment authentication:

1. Get a wallet at [https://keys.coinbase.com](https://keys.coinbase.com)
2. Pass `wallet_seed` to `X402Financial()` — the client auto-handles payment signing
3. Each request costs $0.005–$0.05 USDC depending on endpoint complexity
4. Payment is atomic — if you don't have funds, you get a `402 Payment Required` response

No account creation. No API keys. No monthly fees.

---

## API Coverage

### Bank Statement Parsing
| Method | Description | Price |
|--------|-------------|-------|
| `parse_bank_statement(bank, pdf_data)` | Parse PDF from 9 Singapore banks | $0.02 |
| `extract_transactions(transactions)` | AI entity extraction + categorization | $0.01 |

### Financial Reports
| Method | Description | Price |
|--------|-------------|-------|
| `summary(transactions)` | AI financial summary + spending breakdown | $0.01 |
| `spending_report(transactions)` | Expense report with SG budget benchmarks | $0.01 |
| `cash_flow_report(transactions)` | Income vs expenses + savings rate | $0.01 |
| `subscriptions_report(transactions)` | Auto-detect subscriptions + annual cost | $0.01 |
| `billing_calendar(transactions)` | 3-month forward billing projections | $0.01 |
| `financial_insights(transactions)` | Personalized AI tips + action items | $0.01 |

### Salary & Tax
| Method | Description | Price |
|--------|-------------|-------|
| `salary_net(gross_annual)` | Singapore take-home salary calculator | $0.01 |
| `salary_benchmark(annual_income)` | Salary vs market rates comparison | $0.01 |
| `tax_income(gross, basic, cpf)` | IRAS income tax estimate | $0.02 |

### SGX Stocks
| Method | Description | Price |
|--------|-------------|-------|
| `sgx_stock(symbol)` | Full stock profile (price, div, PE, EPS) | $0.02 |
| `sgx_price(symbol)` | Real-time price only | $0.005 |
| `sgx_dividend(symbol)` | Dividend data + yield | $0.005 |
| `sgx_portfolio(symbols)` | Batch up to 20 stocks | $0.03 |
| `sgx_screen(min_dividend_yield)` | Dividend screener | $0.01 |

### CPF & Retirement
| Method | Description | Price |
|--------|-------------|-------|
| `cpf_calculator(age, basic_salary)` | Project OA/SA/RA at retirement | $0.02 |
| `cpf_topup(age, citizenship, ...)` | CPF voluntary top-up optimizer | $0.01 |
| `srs_calculator(age, annual_contribution, ...)` | SRS tax savings + retirement | $0.01 |
| `fire(age, annual_income, annual_expenses)` | FIRE calculator (Singapoer) | $0.01 |
| `retirement_community(age, monthly_budget)` | Find retirement communities | $0.01 |

### Property
| Method | Description | Price |
|--------|-------------|-------|
| `hdb_resale(town, flat_type)` | HDB resale price estimate (23 towns) | $0.01 |
| `hdb_resale_towns()` | List all towns + market indices | $0.01 |
| `bto_affordability(bto_price, monthly_household_income)` | BTO affordability calculator | $0.02 |
| `property_tax(annual_value, property_type)` | IRAS 2024 progressive tax | $0.01 |
| `property_absd(purchase_price, buyer_type)` | ABSD calculator (SC/PR/foreign) | $0.01 |
| `rental_yield(property_price, monthly_rent)` | Gross/net rental yield | $0.01 |
| `condo_maintenance(sqft, tier)` | Condo monthly fee estimate | $0.01 |
| `mortgage_compare(loan_amount, tenure, rate)` | Bank vs HDB mortgage comparison | $0.01 |

### Investment
| Method | Description | Price |
|--------|-------------|-------|
| `invest_dca(monthly_investment, years)` | IWLU vs CPF OA vs SSB comparison | $0.01 |
| `invest_grow(initial_amount, years)` | Compound growth: CPF/SSB/T-Bills/StashAway | $0.01 |
| `ssb_calculator(amount, hold_years)` | Singapore Savings Bonds calculator | $0.01 |
| `reit_analysis(reit_name)` | REIT analyzer (yield, leverage, sector) | $0.015 |
| `savings_rates()` | Best savings account rate comparison | $0.01 |

### Other Tools
| Method | Description | Price |
|--------|-------------|-------|
| `coe_prices()` | Latest COE premiums (Cat A–E) | $0.01 |
| `car_loan(...)` | Car loan + PARF rebate calculator | $0.01 |
| `school_nearby(postal_code, level)` | Nearby schools + PSLE cutoffs | $0.01 |
| `financial_health_score(...)` | Financial health score + tips | $0.01 |
| `forex_convert(amount, from, to)` | Currency conversion (SGD base) | $0.005 |
| `business_lookup(uen)` | UEN/ACRA business lookup | $0.02 |
| `benefits_check(age)` | CHAS, Pioneer/Generation, Medisave | $0.01 |
| `utilities_estimate(property_type)` | Electricity + water estimate | $0.005 |
| `goal_plan(goal_name, target, monthly_savings, years)` | Savings goal planner | $0.01 |

### Free Endpoints
| Method | Description |
|--------|-------------|
| `health()` | API health + version info |
| `holidays(year)` | Singapore public holidays |
| `merchant_clean(raw_description)` | Normalize merchant name |
| `batch_clean(descriptions)` | Batch clean (≤20 free, 21–100 = $0.005) |

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `WALLET_SEED` | Wallet private key (hex). Get at https://keys.coinbase.com |
| `X402_API_KEY` | Optional API key override |
| `X402_BASE_URL` | Override API base URL |

---

## For AI Agents

This client auto-discovers the best available endpoint on init. For agent workflows:

```python
from x402_financial import X402Financial

client = X402Financial()  # auto-discovers best endpoint

# Salary → tax → investment in one workflow
net = client.salary_net(gross_annual=120000)
tax = client.tax_income(gross_income=120000, basic_income=120000, cpf_contributions=28800)
dca = client.invest_dca(monthly_investment=2000, years=15)
```

The client handles payment authentication automatically. Set `WALLET_SEED` once, use everywhere.

---

## Links

- **API Docs**: https://github.com/nebmil569/x402-financial-data-api
- **Service Manifest**: https://x402-financial-api.life.conway.tech/x402.json
- **PyPI**: https://pypi.org/project/x402-financial
- **x402 Protocol**: https://x402.org