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
error_screenshot_sent = set()

os.makedirs('hits', exist_ok=True)
os.makedirs('debug', exist_ok=True)

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

def send_telegram_debug(filename, location, label):
    try:
        base_url = f"https://api.telegram.org/bot{telegram_token}"
        text = f"\U0001F9EA [DEBUG - {location}] {label}"
        with open(filename, 'rb') as photo:
            response = requests.post(
                f"{base_url}/sendPhoto",
                data={"chat_id": telegram_chat_id, "caption": text},
                files={"photo": photo}
            )
        response.raise_for_status()
        print(f"Debug screenshot sent: {label}")
    except Exception as e:
        print(f"Telegram error: {str(e)}")

def navigate_to_month(driver, month, year):
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

def debug_screenshot(driver, location, step):
    filename = f'debug/{location.lower()}-{step}-{date.today().strftime("%Y%m%d")}-{uuid.uuid4().hex}.png'
    driver.save_screenshot(filename)
    send_telegram_debug(filename, location, step)
    return filename

def create_booking(num_of_guests, location):
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--window-size=1200,1200")

    driver = webdriver.Chrome(options=chrome_options)
    driver.get(SITE_URLS[location])
    time.sleep(random.randint(3, 5))

    if test_mode:
        debug_screenshot(driver, location, 'landing-page')
        driver.quit()
        return

    try:
        # Scroll the CGU checkbox into view and click via JS
        checkbox = driver.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
        driver.execute_script("arguments[0].scrollIntoView(true);", checkbox)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", checkbox)
        submit = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit'], #forms-agree button")
        driver.execute_script("arguments[0].click();", submit)
        time.sleep(random.randint(3, 6))
        debug_screenshot(driver, location, 'after-cgu')
        # Click the "start reservation" link — try multiple selectors as the site may change
        start_link = None
        for selector in [
            (By.XPATH, "/html/body/div/div/div[2]/div/div/a"),
            (By.XPATH, "//a[contains(@href,'step')]"),
            (By.XPATH, "//a[contains(@href,'reserve')]"),
            (By.XPATH, "//a[contains(text(),'予約')]"),
            (By.CSS_SELECTOR, "a.btn, a.button, .reservation a, main a"),
        ]:
            try:
                start_link = driver.find_element(*selector)
                break
            except NoSuchElementException:
                continue
        if start_link:
            start_link.click()
        else:
            debug_screenshot(driver, location, 'no-start-link-found')
            raise Exception("Could not find start reservation link")
        time.sleep(random.randint(3, 6))
        select = Select(driver.find_element(By.NAME, 'guest'))
        time.sleep(random.randint(2, 3))
        select.select_by_index(num_of_guests)

        navigate_to_month(driver, target_month, target_year)
        time.sleep(random.randint(1, 2))

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
        if location not in error_screenshot_sent:
            error_screenshot_sent.add(location)
            try:
                debug_screenshot(driver, location, 'error')
            except Exception as e2:
                print(f"[{location}] Could not send error screenshot: {e2}")
        driver.quit()

iterations = 1 if test_mode else num_iterations
for x in range(iterations):
    for loc in locations:
        create_booking(num_of_guests, loc)
