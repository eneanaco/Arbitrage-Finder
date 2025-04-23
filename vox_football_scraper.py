import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os
from pymongo import MongoClient

# Replace this with your actual connection string (keep it secure!)
# TODO
MONGO_URI = ""

# Initialize MongoDB client and collection
client = MongoClient(MONGO_URI)
db = client["arbitrage_db"]         # or any name you prefer
collection = db["football_odds_vox"]       # will auto-create if it doesn't exist


load_dotenv()

USERNAME = os.getenv("BET_USERNAME")
PASSWORD = os.getenv("BET_PASSWORD")


def start_browser(headless=False):
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(options=chrome_options)
    return driver


def login(driver):
    print("[*] Opening login page...")
    driver.get("https://vox365.co/client.aspx")

    print("[*] Waiting for username field...")
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "username"))
    )

    print("[*] Entering credentials...")
    driver.find_element(By.ID, "username").send_keys(USERNAME)
    driver.find_element(By.ID, "password").send_keys(PASSWORD)
    driver.find_element(By.ID, "submit").click()

    time.sleep(3)
    print("[+] Login attempted.")


def click_back_button(driver):
    try:
        print("[*] Clicking back button to return to match list...")
        back_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "backToWhereYouWhere"))
        )
        back_btn.click()

        # Wait for match rows to reappear
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CLASS_NAME, "matchRow"))
        )
        print("[+] Successfully returned to match list.")
    except Exception as e:
        print("[-] Failed to click back button:", e)


def scrape_odds(driver):
    print("[*] Scanning for leagues and matches...")

    extracted_matches = []
    seen_codes = set()

    # Build flat list of matches (league_name, match_row)
    def build_match_list():
        flat_matches = []
        league_blocks = driver.find_elements(By.CLASS_NAME, "leagueCont")
        print(f"[+] Found {len(league_blocks)} league sections.")
        for block in league_blocks:
            try:
                league_name = block.find_element(By.CLASS_NAME, "lNameText").text.strip()
            except:
                league_name = "Unknown League"

            match_rows = block.find_elements(By.CLASS_NAME, "matchRow")
            print(f"    ↪ League '{league_name}': {len(match_rows)} matches found.")

            for match in match_rows:
                flat_matches.append((league_name, match))
        return flat_matches

    all_matches = build_match_list()
    index = 0

    while index < len(all_matches):
        league_name, match_element = all_matches[index]
        index += 1

        try:
            match_code = match_element.find_element(By.CLASS_NAME, "kodi").text.strip()
        except:
            print(f"[-] Match #{index} skipped: no match code")
            continue

        if match_code in seen_codes:
            continue
        seen_codes.add(match_code)

        try:
            team_spans = match_element.find_elements(By.CLASS_NAME, "matchNameHomeAway")
            if len(team_spans) != 2:
                print(f"[-] Match #{index} skipped: bad team span")
                continue
            home = team_spans[0].text.strip()
            away = team_spans[1].text.strip()
            if home.startswith("(S)") or away.startswith("(S)"):
                continue
        except:
            continue

        try:
            clickable = team_spans[0].find_element(By.XPATH, "..")
            driver.execute_script("arguments[0].click();", clickable)
            print(f"[+] Clicked into {home} vs {away} ({league_name})")
        except:
            print(f"[-] Failed to click {home} vs {away}")
            continue

        # Wait for 1X2 odds
        start_time = time.time()
        for _ in range(3):
            odds_elems = driver.find_elements(By.CLASS_NAME, "oddVal")
            if len(odds_elems) >= 3:
                o1, ox, o2 = odds_elems[:3]
                if all(el.text.strip() for el in [o1, ox, o2]):
                    break
            time.sleep(0.2)
        elapsed = time.time() - start_time
        print(f"[~] Waited {round(elapsed, 2)}s for odds")

        odds_texts = [el.text.strip() for el in odds_elems if el.text.strip()]
        odds_1, odds_x, odds_2 = odds_texts[:3] if len(odds_texts) >= 3 else (None, None, None)

        btts_yes = btts_no = dc_1x = dc_12 = dc_x2 = ou_over = ou_under = None

        rub_blocks = driver.find_elements(By.CLASS_NAME, "rubContainer")
        for block in rub_blocks:
            try:
                title = block.find_element(By.CLASS_NAME, "rubNameDiteRub").text.strip().lower()

                if "gol" in title and "jgol" in block.text.lower():
                    odds = block.find_elements(By.CLASS_NAME, "oddCont")
                    for o in odds:
                        label = o.find_element(By.CLASS_NAME, "oddDesc").text.strip()
                        val = o.find_element(By.CLASS_NAME, "oddVal").text.strip()
                        if label == "Gol":
                            btts_yes = val
                        elif label == "JGol":
                            btts_no = val

                if "dopio shans" == title:
                    odds = block.find_elements(By.CLASS_NAME, "oddCont")
                    for o in odds:
                        label = o.find_element(By.CLASS_NAME, "oddDesc").text.strip()
                        val = o.find_element(By.CLASS_NAME, "oddVal").text.strip()
                        if label == "1X":
                            dc_1x = val
                        elif label == "12":
                            dc_12 = val
                        elif label == "X2":
                            dc_x2 = val

                if "shuma e golave perfundimtare" == title:
                    odds = block.find_elements(By.CLASS_NAME, "oddCont")
                    for o in odds:
                        label = o.find_element(By.CLASS_NAME, "oddDesc").text.strip()
                        val = o.find_element(By.CLASS_NAME, "oddVal").text.strip()
                        if label == "3+":
                            ou_over = val
                        elif label == "0-2":
                            ou_under = val
            except:
                continue

        extracted_matches.append({
            "home": home,
            "away": away,
            "sport": "football",
            "league": league_name,
            "odds": {
                "1": odds_1,
                "X": odds_x,
                "2": odds_2,
                "BTTS_Yes": btts_yes,
                "BTTS_No": btts_no,
                "DC_1X": dc_1x,
                "DC_12": dc_12,
                "DC_X2": dc_x2,
                "Over_2.5": ou_over,
                "Under_2.5": ou_under
            }
        })

        try:
            back_button = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.CLASS_NAME, "backToWhereYouWhere"))
            )
            driver.execute_script("arguments[0].click();", back_button)
            time.sleep(1)
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, "matchRow"))
            )
            print("[+] Back to match list.")
        except Exception as e:
            print(f"[-] Failed to return to match list: {e}")
            return extracted_matches

        # Rebuild match list from fresh DOM
        all_matches = build_match_list()

    # Save to MongoDB
    for match in extracted_matches:
        collection.insert_one(match)
    print(f"[+] Stored {len(extracted_matches)} matches in MongoDB.")

    return extracted_matches


def find_arbitrage(matches):
    print("\n🔎 Searching for arbitrage opportunities...")
    opportunities = []

    for match in matches:
        try:
            o = match["odds"]
            odds_1 = float(o["1"])
            odds_x = float(o["X"])
            odds_2 = float(o["2"])

            inv_total = (1 / odds_1) + (1 / odds_x) + (1 / odds_2)

            if inv_total < 1:
                profit_percent = (1 - inv_total) * 100
                opportunities.append({
                    "teams": f"{match['home']} vs {match['away']}",
                    "odds": o,
                    "profit": round(profit_percent, 2)
                })

        except Exception as e:
            print(f"[-] Skipped one match (arbitrage calc error): {e}")

    print(f"[+] Found {len(opportunities)} arbitrage opportunities.")
    return opportunities


if __name__ == "__main__":
    driver = start_browser(headless=False)

    try:
        collection.delete_many({})
        print("[*] Cleared old odds from MongoDB.")

        login(driver)
        matches = scrape_odds(driver)

        print("\n🎯 Extracted Matches & Odds:")
        for m in matches:
            print(f"{m['home']} vs {m['away']} => 1: {m['odds']['1']} | X: {m['odds']['X']} | 2: {m['odds']['2']}")

        arbs = find_arbitrage(matches)

        for arb in arbs:
            print(f"\n🔥 {arb['teams']}")
            print(f"    Odds: 1 = {arb['odds']['1']} | X = {arb['odds']['X']} | 2 = {arb['odds']['2']}")
            print(f"    Profit: {arb['profit']}%")

    finally:
        driver.quit()
