# Option Valuation Stream

A terminal-based application to periodically fetch **calls and puts** prices using the Black–Scholes model, powered by:

- [yfinance](https://pypi.org/project/yfinance/) for (delayed) market quotes
- [dateparser](https://pypi.org/project/dateparser/) for flexible date parsing
- `curses` for a terminal UI

## Features

- Supports both **call** and **put** options
- Pulls live (delayed) price data from Yahoo Finance
- Calculates theoretical values with **Black–Scholes**
- Displays in a continuously updating curses interface
- Displays option valuations (with profit) in a curses-based interface.
    
- CSV Format (7 columns):
      - ticker,expiration_date,option_type,strike,price_move,purchase_price,contracts
      
- The live underlying price is always fetched via yfinance.
- If the CSV’s price_move is nonzero, that value is added to the live price to simulate
    a new underlying price (applied_price). Otherwise, the live price is used as-is.
    
- Profit is computed as:
    - profit = total_val - (purchase_price * SHARES_PER_CONTRACT * contracts)
    where total_val = (BS option value per share * SHARES_PER_CONTRACT * contracts).
    
- In live mode, the risk-free rate and implied volatility are fetched live via yfinance.
    

## Installation

1. Clone this repo or download the files.
2. Install the dependencies:

   ```bash
   pip install -r requirements.txt