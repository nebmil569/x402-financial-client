# x402 Financial — Python Client

A Python client for the **[x402 Financial Data API](https://x402-financial-api.life.conway.tech)** — Singapore's most comprehensive financial data API powered by the x402 payment protocol (Coinbase).

Pay with USDC on Base (eip155:8453) per request. No API keys. No accounts.

## Features

- **61 financial endpoints** covering Singapore banking, taxes, CPF, SGX stocks, property, investments, and more
- **Automatic x402 v2 payment** — handles payment signing and retry automatically
- **Bank statement parsing** — DBS, OCBC, UOB, Citi, Maybank, StanChart, Trust, BOC
- **SGX stock data** — real-time prices, dividends, fundamentals (PE, EPS, market cap)
- **Singapore-specific** — CPF calculators, IRAS tax, HDB/BTO, COE, SRS, FIRE
- **DCA comparator** — IWLU vs CPF OA vs Singapore Savings Bonds

## Quick Start

```bash
pip install x402-financial
```

```python
from x402_financial import X402Financial

client = X402Financial(wallet_seed="0x...")  # or set WALLET_SEED env var

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

For automatic x402 payment support:
```bash
pip install x402-financial[coinbase]
```

Or set the `WALLET_SEED` environment variable:
```bash
export WALLET_SEED="0x..."
```

## API Coverage

| Category | Endpoints |
|----------|-----------|
| Bank Parsing | /parse/{bank}, /extract/transactions |
| SGX Stocks | /sgx/stock, /sgx/price, /sgx/dividend, /sgx/portfolio, /sgx/screen, /sgx/search |
| Salary & Tax | /salary/net, /salary/benchmark, /tax/income, /tax/corporate |
| CPF & Retirement | /cpf/calculator, /cpf/contributions, /cpf/topup, /srs/calculator, /fire |
| Investments | /invest/dca, /invest/grow, /forex/convert, /ssb/rates, /ssb/calculator |
| Property | /bto/affordability, /hdb/resale, /property/tax, /property/absd, /mortgage/compare, /refinance |
| Reports | /summary, /report/spending, /report/cash-flow, /report/subscriptions |
| Utilities | /cost/estimate, /electricity/compare, /coe, /holidays/singapore |

## How x402 Payments Work

1. You make a request without payment → API returns HTTP 402 with payment requirements
2. The `X402Financial` client extracts the payment spec (amount, network, asset)
3. It signs the payment with your wallet seed using Coinbase's SDK
4. It retries the request with the signed payment header
5. You get the data — the API receives automatic USDC payment

No need to manage API keys, subscriptions, or billing cycles.

## Links

- **API**: https://x402-financial-api.life.conway.tech
- **x402 Protocol**: https://x402.org
- **GitHub**: https://github.com/nebmil569/x402-financial-data-api
- **Wallet**: https://keys.coinbase.com

## License

MIT
