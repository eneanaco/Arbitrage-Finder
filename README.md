# ⚽📊 Betting Arbitrage Scanner

This project is an automated web scraper and arbitrage detector that collects real-time betting odds from multiple sportsbooks and identifies profitable arbitrage opportunities. It currently supports football matches and scans across markets like:

- 1X2 (Match Winner)
- BTTS (Both Teams to Score)
- Over/Under Goals
- Double Chance

Odds are stored in MongoDB for fast querying and comparison, and arbitrage alerts are sent via email.

---

## 📦 Features

- 🔍 Scrapes football odds from **vox365** and **albbet.org**
- 📥 Stores all data in MongoDB using a unified structure
- ⚖️ Compares odds using fuzzy matching to handle name differences
- 💰 Detects arbitrage opportunities across all supported markets

---

## 🛠️ Tech Stack

- **Python 3.10+**
- **Selenium** for web scraping
- **pymongo** for database operations
- **fuzzywuzzy** for team/league name matching
- **smtplib** for email alerts
- **MongoDB** for storing structured odds

---

## 🚀 How to Run
```bash
1. Install dependencies:

pip install -r requirements.txt

2. Set up MongoDB

Add the connection string (assign the connection String to the MONGO_URI variable) under the 'TODO' comments on every python module

3. Set up Environment Variables for Email:

export EMAIL_USER='your_email@gmail.com'
export EMAIL_PASS='your_app_password'

4. Run the following scrapers to scrape for football odds:

python vox365_scraper.py
python albbet_scraper.py

5. Run the following module to scan the collected odds for arbitrage opportunities:

python arbitrage_scanner.py
```

📌 **TO DO**

- Add scrapers for other betting websites

- Expand to basketball/tennis

- Add unit tests
