#!/usr/bin/env python3

from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver import Firefox
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait
import csv
import datetime
import logging
import os
import random
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib


class Tor:
    def __init__(self, cmd=os.getenv("TOR_CMD", "tor")):
        self.cmd = cmd
        self.proc = None
        self.socks_port = None
        self.data_directory = tempfile.mkdtemp(prefix="tordata")
        self.torrc = list(tempfile.mkstemp(prefix="torrc"))[1]


    def generate_torrc(self):
        config = {
            "SocksPort": self.socks_port,
            "DataDirectory": self.data_directory
        }

        try:
            with open(self.torrc, "w") as f:
                for key, value in config.items():
                    f.write(f"{key} {value}\n")
        except OSError as e:
            logging.critical("Writing torrc failed! Exiting")
            quit()


    def set_socks_port(self, port_from=9050, port_to=19050):
        while True:
            socks_port = random.randrange(port_from, port_to)
             
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", socks_port)) != 0:
                    logging.debug(f"SocksPort {socks_port} is available.")
                    return socks_port

            logging.warning(f"SocksPort {socks_port} is NOT available! Trying other port...")


    def connect(self, timeout=60):
        logging.info("Starting Tor...")

        self.socks_port = self.set_socks_port()

        self.generate_torrc()

        try:
            self.proc = subprocess.Popen([self.cmd, "-f", self.torrc], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            
            tor_error = True

            start_time = time.time()
            total_time = 0

            while total_time <= timeout:
                if "Bootstrapped 100% (done): Done" in self.proc.stdout.readline().decode():
                    logging.info(f"Tor running on SocksPort {self.socks_port}...")

                    tor_error = False

                    break

                total_time = time.time() - start_time

            assert not tor_error
        except Exception as e:
            logging.error("Tor Error! Not connected... Exiting")
            quit()

        return self


    def quit(self):
        logging.debug("Quitting Tor...")

        try:
            self.proc.kill()
        except ProcessLookupError as e:
            pass

        try:
            os.remove(self.torrc)
        except FileNotFoundError as e:
            pass

        try:
            shutil.rmtree(self.data_directory, ignore_errors=True)
        except FileNotFoundError as e:
            pass


    def renew_circuit(self):
        try:
            os.kill(self.proc.pid, signal.SIGHUP)

            logging.info("New Tor Circuit established.")
        except ProcessLookupError as e:
            logging.warning("Tor is not running!")


class Browser:
    def __init__(self, width=2000, height=3000, load_timeout=30, locale="en-us", headless=True, tor=None):
        self.tor = tor

        options = Options()
        options.add_argument(f"--width={width}")
        options.add_argument(f"--height={height}")
        options.set_preference("intl.accept_languages", locale); 
        options.set_preference("browser.cache.disk.enable", False);
        options.set_preference("browser.cache.memory.enable", False);
        options.set_preference("browser.cache.offline.enable", False);
        options.set_preference("network.http.use-cache", False);

        if headless:
            options.add_argument("--headless")

        if tor is not None:
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.socks", "127.0.0.1")
            options.set_preference("network.proxy.socks_port", tor.socks_port)
            options.set_preference("network.proxy.socks_remote_dns", False)

        self.driver = Firefox(options=options)
        self.driver.set_page_load_timeout(load_timeout)


    def quit(self):
        logging.debug("Quitting Browser...")
        self.driver.quit()


    def request(self, url, timeout=1, retry_delay=10):
        error_messages = ["Sorry, you are rate limited. Please wait a few moments then try again.",
                          "Something went wrong. Try reloading."]

        while True:
            try:
                self.driver.delete_all_cookies()
                self.driver.get(url)
            except Exception as e:
                logging.error(f"Connection Error! retrying in {retry_delay} seconds...")
                
                if self.tor is not None:
                    self.tor.renew_circuit()

                time.sleep(retry_delay)

                continue

            if self.tor is None:
                time.sleep(timeout)
            else:
                time.sleep((timeout*2))

            for msg in error_messages:
                while True:
                    try:
                        assert self.driver.find_element(By.XPATH, f"//span[text()='{msg}']").text == msg

                        logging.error(f"Twitter Error ['{msg}']! retrying in {retry_delay} seconds...")

                        if self.tor is not None:
                            self.tor.renew_circuit()

                        time.sleep(retry_delay)

                        self.request(url, timeout, retry_delay)
                    except NoSuchElementException as e:
                        break
                    except AssertionError as e:
                        continue

            else:
                break


class Twitter:
    def __init__(self, username, tor=None):
        self.username = username
        self.tor = tor


    def get_joined_date(self, browser):
        logging.debug("Fetching Joined Date...")
        browser.request(f"https://twitter.com/{self.username}")

        try:
            joined = browser.driver.find_element(By.XPATH, "//span[contains(text(), 'Joined')]").text.split(" ")
            date_joined = f"{joined[2]}-{time.strptime(joined[1], '%B').tm_mon:02}-01"

            return date_joined
        except NoSuchElementException as e:
            logging.error("Error! User not found... Exiting")

            if self.tor is not None:
                self.tor.quit()

            browser.quit()
            quit()


    def scrape_tweets(self, browser, date_start, date_end, ignore_lockfile=False, max_retries=3):
        tweets_total = 0

        while datetime.datetime.strptime(date_start, "%Y-%m-%d") <= datetime.datetime.strptime(date_end, "%Y-%m-%d"):
            date_until = (datetime.datetime.strptime(date_start, "%Y-%m-%d") + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            date_current = date_start

            search_query = f"from:{username} exclude:retweets since:{date_start} until:{date_until}"
            search_url = f"https://twitter.com/search?q={urllib.parse.quote(search_query)}&src=typed_query&f=live"

            logging.debug(search_url)

            browser.request(search_url)

            tweets = []

            no_results = False

            try:
                browser.driver.find_element(By.XPATH, f"//span[text()='No results for \"{search_query}\"']")
                
                no_results = True
            except NoSuchElementException as e:
                t = -1

                while t < len(tweets):
                    t = len(tweets)

                    browser.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)

                    tweets = browser.driver.find_elements(By.CSS_SELECTOR, "article")

            if not no_results and len(tweets) == 0:
                logging.debug(f"Search Error! Retrying ({date_start})...")
                self.scrape_tweets(browser, date_start, date_end, ignore_lockfile, max_retries)

            tweet_ids = []

            for tweet in tweets:
                try:
                    tweet_id = tweet.find_element(By.CSS_SELECTOR, "time").find_element(By.XPATH, "..").get_attribute("href").split("/")[-1]
                    tweet_ids.append(tweet_id)
                except Exception as e:
                    pass

            try:
                with open(os.path.join(data_path, username, f"{self.username}.lock"), "w") as f:
                    f.write(f"{date_start}")
            except:
                pass

            logging.info(f"{date_current} ({len(tweet_ids)})")

            if len(tweet_ids) > 0:
                for tweet_id in reversed(tweet_ids):
                    archived = None

                    for retry in range(max_retries):
                        archived = self.archive_tweet(browser, tweet_id)

                        if archived:
                            break

                        logging.error(f"Tweet Error! retrying {tweet_id}... ({retry+1}/{max_retries})")

                    if archived is None:
                        logging.error(f"Failed to archive Tweet {tweet_id}!")

                    tweets_total += 1

            date_start = (datetime.datetime.strptime(date_start, "%Y-%m-%d") + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

        logging.info(f"Finished! {tweets_total} tweets archived.")


    def archive_tweet(self, browser, tweet_id, timeout=30):
        try:
            with open(os.path.join(data_path, username, f"{self.username}.csv")) as f:
                for row in csv.reader(f, delimiter="|"):
                    if row[0] == tweet_id:
                        logging.debug(f"Tweet {tweet_id} already exists. skipping...")

                        return True
        except FileNotFoundError as e:
            pass

        tweet_url = f"https://twitter.com/{self.username}/status/{tweet_id}"

        start_time = time.time()

        browser.request(tweet_url)

        try:
            tweet_date_element = WebDriverWait(browser.driver, timeout).until(lambda d: browser.driver.find_element(By.XPATH, f"//a[translate(@href, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='/{self.username}/status/{tweet_id}']"))
            tweet_element = tweet_date_element.find_element(By.XPATH, f"../../../../../../../../../..")
        except Exception as e:
            logging.error(f"Tweet Error! Timeout reached ({tweet_id})...")

            if self.tor is not None:
                self.tor.renew_circuit()

            return

        try:
            tweet_text = tweet_element.find_element(By.CSS_SELECTOR, "article div > div > div:nth-child(3) div[id^='id_']").text.replace("\n", " ").replace("  ", " ")

            if tweet_text.startswith("Replying to @"):
                tweet_text = tweet_element.find_element(By.CSS_SELECTOR, "article div > div > div:nth-child(3) > div:nth-child(2) div[id^='id_']").text.replace("\n", " ").replace("  ", " ")
        except NoSuchElementException as e:
            tweet_text = ""

        if len(tweet_id) > 10:
            tweet_date = datetime.datetime.fromtimestamp(int(((int(tweet_id) >> 22) + 1288834974657) / 1000)).isoformat()
        else:
            try:
                tweet_date = datetime.datetime.strptime(tweet_date_element.find_element(By.CSS_SELECTOR, "span").text, "%I:%M %p · %b %d, %Y").isoformat()
            except NoSuchElementException as e:
                return

        try:
            with open(os.path.join(data_path, username, f"{self.username}.csv"), "a+") as f:
                csv.writer(f, delimiter="|").writerow([tweet_id, tweet_date, tweet_text])
        except Exception as e:
            logging.error("Failed to write to CSV file!")

            return

        try:
            with open(os.path.join(data_path, username, "screenshots", f"{tweet_id}.png"), "wb") as screenshot_file:
                screenshot_file.write(tweet_element.screenshot_as_png)
        except Exception as e:
            logging.error("Failed to save screenshot file")

            return

        total_time = time.time() - start_time

        logging.info(f"{tweet_url} ({total_time:.2f}s)")

        return True


if __name__ == "__main__":
    try:
        debug = bool(int(os.getenv("DEBUG", 0)))
        loglevel = logging.DEBUG if debug else logging.INFO

        logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=loglevel)
        logging.getLogger('selenium.webdriver.remote.remote_connection').setLevel(logging.CRITICAL)
        logging.getLogger("urllib3").setLevel(logging.CRITICAL)

        headless = bool(int(os.getenv("HEADLESS", 1)))
        ignore_lockfile = bool(int(os.getenv("IGNORE_LOCKFILE", 0)))

        data_path = os.getenv("DATA_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))

        try:
            username = sys.argv[1].lower()
            usernames = [username] 
        except IndexError:
            logging.debug("No Username given...")

            try:
                usernames = sorted(next(os.walk(data_path))[1])
            except Exception as e:
                logging.critical("Error! Cannot read data path... Exiting")
                quit()

        if len(usernames) == 0:
            logging.error("Error! No usernames given... Exiting")
            quit()

        logging.info(f"Usernames found: {', '.join(usernames)}")

        tor = None

        if bool(int(os.getenv("USE_TOR", 0))):
            tor = Tor().connect()

        for username in usernames:
            logging.info(f"Username: @{username}")

            browser = Browser(tor=tor, headless=headless)

            try:
                date_start = sys.argv[2]
            except IndexError as e:
                date_start = None

            try:
                date_end = sys.argv[3]
            except IndexError as e:
                date_end = datetime.datetime.today().strftime("%Y-%m-%d")

            if date_start is None:
                try:
                    assert not ignore_lockfile

                    with open(os.path.join(data_path, username, f"{username}.lock")) as f:
                        date_start = f.read().replace("\n", "")

                    logging.info(f"Lockfile found!")
                except Exception as e:
                    date_start = Twitter(username, tor).get_joined_date(browser)

            try:
                datetime.datetime.strptime(date_start, "%Y-%m-%d")
                datetime.datetime.strptime(date_end, "%Y-%m-%d")
            except ValueError as e:
                logging.critical("Invalid Date Format! Exiting...")

                if tor is not None:
                    tor.quit()
                 
                browser.quit()
                quit()

            logging.info(f"Start: {date_start}")
            logging.info(f"End: {date_end}")

            try:
                os.makedirs(os.path.join(data_path, username, "screenshots"))
            except OSError as e:
                pass

            Twitter(username, tor).scrape_tweets(browser, date_start, date_end, ignore_lockfile)

            browser.quit()
    except KeyboardInterrupt:
        try:
            browser.quit()
        except:
            pass

        if tor is not None:
            tor.quit()

        logging.info("Exiting...")
