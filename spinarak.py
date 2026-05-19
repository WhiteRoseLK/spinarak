import asyncio, os, uuid, random, requests, glob
from datetime import date
from bs4 import BeautifulSoup
from pyvirtualdisplay import Display
from pydoll.browser import Chrome
from pydoll.browser.options import ChromiumOptions

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
debug_screenshot_sent = set()

os.makedirs('hits', exist_ok=True)
os.makedirs('debug', exist_ok=True)

for f in glob.glob('debug/*.png') + glob.glob('hits/*.png'):
    os.remove(f)

display = Display(visible=0, size=(1200, 1200))
display.start()

BOOKING_URLS = {
    'Tokyo': 'https://reserve.pokemon-cafe.jp/reserve/step1',
    'Osaka': 'https://osaka.pokemon-cafe.jp/reserve/step1',
}
SITE_URLS = {
    'Tokyo': 'https://reserve.pokemon-cafe.jp/',
    'Osaka': 'https://osaka.pokemon-cafe.jp/',
}


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

async def take_debug_screenshot(tab, location, step):
    filename = f'debug/{location.lower()}-{step}-{date.today().strftime("%Y%m%d")}-{uuid.uuid4().hex}.png'
    await tab.take_screenshot(path=filename)
    send_telegram_debug(filename, location, step)
    return filename

def is_target_day(text):
    for day in target_days:
        if (day + '日') in text or f'/{day}' in text or text.strip().startswith(day):
            return True
    return False

async def navigate_to_month(tab, month, year):
    for _ in range(24):
        html = await tab.page_source
        if str(year) in html and (f"{month}月" in html or f"/{month}/" in html):
            return
        next_btn = None
        for selector in [
            {'class_name': 'next'},
            {'tag_name': 'button', 'text': '翌月'},
            {'tag_name': 'a', 'text': '翌月'},
        ]:
            try:
                next_btn = await tab.find(**selector, timeout=2, raise_exc=False)
                if next_btn:
                    break
            except Exception:
                continue
        if next_btn:
            await next_btn.click()
            await asyncio.sleep(random.uniform(1, 2))
        else:
            print("Could not find next month button — scraping current month")
            return

async def create_booking(num_of_guests, location):
    options = ChromiumOptions()
    options.add_argument('--window-size=1200,1200')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')

    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.enable_auto_solve_cloudflare_captcha(time_to_wait_captcha=15)
        await tab.go_to(SITE_URLS[location])
        await asyncio.sleep(random.uniform(3, 5))

        if test_mode:
            await take_debug_screenshot(tab, location, 'landing-page')
            return

        try:
            await tab.execute_script(
                "var cb = document.querySelector('input[type=\"checkbox\"]');"
                "if(cb){ cb.scrollIntoView(); cb.click(); }"
            )
            await asyncio.sleep(1)
            await tab.execute_script(
                "var btn = document.querySelector('button[type=\"submit\"], input[type=\"submit\"], #forms-agree button, button');"
                "if(btn) btn.click();"
            )
            await asyncio.sleep(random.uniform(3, 6))

            await asyncio.sleep(5)  # wait for CF auto-solve

            if location not in debug_screenshot_sent:
                debug_screenshot_sent.add(location)
                await take_debug_screenshot(tab, location, 'after-cgu')

            start_link = await tab.find(tag_name='a', timeout=5, raise_exc=False)
            if start_link:
                await start_link.click()
            else:
                if location not in error_screenshot_sent:
                    error_screenshot_sent.add(location)
                    await take_debug_screenshot(tab, location, 'no-start-link')
                raise Exception("Could not find start reservation link")

            await asyncio.sleep(random.uniform(3, 6))

            await tab.execute_script(
                f"var s=document.querySelector('select[name=\"guest\"]');"
                f"if(s){{s.value='{num_of_guests}';s.dispatchEvent(new Event('change'));}}"
            )
            await asyncio.sleep(random.uniform(2, 3))

            await navigate_to_month(tab, target_month, target_year)
            await asyncio.sleep(random.uniform(1, 2))

            if location not in debug_screenshot_sent:
                debug_screenshot_sent.add(location)
                await take_debug_screenshot(tab, location, 'calendar-page')

            html = await tab.page_source
            soup = BeautifulSoup(html, "html.parser")
            calendar_cells = soup.find_all("li")

            available = False
            available_slots = []
            for cell in calendar_cells:
                text = cell.text.strip()
                if "(full)" not in text.lower() and "n/a" not in text.lower() and is_target_day(text):
                    available_slots.append(text)
                    available = True

            if available:
                print(f'[{location}] Slot(s) AVAILABLE:')
                for day in available_slots:
                    print(day)
                filename = f'hits/pokemon-cafe-slot-found-{date.today().strftime("%Y%m%d")}-{uuid.uuid4().hex}.png'
                await tab.take_screenshot(path=filename)
                send_telegram(available_slots, filename, location)
            else:
                print(f"[{location}] No available slots found for 18-21 July :(")

        except Exception as e:
            print(f"[{location}] Error: {e}")
            if location not in error_screenshot_sent:
                error_screenshot_sent.add(location)
                try:
                    await take_debug_screenshot(tab, location, 'error')
                except Exception as e2:
                    print(f"[{location}] Could not send error screenshot: {e2}")

async def main():
    iterations = 1 if test_mode else num_iterations
    for _ in range(iterations):
        for loc in locations:
            await create_booking(num_of_guests, loc)

asyncio.run(main())
