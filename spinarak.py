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

# Define your Telegram settings as repo secrets
telegram_token = os.environ['TELEGRAM_BOT_TOKEN']
telegram_chat_id = os.environ['TELEGRAM_CHAT_ID']

num_iterations = 10
num_of_guests=3
location = 'Osaka'

magic_cell = ''

display = Display(visible=0, size=(800, 800))
display.start()

chromedriver_autoinstaller.install()  # Check if the current version of chromedriver exists
                                      # and if it doesn't exist, download it automatically,
                                      # then add chromedriver to path

def send_telegram(avail_slots, filename):
    try:
        base_url = f"https://api.telegram.org/bot{telegram_token}"
        text = "\U0001F6A8 Available days found by Spinarak bot:\n\n"
        for day in avail_slots:
            text += f"• {day}\n"
        text += "\nGo book now: https://osaka.pokemon-cafe.jp/reserve/step1"

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

def create_booking(num_of_guests, location):
    '''Create a reservation for Pokemon Cafe
    Keyword arguments:
    num_of_guests -- number of guests to book (1-8)
    '''

    if location == "Tokyo":
        website = "https://reserve.pokemon-cafe.jp/"
    elif location == "Osaka":
        website = "https://osaka.pokemon-cafe.jp/"

    chrome_options = webdriver.ChromeOptions()
    options = [
        "--window-size=1200,1200",
    ]

    for option in options:
        chrome_options.add_argument(option)

    driver = webdriver.Chrome(options=chrome_options)
    driver.get(website)

    try:
        driver.find_element(By.XPATH, "//*[@id=\"forms-agree\"]/div/div[1]/label").click()
        driver.find_element(By.XPATH, "//*[@id=\"forms-agree\"]/div/div[2]/button").click()
        time.sleep(random.randint(3, 6))
        driver.find_element(By.XPATH, "/html/body/div/div/div[2]/div/div/a").click()
        time.sleep(random.randint(3, 6))
        select = Select(driver.find_element(By.NAME, 'guest'))
        time.sleep(random.randint(2, 3))

        select.select_by_index(num_of_guests)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        calendar_cells = soup.find_all("li")

        available = False
        available_slots = []
        global magic_cell
        for cell in calendar_cells:
            if "(full)" not in cell.text.lower() and "n/a" not in cell.text.lower():
                available_slots.append(cell.text.strip())
                available = True
                magic_cell = cell.text

        driver.execute_script('document.getElementsByTagName("html")[0].style.scrollBehavior = "auto"')
        element = driver.find_element(By.XPATH, "/html/body/div/div/div[2]/div/div[1]/p[3]")
        element.location_once_scrolled_into_view
        if available:
            print('Slot(s) AVAILABLE: ')
            for day in available_slots:
                print(day + ' ')
            filename = 'hits/pokemon-cafe-slot-found-' + date.today().strftime("%Y%m%d") + '-' + str(uuid.uuid4().hex) + '.png'
            driver.save_screenshot(filename)
            send_telegram(available_slots, filename)
        else:
            print("No available slots found :(")

        driver.quit()
    except NoSuchElementException:
        pass

[create_booking(num_of_guests, location) for x in range(num_iterations)]
