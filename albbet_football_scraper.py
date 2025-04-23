import time
import warnings
import undetected_chromedriver as uc

from datetime import datetime

from pymongo import MongoClient
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException

warnings.filterwarnings("ignore", category=ResourceWarning)
# Replace this with your actual connection string (keep it secure!)
# TODO
MONGO_URI = ""

class AlbbetFootballScraper:
    def __init__(self, driver: webdriver.Chrome):

        self.mongo_client = MongoClient(MONGO_URI)
        self.db = self.mongo_client["arbitrage_db"]
        self.odds_collection = self.db["football_odds_albbet"]

        self.odds_collection.delete_many({})
        print("🧹 Cleared football_odds_albbet collection before run.")


        # Reduced the default wait from 10 to 5 seconds for speed
        self.driver = driver
        self.wait = WebDriverWait(driver, 5)
        self.today_str = datetime.today().strftime("%A %d %B")

    def _short_sleep(self, duration=0.3):
        """Minimal sleep to prevent click intercept or stale DOM issues."""
        time.sleep(duration)

    def set_language_to_english(self):
        try:
            print("🌐 Setting language to English...")
            lang_dropdown = self.wait.until(
                EC.element_to_be_clickable((By.CLASS_NAME, "hpf-select"))
            )
            select = Select(lang_dropdown)
            select.select_by_visible_text("English")
            self._short_sleep(0.3)
            print("✅ Language set to English.")
        except TimeoutException:
            print("❌ Language dropdown not found.")
            self.driver.save_screenshot("language_fail.png")
            raise

    def _page_has_leagues_fast(self, timeout=1):
        """
        Quickly checks if the page has 'spo-h1' within 'timeout' seconds.
        If none are found, returns False quickly (saving time).
        """
        short_wait = WebDriverWait(self.driver, timeout)
        try:
            short_wait.until(EC.presence_of_element_located((By.CLASS_NAME, "spo-h1")))
            return True
        except TimeoutException:
            return False

    def _page_has_leagues(self):
        """Slower, full wait approach."""
        try:
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "spo-h1")))
            return True
        except TimeoutException:
            return False

    def _page_has_matches(self):
        try:
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "nde-podHeaderRow")))
            return True
        except TimeoutException:
            return False

    def _safe_click(self, element):
        """
        Safely clicks 'element' using a triple fallback approach:
          1) Normal click
          2) ActionChains click
          3) JavaScript click
        """
        # Scroll the element into view center
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        self._short_sleep(0.2)

        try:
            element.click()
        except (ElementClickInterceptedException, Exception) as e_click:
            print(f"⚠️ Normal click failed: {e_click}. Trying ActionChains...")
            try:
                actions = ActionChains(self.driver)
                actions.move_to_element(element).click().perform()
            except Exception as e_actions:
                print(f"⚠️ ActionChains failed too: {e_actions}. Using JS click...")
                self.driver.execute_script("arguments[0].click();", element)

        self._short_sleep(0.2)

    def iterate_countries(self):
        for i in range(100):
            try:
                countries = self.driver.find_elements(By.CLASS_NAME, "spo-h1")
                if i >= len(countries):
                    print(f"✅ Done after {i} countries.")
                    break

                print(f"📍 Now checking country {i + 1}/{len(countries)}")
                target = countries[i]

                # Use safe_click to handle intercept issues
                self._safe_click(target)
                self._short_sleep(0.2)

                # FAST check for leagues
                if self._page_has_leagues_fast(timeout=1):
                    self.iterate_leagues()
                    self.go_back("country")
                elif self._page_has_matches():
                    print(f"🧠 Looking for matches on: '{self.today_str}'")
                    self.process_matches_for_today()
                    self.go_back("league")
                else:
                    print("⚠️ Unknown page structure after clicking country.")
                    self.driver.save_screenshot(f"unexpected_page_after_country_{i + 1}.png")
                    self.go_back("country")

            except Exception as e:
                print(f"❌ Failed at country {i + 1}: {e}")
                self.driver.save_screenshot(f"fail_country_{i + 1}.png")
                self.go_back("country")
                continue

    def iterate_leagues(self):
        leagues = self.wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "spo-h1")))
        for i in range(len(leagues)):
            leagues = self.driver.find_elements(By.CLASS_NAME, "spo-h1")
            self._short_sleep(0.2)
            self._safe_click(leagues[i])  # use safe_click here too
            self._short_sleep(0.2)

            print(f"🧠 Looking for matches on: '{self.today_str}'")
            self.process_matches_for_today()
            self.go_back("league")

    def process_matches_for_today(self):
        try:
            print(f"🪣 Collecting wrappers for '{self.today_str}'...")
            all_wrappers = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="wrapper"]')
            today_wrappers = []
            current_date = None

            # First pass
            for w in all_wrappers:
                header_els = w.find_elements(By.CLASS_NAME, "nde-podHeaderRow")
                if header_els:
                    raw_header = header_els[0].text.strip()
                    if self.today_str in raw_header:
                        current_date = self.today_str
                    else:
                        current_date = None

                if current_date == self.today_str:
                    match_els = w.find_elements(By.CLASS_NAME, "nde-Market_GameDetail_Rez")
                    if match_els:
                        today_wrappers.append(w)

            if not today_wrappers:
                print(f"📭 No matches found for today: {self.today_str}")
                return

            print(f"✅ Found {len(today_wrappers)} wrapper(s) for today's date: {self.today_str}")

            # Second pass in a while-loop
            match_idx = 0
            while match_idx < len(today_wrappers):
                # Re-fetch all wrappers because DOM might have changed
                all_wrappers = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="wrapper"]')
                temp_today_wrappers = []
                current_date = None

                for w in all_wrappers:
                    header_els = w.find_elements(By.CLASS_NAME, "nde-podHeaderRow")
                    if header_els:
                        raw_header = header_els[0].text.strip()
                        if self.today_str in raw_header:
                            current_date = self.today_str
                        else:
                            current_date = None

                    if current_date == self.today_str:
                        match_els = w.find_elements(By.CLASS_NAME, "nde-Market_GameDetail_Rez")
                        if match_els:
                            temp_today_wrappers.append(w)

                today_wrappers = temp_today_wrappers

                if match_idx >= len(today_wrappers):
                    print("📦 No more matches left to open.")
                    break

                w = today_wrappers[match_idx]
                match_els = w.find_elements(By.CLASS_NAME, "nde-Market_GameDetail_Rez")
                if not match_els:
                    print(f"⚠️ Wrapper {match_idx+1} has no match elements. Skipping.")
                    match_idx += 1
                    continue

                match = match_els[0]
                print(f"⚽ Opening match {match_idx+1}/{len(today_wrappers)} for today: {self.today_str}")

                self._safe_click(match)
                self._short_sleep(0.3)

                self.scrape_match_odds()
                self.go_back("match")

                match_idx += 1

            print("✅ Done opening all matches for today.")

        except Exception as e:
            print(f"❌ process_matches_for_today error: {e}")


    def scrape_match_odds(self):
        print("🔍 Scraping odds...")

        try:
            odds = {
                "teams": {},
                "league": "",
                "1X2": {},
                "DoubleChance": {},
                "OverUnder2_5": {},
                "BTTS": {}
            }

            # 🏷 Extract team names from banner
            try:
                banner_names = self.driver.find_elements(By.CLASS_NAME, "nd-banner-name")
                if len(banner_names) >= 2:
                    home_team = banner_names[0].text.strip()
                    away_team = banner_names[1].text.strip()
                else:
                    home_team, away_team = "Unknown", "Unknown"
                    print("⚠️ Less than 2 team names found in banner.")
                odds["teams"] = {"home": home_team, "away": away_team}
                print(f"🏟️ Match: {home_team} vs {away_team}")
            except Exception as e:
                print(f"⚠️ Could not extract team names: {e}")
                odds["teams"] = {"home": "Unknown", "away": "Unknown"}

            # 🏆 Extract league name from breadcrumb
            try:
                breadcrumb = self.driver.find_element(By.CLASS_NAME, "nd-HeaderNavigation_BreadcrumbLevel2")
                breadcrumb_text = breadcrumb.text.strip()
                league_name = breadcrumb_text.split(" / ")[0] if " / " in breadcrumb_text else breadcrumb_text
                odds["league"] = league_name
                print(f"🏆 League: {league_name}")
            except Exception as e:
                print(f"⚠️ Could not extract league name: {e}")
                odds["league"] = "Unknown"

            # 1X2 odds
            full_time_result_section = self.driver.find_element(
                By.XPATH, "//div[@class='nd-h1' and contains(text(), 'Full Time Result')]/following-sibling::div")
            odds_1x2_elements = full_time_result_section.find_elements(By.CLASS_NAME, "nd-priceColumnOdd")

            if len(odds_1x2_elements) >= 3:
                for el in odds_1x2_elements:
                    label = el.find_element(By.CLASS_NAME, "nd-opp").text.strip()
                    value = el.find_elements(By.TAG_NAME, "span")[1].text.strip()
                    odds["1X2"][label] = value
                print("✅ 1X2 odds:", odds["1X2"])
            else:
                print("⚠️ Less than 3 elements found for 1X2")

            # Double Chance odds (same page)
            try:
                double_chance_section = self.driver.find_element(
                    By.XPATH, "//div[@class='nd-h1' and contains(text(), 'Double Chance')]/following-sibling::div")
                dc_odd_elements = double_chance_section.find_elements(By.CLASS_NAME, "nd-priceColumnOdd")
                for el in dc_odd_elements:
                    label = el.find_element(By.CLASS_NAME, "nd-opp").text.strip()
                    value = el.find_elements(By.TAG_NAME, "span")[1].text.strip()
                    odds["DoubleChance"][label] = value
                print("✅ Double Chance odds:", odds["DoubleChance"])
            except Exception as e:
                print(f"⚠️ Could not parse Double Chance odds: {e}")

            # Navigate to Goals tab → Over/Under 2.5
            try:
                goals_tab = self.driver.find_element(
                    By.XPATH, "//div[contains(@class, 'nd-enhancedTab') and contains(text(), 'Goals')]")
                self._safe_click(goals_tab)
                self._short_sleep(0.3)

                columns = self.driver.find_elements(By.CLASS_NAME, "nd-Col13")
                if len(columns) >= 3:
                    over_col = columns[1].find_elements(By.CLASS_NAME, "nd-priceColumnOdd")
                    under_col = columns[2].find_elements(By.CLASS_NAME, "nd-priceColumnOdd")

                    if len(over_col) >= 2 and len(under_col) >= 2:
                        odds["OverUnder2_5"] = {
                            "Over 2.5": over_col[1].text.strip(),
                            "Under 2.5": under_col[1].text.strip()
                        }
                        print("✅ Over/Under 2.5 odds:", odds["OverUnder2_5"])
                    else:
                        print("⚠️ Not enough odds found in Over/Under columns")
                else:
                    print("⚠️ Could not find sufficient nd-Col13 columns")
            except Exception as e:
                print(f"⚠️ Could not extract Over/Under 2.5 odds: {e}")

            # Navigate to BTTS tab
            try:
                btts_tab = self.driver.find_element(
                    By.XPATH, "//div[contains(@class, 'nd-enhancedTab') and contains(text(), 'Both Teams to Score')]")
                self._safe_click(btts_tab)
                self._short_sleep(0.3)

                btts_rows = self.driver.find_elements(
                    By.XPATH, "//div[@class='nd-h1' and contains(text(), 'Both Teams To Score')]/following-sibling::div")
                for row in btts_rows:
                    all_spans = row.find_elements(By.CLASS_NAME, "nd-priceColumnOdd")
                    if len(all_spans) >= 2:
                        yes = all_spans[0].find_elements(By.TAG_NAME, "span")[1].text.strip()
                        no = all_spans[1].find_elements(By.TAG_NAME, "span")[1].text.strip()
                        odds["BTTS"] = {"Yes": yes, "No": no}
                        print("✅ BTTS odds:", odds["BTTS"])
                        break
            except Exception as e:
                print(f"⚠️ Could not extract BTTS odds: {e}")

            # 💾 Save to MongoDB in flattened structure
            try:
                doc = {
                    "home": odds["teams"]["home"],
                    "away": odds["teams"]["away"],
                    "league": odds["league"],
                    "odds": {
                        "1": odds["1X2"].get("1", ""),
                        "X": odds["1X2"].get("X", ""),
                        "2": odds["1X2"].get("2", ""),
                        "DC_1X": odds["DoubleChance"].get("1X", ""),
                        "DC_12": odds["DoubleChance"].get("12", ""),
                        "DC_X2": odds["DoubleChance"].get("X2", ""),
                        "BTTS_Yes": odds["BTTS"].get("Yes", ""),
                        "BTTS_No": odds["BTTS"].get("No", ""),
                        "Over_2.5": odds["OverUnder2_5"].get("Over 2.5", ""),
                        "Under_2.5": odds["OverUnder2_5"].get("Under 2.5", "")
                    }
                }

                self.odds_collection.insert_one(doc)
                print("💾 Saved match to MongoDB.")
            except Exception as e:
                print(f"❌ Failed to save match to MongoDB: {e}")

            # 🔙 Go back to main match list
            self.go_back("match")
            self.go_back("match")

        except Exception as e:
            print(f"❌ Error while scraping odds: {e}")


    def go_back(self, level):
        back_classes = {
            "match": "nd-HeaderNavigation_BreadcrumbBack",
            "league": "kam-HeaderNavigation_BreadcrumbBack",
            "country": "spo-HeaderNavigation_BreadcrumbBack"
        }
        wait_targets = {
            "match": "nde-podHeaderRow",
            "league": "spo-h1",
            "country": "spo-h1"
        }

        back_class = back_classes.get(level)
        wait_for = wait_targets.get(level)

        if not back_class or not wait_for:
            raise ValueError("Unknown back level: " + level)

        try:
            wait_time = 0.5 if level == "match" else 2
            short_wait = WebDriverWait(self.driver, wait_time)

            print(f"🔙 Locating back button for {level}...")
            back_btn = short_wait.until(EC.presence_of_element_located((By.CLASS_NAME, back_class)))
            print(f"✅ Back button for {level} found, clicking...")

            self.driver.execute_script("arguments[0].scrollIntoView(true);", back_btn)
            self.driver.execute_script("arguments[0].click();", back_btn)
            self._short_sleep(0.2)

            print(f"⏳ Waiting for target element after back ({wait_for})...")
            short_wait.until(EC.presence_of_element_located((By.CLASS_NAME, wait_for)))
            self._short_sleep(0.15)
            print(f"✅ Successfully returned to {level} level.")
        except TimeoutException:
            print(f"❌ Could not navigate back to {level} (Timeout while waiting for next view)")
            self.driver.save_screenshot(f"back_fail_{level}.png")
        except Exception as e:
            print(f"❌ Unexpected error during go_back({level}): {e}")
            self.driver.save_screenshot(f"back_fail_{level}_exception.png")


if __name__ == "__main__":
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = uc.Chrome(options=options, headless=False)

    print("🌍 Navigating to Soccer page initially...")
    driver.get("https://albbet.org/?Key=4_0_0_0_0_0_0_")

    print("🤖 Waiting for CAPTCHA to auto-solve...")
    time.sleep(4)  # Adjust this if you need more or less time for the captcha

    scraper = AlbbetFootballScraper(driver)
    scraper.set_language_to_english()

    print("🔁 Reloading Soccer page after language change...")
    driver.get("https://albbet.org/?Key=4_0_0_0_0_0_0_")
    time.sleep(1)

    # Start scraping
    scraper.iterate_countries()

    driver.quit()
