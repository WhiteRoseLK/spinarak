import chromedriver_autoinstaller, os, uuid, random, time, requests
from datetime import date
from bs4 import BeautifulSoup
from selenium import webdriver
from pyvirtualdisplay import Display
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains

telegram_token = os.environ['TELEGRAM_BOT_TOKEN']
telegram_chat_id = os.environ['TELEGRAM_CHAT_ID']

num_iterations = 10
num_of_guests = 6
locations = ['Tokyo', 'Osaka']
target_days = ['18', '19', '20', '21']  # July 2026
target_month = 7
target_year = 2026
test_mode = os.environ.get('TEST_MODE', '').lower() == 'true'

BOOKING_URLS = {
    'Tokyo': 'https://reserve.pokemon-cafe.jp/reserve/step1',
    'Osaka': 'https://osaka.pokemon-cafe.jp/reserve/step1',
}

SITE_URLS = {
    'Tokyo': 'https://reserve.pokemon-cafe.jp/',
    'Osaka': 'https://osaka.pokemon-cafe.jp/',
}

magic_cell = ''

display = Display(visible=0, size=(800, 800))
display.start()

chromedriver_autoinstaller.install()

def send_telegram(avail_slots, filename, location):
    try:
        base_url = f"https://api.telegram.org/bot{telegram_token}"
        text = f"\U0001F6A8 [{location}] Available days found by Spinarak bot:\n\n"
        for day in avail_slots:
            text += f"• {day}\n"
        text += f"\nGo book now: {BOOKING_URLS[location]}"

        with open(filename, 'rb') as photo:
            response = requests.post(
                f"{base_url}/sendPhoto",
                data={"chat_id": telegram_chat_id, "caption": text},
                files={"photo": photo}
            )
        response.raise_for_status()
        print("Telegram message sent!")
    except Exception as e:
        print(f"Telegram error: {str(e)}")

def send_telegram_test(filename, location):
    try:
        base_url = f"https://api.telegram.org/bot{telegram_token}"
        text = f"\U0001F9EA [TEST - {location}] No slots found — screenshot of current calendar page"
        with open(filename, 'rb') as photo:
            response = requests.post(
                f"{base_url}/sendPhoto",
                data={"chat_id": telegram_chat_id, "caption": text},
                files={"photo": photo}
            )
        response.raise_for_status()
        print("Telegram test message sent!")
    except Exception as e:
        print(f"Telegram error: {str(e)}")

def navigate_to_month(driver, month, year):
    # Navigate forward until the target month/year is visible on the calendar.
    # XPaths below cover common patterns — may need adjustment if the site changes.
    for _ in range(24):
        page = driver.page_source
        if str(year) in page and (f"{month}月" in page or f"/{month}/" in page):
            return
        next_btn = None
        for xpath in [
            "//*[contains(@class,'next')]",
            "//*[contains(@class,'arrow-right')]",
            "//button[contains(text(),'翌月')]",
            "//a[contains(text(),'翌月')]",
            "//*[contains(@aria-label,'next')]",
        ]:
            try:
                next_btn = driver.find_element(By.XPATH, xpath)
                break
            except NoSuchElementException:
                continue
        if next_btn:
            next_btn.click()
            time.sleep(random.randint(1, 2))
        else:
            print("Could not find next month button — scraping current month")
            return

def is_target_day(text):
    for day in target_days:
        if (day + '日') in text or f'/{day}' in text or text.strip().startswith(day):
            return True
    return False

def create_booking(num_of_guests, location):
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--window-size=1200,1200")

    driver = webdriver.Chrome(options=chrome_options)
    driver.get(SITE_URLS[location])
    time.sleep(random.randint(3, 5))

    # In test mode, immediately screenshot the landing page so we can inspect
    # the current site structure and update XPaths if needed
    if test_mode:
        print(f'[{location}] TEST MODE — screenshot of landing page')
        filename = f'hits/pokemon-cafe-test-landing-{location.lower()}-{date.today().strftime("%Y%m%d")}-{uuid.uuid4().hex}.png'
        driver.save_screenshot(filename)
        send_telegram_test(filename, location)
        driver.quit()
        return

    try:
        # Scroll to bottom so the CGU checkbox becomes interactable
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.randint(2, 3))
        # Accept terms: try the original ID first, then fall back to generic checkbox/button
        try:
            driver.find_element(By.XPATH, "//*[@id=\"forms-agree\"]/div/div[1]/label").click()
            driver.find_element(By.XPATH, "//*[@id=\"forms-agree\"]/div/div[2]/button").click()
        except NoSuchElementException:
            driver.find_element(By.XPATH, "//input[@type='checkbox']").click()
            driver.find_element(By.XPATH, "//button[@type='submit'] | //input[@type='submit'] | //button[contains(@class,'agree')] | //button[contains(@class,'next')]").click()
        time.sleep(random.randint(3, 6))
        driver.find_element(By.XPATH, "/html/body/div/div/div[2]/div/div/a").click()
        time.sleep(random.randint(3, 6))
        select = Select(driver.find_element(By.NAME, 'guest'))
        time.sleep(random.randint(2, 3))
        select.select_by_index(num_of_guests)

        navigate_to_month(driver, target_month, target_year)
        time.sleep(random.randint(1, 2))

        # In test mode, send a screenshot immediately after navigation
        # so we can verify the bot is on the right page regardless of what happens next
        if test_mode:
            print(f'[{location}] TEST MODE — sending screenshot of current calendar page')
            filename = f'hits/pokemon-cafe-test-{date.today().strftime("%Y%m%d")}-{uuid.uuid4().hex}.png'
            driver.save_screenshot(filename)
            send_telegram_test(filename, location)
            driver.quit()
            return

        soup = BeautifulSoup(driver.page_source, "html.parser")
        calendar_cells = soup.find_all("li")

        available = False
        available_slots = []
        global magic_cell
        for cell in calendar_cells:
            text = cell.text.strip()
            if "(full)" not in text.lower() and "n/a" not in text.lower() and is_target_day(text):
                available_slots.append(text)
                available = True
                magic_cell = text

        driver.execute_script('document.getElementsByTagName("html")[0].style.scrollBehavior = "auto"')
        element = driver.find_element(By.XPATH, "/html/body/div/div/div[2]/div/div[1]/p[3]")
        element.location_once_scrolled_into_view
        if available:
            print(f'[{location}] Slot(s) AVAILABLE:')
            for day in available_slots:
                print(day)
            filename = f'hits/pokemon-cafe-slot-found-{date.today().strftime("%Y%m%d")}-{uuid.uuid4().hex}.png'
            driver.save_screenshot(filename)
            send_telegram(available_slots, filename, location)
        else:
            print(f"[{location}] No available slots found for 18-21 July :(")

        driver.quit()
    except Exception as e:
        print(f"[{location}] Error: {e}")
        try:
            filename = f'hits/pokemon-cafe-error-{location.lower()}-{date.today().strftime("%Y%m%d")}-{uuid.uuid4().hex}.png'
            driver.save_screenshot(filename)
            send_telegram_test(filename, location)
        except Exception as e2:
            print(f"[{location}] Could not send error screenshot: {e2}")
        driver.quit()

iterations = 1 if test_mode else num_iterations
for x in range(iterations):
    for loc in locations:
        create_booking(num_of_guests, loc)
