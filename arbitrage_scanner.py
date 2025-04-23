import smtplib
import ssl
from pymongo import MongoClient
from email.message import EmailMessage
from dotenv import load_dotenv
from rapidfuzz import fuzz
import os

# Load environment variables
load_dotenv()
EMAIL_USER = os.getenv("GMAIL_USER")
EMAIL_PASS = os.getenv("GMAIL_PASS")

# MongoDB setup
# TODO : Add MongoDB Connection String
client = MongoClient("")
db = client["arbitrage_db"]
albbet_collection = db["football_odds_albbet"]
vox_collection = db["football_odds_vox"]

# Settings
FUZZY_MATCH_THRESHOLD = 70
ARBITRAGE_RESULTS = []
STAKE = 100  # Base stake for bet sizing

# Market groups
MARKETS = [
    ("1", "1"),
    ("X", "X"),
    ("2", "2"),
    ("DC_1X", "DC_1X"),
    ("DC_12", "DC_12"),
    ("DC_X2", "DC_X2"),
    ("BTTS_Yes", "BTTS_Yes"),
    ("BTTS_No", "BTTS_No"),
    ("Over_2.5", "Over_2.5"),
    ("Under_2.5", "Under_2.5"),
]

TWO_WAY_COMBOS = [
    ("DC_1X", "2"),
    ("DC_12", "X"),
    ("DC_X2", "1"),
    ("BTTS_Yes", "BTTS_No"),
    ("Over_2.5", "Under_2.5")
]

def debug_log(msg):
    print(f"[DEBUG] {msg}")

def is_potential_match(match1, match2, threshold=FUZZY_MATCH_THRESHOLD):
    def clean(val):
        return val.strip().lower()

    home1, away1, league1 = clean(match1["home"]), clean(match1["away"]), clean(match1["league"])
    home2, away2, league2 = clean(match2["home"]), clean(match2["away"]), clean(match2["league"])

    home_sim = fuzz.token_set_ratio(home1, home2)
    away_sim = fuzz.token_set_ratio(away1, away2)
    league_sim = fuzz.token_set_ratio(league1, league2)

    debug_log(f"Checking: {match1['home']} vs {match1['away']} <=> {match2['home']} vs {match2['away']}")
    debug_log(f"Similarities - Home: {home_sim}, Away: {away_sim}, League: {league_sim}")

    return min(home_sim, away_sim, league_sim) >= threshold

def find_best_odds(alb_odds, vox_odds, label=""):
    best = {}
    for key, _ in MARKETS:
        try:
            alb_odd = float(alb_odds.get(key, 0))
            vox_odd = float(vox_odds.get(key, 0))
            if alb_odd > 1 or vox_odd > 1:
                best_odd = max(alb_odd, vox_odd)
                best[key] = best_odd
        except Exception as e:
            debug_log(f"Error parsing odds for {key}: {e}")
    debug_log(f"Best odds for {label}: {best}")
    return best

def compute_arbitrage(odds_dict, label, combo_keys):
    try:
        combo_odds = {k: odds_dict[k] for k in combo_keys if k in odds_dict and odds_dict[k] > 1}
        if len(combo_odds) != len(combo_keys):
            return None  # Incomplete combo
        total_inverse = sum(1 / v for v in combo_odds.values())
        if total_inverse < 1:
            profit_percent = round((1 - total_inverse) * 100, 2)
            stake_split = {
                k: round((1 / v) / total_inverse * STAKE, 2)
                for k, v in combo_odds.items()
            }
            return {
                "match": label,
                "market": "+".join(combo_keys),
                "profit_percent": profit_percent,
                "odds": combo_odds,
                "stake_split": stake_split
            }
    except Exception as e:
        debug_log(f"Error computing arbitrage: {e}")
    return None

def find_arbitrage_bets():
    matches_checked = 0
    matches_matched = 0

    for alb_doc in albbet_collection.find():
        for vox_doc in vox_collection.find():
            matches_checked += 1

            if is_potential_match(alb_doc, vox_doc):
                matches_matched += 1
                label = f"{alb_doc['home']} vs {alb_doc['away']} ({alb_doc['league']})"
                debug_log(f"✅ Match FOUND: {label}")

                best_odds = find_best_odds(alb_doc["odds"], vox_doc["odds"], label=label)

                # Check 3-way arbitrage: 1X2
                arb = compute_arbitrage(best_odds, label, ["1", "X", "2"])
                if arb:
                    debug_log(f"🎯 Arbitrage (1X2) found for {label}")
                    ARBITRAGE_RESULTS.append(arb)

                # Check 3-way arbitrage: Double Chance
                arb = compute_arbitrage(best_odds, label, ["DC_1X", "DC_12", "DC_X2"])
                if arb:
                    debug_log(f"🎯 Arbitrage (DC_1X+DC_12+DC_X2) found for {label}")
                    ARBITRAGE_RESULTS.append(arb)

                # Check all 2-way combos
                for k1, k2 in TWO_WAY_COMBOS:
                    arb = compute_arbitrage(best_odds, label, [k1, k2])
                    if arb:
                        debug_log(f"🎯 Arbitrage ({k1} + {k2}) found for {label}")
                        ARBITRAGE_RESULTS.append(arb)

    debug_log(f"Matches checked: {matches_checked}, Matches matched: {matches_matched}")

def send_email_report():
    if not ARBITRAGE_RESULTS:
        print("❌ No arbitrage opportunities found.")
        return

    msg = EmailMessage()
    msg["Subject"] = "⚽ Arbitrage Opportunities Report"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_USER

    body = "🔥 Arbitrage Bets Found:\n\n"
    for arb in ARBITRAGE_RESULTS:
        body += f"Match: {arb['match']}\n"
        body += f"Market: {arb['market']}\n"
        body += f"Profit: {arb['profit_percent']}%\n"
        body += "Best Odds:\n"
        for market, odd in arb["odds"].items():
            body += f"  {market}: {odd}\n"
        body += "Suggested Stakes (for 100€):\n"
        for market, stake in arb["stake_split"].items():
            body += f"  {market}: {stake}€\n"
        body += "-" * 40 + "\n\n"

    msg.set_content(body)

    # 💬 Print the email to console
    print("📧 Email content:\n")
    print(body)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        print("✅ Email sent successfully.")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")


# === RUN MODULE ===
debug_log("Starting arbitrage scan...")
find_arbitrage_bets()
send_email_report()
debug_log("Finished.")
