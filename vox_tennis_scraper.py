from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os, time
from dotenv import load_dotenv
from pymongo import MongoClient

# Load from .env or hardcode (replace with your own URI)
# TODO
MONGO_URI = ""
client = MongoClient(MONGO_URI)

# Use a dedicated collection for tennis
db = client["arbitrage_db"]
collection = db["tennis_odds_vox"]

load_dotenv()

USERNAME = os.getenv("BET_USERNAME")
PASSWORD = os.getenv("BET_PASSWORD")

def start_browser(headless=False):
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
    return webdriver.Chrome(options=chrome_options)


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


def scrape_odds(driver):
    print("[*] Navigating to the Tennis section...")
    tennis_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//span[@class='spNameLeftSports' and contains(text(), 'Tenis')]"))
    )
    driver.execute_script("arguments[0].click();", tennis_button)
    time.sleep(2)

    print("[*] Scanning for tennis league blocks...")
    league_blocks = WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.CLASS_NAME, "leagueCont"))
    )
    print(f"[+] Found {len(league_blocks)} tennis leagues.")

    extracted_matches = []

    for league_block in league_blocks:
        try:
            league_name = league_block.find_element(By.CLASS_NAME, "lNameText").text.strip()
        except:
            league_name = "Unknown League"

        match_rows = league_block.find_elements(By.CLASS_NAME, "matchRow")
        print(f"    ↪ League '{league_name}': {len(match_rows)} matches found.")

        for i, match in enumerate(match_rows):
            try:
                team_spans = match.find_elements(By.CLASS_NAME, "matchNameHomeAway")
                if len(team_spans) != 2:
                    print(f"[-] Match #{i} skipped: bad team names")
                    continue
                home = team_spans[0].text.strip()
                away = team_spans[1].text.strip()

                odds_container = match.find_element(By.CLASS_NAME, "ovDiteOddsCont")
                odds = odds_container.find_elements(By.CLASS_NAME, "odd")

                if len(odds) < 2:
                    print(f"[-] Match #{i} skipped: not enough odds")
                    continue

                odd_1 = odds[0].text.strip()
                odd_2 = odds[1].text.strip()

                print(f"[+] {home} vs {away} ({league_name}) => 1: {odd_1}, 2: {odd_2}")
                extracted_matches.append({
                    "home": home,
                    "away": away,
                    "league": league_name,
                    "sport": "tennis",
                    "odds": {
                        "1": odd_1,
                        "2": odd_2
                    }
                })

            except Exception as e:
                print(f"[-] Match #{i} failed: {e}")

    # Save to MongoDB
    for match in extracted_matches:
        collection.insert_one(match)
    print(f"[+] Stored {len(extracted_matches)} tennis matches in MongoDB.")

    return extracted_matches


if __name__ == "__main__":
    driver = start_browser()
    try:
        collection.delete_many({})
        print("[*] Cleared old tennis odds from MongoDB.")

        login(driver)
        scrape_odds(driver)
        input("\nPress Enter to close the browser...")
    finally:
        driver.quit()
