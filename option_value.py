#!/usr/bin/env python3
import curses
import time
import csv
import math
from math import log, sqrt, exp
from statistics import NormalDist
import argparse
import dateparser
from datetime import datetime
import yfinance as yf

###############################################################################
# Default fallback parameters
###############################################################################
R_DEFAULT = 0.05     # fallback risk-free rate
SIGMA_DEFAULT = 0.25 # fallback implied volatility
SHARES_PER_CONTRACT = 100  # constant: each option contract covers 100 shares

###############################################################################
# Black–Scholes formulas for calls and puts
###############################################################################
def call_value(S, K, r, sigma, T):
    """Returns the Black–Scholes call option value."""
    def phi(x):
        return NormalDist(mu=0, sigma=1).cdf(x)
    if T <= 0:
        return max(0, S - K)
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    return S * phi(d1) - K * exp(-r * T) * phi(d2)

def put_value(S, K, r, sigma, T):
    """Returns the Black–Scholes put option value."""
    def phi(x):
        return NormalDist(mu=0, sigma=1).cdf(x)
    if T <= 0:
        return max(0, K - S)
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    return K * exp(-r * T) * phi(-d2) - S * phi(-d1)

###############################################################################
# Retrieve risk-free rate from Yahoo Finance (^IRX)
###############################################################################
def get_risk_free_rate():
    """
    Fetch the 13-week T-bill yield from Yahoo Finance (^IRX).
    The value is typically expressed as a percent; divide by 100.
    """
    try:
        ticker = yf.Ticker("^IRX")
        info = ticker.info
        r_percent = info.get("regularMarketPrice", None)
        if r_percent is not None:
            return r_percent / 100.0
    except Exception:
        pass
    return R_DEFAULT

###############################################################################
# Retrieve implied volatility from the option chain via yfinance
###############################################################################
def get_implied_vol(symbol, exp_str, option_type, target_strike):
    """
    Fetches the option chain for the specified expiration (exp_str, format "YYYY-MM-DD")
    for the given symbol and option_type ("call" or "put"). It then selects the option
    with the strike closest to target_strike and returns its implied volatility.
    Falls back to SIGMA_DEFAULT if no data is available.
    """
    try:
        ticker = yf.Ticker(symbol)
        if exp_str not in ticker.options:
            return SIGMA_DEFAULT
        chain = ticker.option_chain(exp_str)
        df = chain.calls if option_type == "call" else chain.puts
        if df.empty:
            return SIGMA_DEFAULT
        df["diff"] = abs(df["strike"] - target_strike)
        best_row = df.loc[df["diff"].idxmin()]
        sigma_live = best_row.get("impliedVolatility", SIGMA_DEFAULT)
        if sigma_live is None:
            return SIGMA_DEFAULT
        return sigma_live
    except Exception:
        return SIGMA_DEFAULT

###############################################################################
# Retrieve live underlying price using yfinance
###############################################################################
def get_live_price(symbol):
    """
    Attempts to fetch the current price for the given symbol using yfinance.
    Tries fast_info first, then ticker.info, and finally history if needed.
    Returns None if no price is available.
    """
    try:
        ticker = yf.Ticker(symbol)
        if hasattr(ticker, 'fast_info'):
            price = ticker.fast_info.get('lastPrice', None)
            if price is not None:
                return price
        info = ticker.info
        price = info.get("regularMarketPrice", None)
        if price is not None:
            return price
    except Exception:
        pass
    try:
        data = ticker.history(period="1d", interval="1m")
        if not data.empty:
            return data["Close"].iloc[-1]
    except Exception:
        return None
    return None

###############################################################################
# Main curses streaming function (live mode for underlying price)
###############################################################################
def stream_valuation(stdscr, csv_file, refresh_interval=15):
    """
    Displays option valuations (with profit) in a curses-based interface.
    
    CSV Format (7 columns):
      ticker,expiration_date,option_type,strike,price_move,purchase_price,contracts
      
    The live underlying price is always fetched via yfinance.
    If the CSV’s price_move is nonzero, that value is added to the live price to simulate
    a new underlying price (applied_price). Otherwise, the live price is used as-is.
    
    Profit is computed as:
      profit = total_val - (purchase_price * SHARES_PER_CONTRACT * contracts)
    where total_val = (BS option value per share * SHARES_PER_CONTRACT * contracts).
    
    Additionally, in live mode, the risk-free rate and implied volatility are fetched live via yfinance.
    
    :param stdscr: curses screen.
    :param csv_file: Path to CSV file with option positions.
    :param refresh_interval: Seconds between data refreshes.
    """
    curses.curs_set(0)  # Hide the cursor

    # Retrieve live risk-free rate from ^IRX.
    live_r = get_risk_free_rate()

    while True:
        stdscr.clear()

        #Read positions from CSV
        positions = []
        unique_tickers = set()
        with open(csv_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                # Skip empty or commented lines
                if not row or row[0].startswith('#'):
                    continue
                if len(row) < 7:
                    continue  # Skip malformed rows
                ticker = row[0].strip()
                expiration_date = row[1].strip()
                option_type = row[2].strip().lower()
                try:
                    strike = float(row[3].strip())
                    move_str = row[4].strip()  # simulated price move
                    purchase_price = float(row[5].strip())
                    contracts = int(row[6].strip())
                except ValueError:
                    continue
                positions.append({
                    'ticker': ticker,
                    'expiration_date': expiration_date,
                    'option_type': option_type,
                    'strike': strike,
                    'move_str': move_str,
                    'purchase_price': purchase_price,
                    'contracts': contracts
                })
                unique_tickers.add(ticker)

        # Fetch live underlying prices for each ticker
        ticker_data = {}
        for tck in unique_tickers:
            tck_stripped = tck.strip()
            price = get_live_price(tck_stripped)
            ticker_data[tck_stripped] = price

        # Print header with fixed column widths (including PROFIT)
        header_line = (
            f"{'TICKER':<6} | "
            f"{'TYPE':<4} | "
            f"{'EXPIRATION':<11} | "
            f"{'STRIKE':<8} | "
            f"{'CUR_PRICE':<9} | "
            f"{'MOVE':<6} | "
            f"{'APPLIED_PRICE':<12} | "
            f"{'TIME_TO_EXP':<11} | "
            f"{'BS_OPT_VAL/SH':<12} | "
            f"{'CONTRACTS':<8} | "
            f"{'TOTAL_VAL':<10} | "
            f"{'PROFIT':<10}"
        )
        stdscr.addstr(0, 0, f"=== Option Valuation Stream (LIVE MODE) ===")
        stdscr.addstr(1, 0, f"Last Refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        stdscr.addstr(2, 0, f"Risk-free rate (^IRX): {live_r*100:.2f}%")
        stdscr.addstr(3, 0, f"Data refreshes every {refresh_interval} seconds. (Press Ctrl+C to quit)")
        stdscr.addstr(5, 0, header_line)

        # Process each position and print a data row
        row_start = 6
        for i, pos in enumerate(positions):
            ticker = pos['ticker']
            option_type = pos['option_type']
            expiration_date = pos['expiration_date']
            strike = pos['strike']
            move_str = pos['move_str']
            purchase_price = pos['purchase_price']
            contracts = pos['contracts']

            r_used = live_r  # live risk-free rate
            sigma_used = SIGMA_DEFAULT  # fallback; we'll try to fetch live below

            # Parse expiration date and compute time to expiration (in years)
            parsed_exp = dateparser.parse(expiration_date)
            if not parsed_exp:
                line = f"{ticker:<6} | {option_type:<4} | {expiration_date:<11} | Invalid date"
                stdscr.addstr(row_start + i, 0, line)
                continue
            T = (parsed_exp - datetime.now()).days / 365.0

            # Retrieve the live underlying price
            live_price = ticker_data.get(ticker.strip(), None)
            if live_price is None:
                line = f"{ticker:<6} | {option_type:<4} | {parsed_exp.strftime('%d-%b-%Y'):<11} | (No data)"
                stdscr.addstr(row_start + i, 0, line)
                continue

            # Determine applied price: if move_str is nonzero, add it; else use live price.
            try:
                move_val = float(move_str.replace('+', ''))
            except ValueError:
                move_val = 0.0
            applied_price = live_price + move_val

            # In live mode, attempt to fetch implied volatility from the option chain.
            exp_str = parsed_exp.strftime("%Y-%m-%d")
            sigma_used = get_implied_vol(ticker.strip(), exp_str, option_type, strike)

            # Calculate BS option value per share using applied price.
            if option_type == 'call':
                bs_val_per_share = call_value(applied_price, strike, r_used, sigma_used, T)
            elif option_type == 'put':
                bs_val_per_share = put_value(applied_price, strike, r_used, sigma_used, T)
            else:
                line = f"{ticker:<6} | Unknown type: {option_type}"
                stdscr.addstr(row_start + i, 0, line)
                continue

            total_val = bs_val_per_share * SHARES_PER_CONTRACT * contracts
            purchase_cost = purchase_price * SHARES_PER_CONTRACT * contracts
            profit = total_val - purchase_cost

            data_line = (
                f"{ticker.strip():<6} | "                        
                f"{option_type:<4} | "                           
                f"{parsed_exp.strftime('%d-%b-%Y'):<11} | "     
                f"{strike:<8.2f} | "                            
                f"{live_price:<9.2f} | "                       
                f"{move_val:+6.2f} | "                              
                f"{applied_price:<12.2f} | "                       
                f"{T:<11.3f} | "                              
                f"{bs_val_per_share:<12.2f} | "                
                f"{contracts:<8} | "                               
                f"{total_val:<10.2f} | "                            
                f"{profit:<10.2f}"                                  
            )
            stdscr.addstr(row_start + i, 0, data_line)

        stdscr.refresh()
        time.sleep(refresh_interval)

# Main function
def main():
    parser = argparse.ArgumentParser(
        description="Stream option valuations with profit calculation in live mode using yfinance.",
        epilog=(
            "Example:\n"
            "  python3 option_value.py --csv positions.csv --refresh 15\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--csv", default="positions.csv",
                        help="Path to CSV file listing option positions (7 columns).")
    parser.add_argument("--refresh", type=int, default=15,
                        help="Refresh interval in seconds (default=15).")
    args = parser.parse_args()

    try:
        curses.wrapper(stream_valuation, csv_file=args.csv, refresh_interval=args.refresh)
    except KeyboardInterrupt:
        print("\n[Exiting gracefully on Ctrl+C]")

if __name__ == "__main__":
    main()