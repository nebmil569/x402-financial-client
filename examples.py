"""
x402 Financial API — Usage Examples
===================================
Run with: python examples.py
Requires: WALLET_SEED env var (get at https://keys.coinbase.com)
"""

import os
import json

# Import the client
from x402_financial import X402Financial, X402PaymentError


def main():
    # Initialize — uses WALLET_SEED env var
    wallet = os.environ.get("WALLET_SEED")
    if not wallet:
        print("ERROR: Set WALLET_SEED env var first")
        print("  export WALLET_SEED='0x...'")
        return
    
    client = X402Financial(wallet_seed=wallet)
    
    print("=" * 60)
    print("x402 Financial API — Python Client Demo")
    print("=" * 60)
    
    # 1. Check API health
    print("\n[1] API Health")
    health = client.health()
    print(f"  Version: {health.get('version')}")
    print(f"  Prices: {len(client.endpoints)} paid endpoints")
    
    # 2. Salary net calculation (Singapore take-home)
    print("\n[2] Singapore Take-Home Salary")
    print("  $80,000 annual gross salary:")
    try:
        result = client.salary_net(gross_annual=80000)
        print(f"  Gross monthly:    ${result.get('gross_monthly', 0):,.2f}")
        print(f"  CPF (employee):  ${result.get('cpf_employee', 0):,.2f}")
        print(f"  Income tax:       ${result.get('income_tax', 0):,.2f}")
        print(f"  SDL:              ${result.get('sdl', 0):,.2f}")
        print(f"  Net monthly:      ${result.get('net_monthly', 0):,.2f}")
        print(f"  Net annual:       ${result.get('net_annual', 0):,.2f}")
        print(f"  Effective rate:   {result.get('effective_rate_pct', 0):.1f}%")
    except X402PaymentError as e:
        print(f"  Payment required: {e}")
        print(f"  Amount: {e.required_amount} USDC on {e.network}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # 3. SGX stock lookup
    print("\n[3] SGX Stock Profile — DBS")
    try:
        result = client.sgx_stock("DBS")
        print(f"  Price:       ${result.get('price', 'N/A')}")
        print(f"  PE ratio:    {result.get('pe_ratio', 'N/A')}")
        print(f"  Dividend:    {result.get('dividend', {}).get('annual_dividend_per_share', 'N/A')}/share")
        print(f"  Yield:       {result.get('dividend', {}).get('dividend_yield_pct', 'N/A')}%")
        print(f"  Market cap:  ${result.get('market_cap', 'N/A')}")
    except X402PaymentError as e:
        print(f"  Payment required: {e}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # 4. SGX dividend screener
    print("\n[4] SGX Dividend Screener (min 4% yield)")
    try:
        result = client.sgx_screen(min_dividend_yield=4.0)
        stocks = result.get('stocks', [])[:5]
        print(f"  Found {len(result.get('stocks', []))} stocks with ≥4% yield")
        for s in stocks:
            print(f"  {s.get('symbol')}: {s.get('dividend_yield_pct')}% yield, ${s.get('price')}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # 5. CPF calculator
    print("\n[5] CPF Retirement Projection (age 35, $5k salary)")
    try:
        result = client.cpf_calculator(age=35, basic_salary=5000)
        at_55 = result.get('at_55', {})
        print(f"  At 55: OA=${at_55.get('oa_sgd', 0):,.0f} | SA=${at_55.get('sa_sgd', 0):,.0f} | RA=${at_55.get('ra_sgd', 0):,.0f}")
        print(f"  Total: ${at_55.get('total_sgd', 0):,.0f}")
        print(f"  Retirement tier: {result.get('retirement_tier', 'N/A')}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # 6. BTO affordability
    print("\n[6] BTO Affordability ($90k household income, 4-room)")
    try:
        result = client.bto_affordability(annual_household_income=90000, flat_type="4-room")
        print(f"  Verdict: {result.get('verdict', 'N/A')}")
        print(f"  Monthly mortgage: ${result.get('monthly_mortgage', 0):,.2f}")
        print(f"  Grants eligible: ${result.get('total_grants', 0):,.0f}")
        print(f"  Cash required: ${result.get('cash_overlay', 0):,.0f}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # 7. COE prices
    print("\n[7] Latest Singapore COE Prices")
    try:
        result = client.coe_prices()
        cats = result.get('all_categories', {})
        for cat, data in cats.items():
            print(f"  Cat {cat}: ${data.get('premium', 'N/A')} ({data.get('trend', 'N/A')})")
    except Exception as e:
        print(f"  Error: {e}")
    
    print("\n" + "=" * 60)
    print("Install: pip install x402-financial")
    print("Docs: https://github.com/nebmil569/x402-financial-data-api")
    print("=" * 60)


if __name__ == "__main__":
    main()
