#!/usr/bin/env python3

from PIL import Image
from io import BytesIO
from random import randrange
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver import Firefox
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
import csv
import datetime
import os
import re
import requests
import socket
import sys
import time
import urllib
import socket
import shutil
import subprocess
import stem
import stem.connection
import stem.process
import tempfile


class Tor:
    def __init__(self, cmd=os.getenv("TOR_CMD", "/opt/homebrew/bin/tor")):
        self.cmd = cmd
        self.proc = None
        self.listen_address = "127.0.0.1"
        self.socks_port = randrange(10000, 20000)
        self.control_port = randrange(20000, 30000)
        self.control_password = "".join(chr(randrange(97, 122)) for i in range(8))
        self.data_directory = tempfile.mkdtemp(prefix="tordata")


    def hash_control_password(self, password):
        return subprocess.Popen([self.cmd, "--hash-password", password], stdout=subprocess.PIPE).stdout.read().decode().replace("\n", "")
        

    def connect(self):
        print("Starting Tor...")

        try:
            self.config = {
                "SocksPort": str(self.socks_port),
                "ControlPort": str(self.control_port),
                "HashedControlPassword": self.hash_control_password(self.control_password),
                "DataDirectory": self.data_directory
            }

            self.proc = stem.process.launch_tor_with_config(config=self.config, tor_cmd=self.cmd, take_ownership=True)
            
            print(f"Tor running on SocksPort {self.socks_port}...")
        except Exception as e:
            print("Tor Error! Not connected...")
            quit()

        return self


    def quit(self):
        try:
            self.proc.teminate()
            shutil.rmtree(tor_data_directory, ignore_errors=True)
        except:
            pass


    def renew_circuit(self):
        try:
            s = socket.socket()
            s.connect((self.listen_address, self.control_port))
            s.send(f"AUTHENTICATE \"{self.control_password}\"\r\nSIGNAL NEWNYM\r\n".encode())

            print("New Tor Circuit established.")
        except Exception as e:
            print("Tor is not running!")


class Browser:
    def __init__(self, width=2000, height=3000, locale="en-us", headless=True, tor=None):
        self.tor = tor

        options = Options()
        options.add_argument(f"--width={width}")
        options.add_argument(f"--height={height}")
        options.set_preference("intl.accept_languages", locale); 

        if headless:
            options.add_argument("--headless")

        if tor is not None:
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.socks", tor.listen_address)
            options.set_preference("network.proxy.socks_port", tor.socks_port)
            options.set_preference("network.proxy.socks_remote_dns", False)

        self.driver = Firefox(options=options)


    def quit(self):
        self.driver.quit()


    def request(self, url, wait_delay=1, retry_delay=10):
        error_messages = ["Sorry, you are rate limited. Please wait a few moments then try again.",
                          "Something went wrong. Try reloading."]

        if self.tor is not None:
            wait_delay = 5

        connection_error = True
        twitter_error = True

        while connection_error or twitter_error:
            try:
                self.driver.get(url)

                time.sleep(wait_delay)

                connection_error = False
            except Exception as e:
                print(f"Connection Error! retrying in {retry_delay} seconds...")
                print(e)
                
                if self.tor is not None:
                    self.tor.renew_circuit()

                connection_error = True
                time.sleep(retry_delay)

                continue

            for msg in error_messages:
                try:
                    self.driver.find_element(By.XPATH, f"//span[text()='{msg}']")

                    print(f"Twitter Error ['{msg}']! retrying in {retry_delay} seconds...")

                    if self.tor is not None:
                        self.tor.renew_circuit()
                    
                    twitter_error = True

                    time.sleep(retry_delay)

                    break
                except NoSuchElementException:
                    twitter_error = False


class Twitter:
    def __init__(self, username, tor=None):
        self.username = username
        self.tor = tor


    def get_joined_date(self):
        browser = Browser(tor=self.tor)
        browser.request(f"https://twitter.com/{self.username}")

        try:
            joined = browser.driver.find_element(By.XPATH, "//span[contains(text(), 'Joined')]").text.split(" ")
            date_joined = f"{joined[2]}-{time.strptime(joined[1], '%B').tm_mon:02}-01"

            browser.quit()

            return date_joined
        except NoSuchElementException as e:
            print("Error!")

            browser.quit()
            quit()


    def scrape_tweets(self, date_start, date_end):
        tweets_total = 0

        while datetime.datetime.strptime(date_start, "%Y-%m-%d") <= datetime.datetime.strptime(date_end, "%Y-%m-%d"):
            date_until = (datetime.datetime.strptime(date_start, "%Y-%m-%d") + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            date_current = date_start

            search_query = f"from:{username} exclude:retweets since:{date_start} until:{date_until}"
            search_url = f"https://twitter.com/search?q={urllib.parse.quote(search_query)}&src=typed_query&f=live"

            browser = Browser(tor=self.tor)
            browser.request(search_url)

            tweets = []

            try:
                browser.driver.find_element(By.XPATH, f"//span[text()='No results for \"{search_query}\"']")
            except NoSuchElementException as e:
                t = -1

                while t < len(tweets):
                    t = len(tweets)

                    browser.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)

                    tweets = browser.driver.find_elements(By.CSS_SELECTOR, "article")

            tweet_ids = []

            for tweet in tweets:
                try:
                    tweet_id = tweet.find_element(By.CSS_SELECTOR, "time").find_element(By.XPATH, "..").get_attribute("href").split("/")[-1]
                    tweet_ids.append(tweet_id)
                except NoSuchElementException as e:
                    pass

            browser.driver.quit()

            try:
                with open(os.path.join(data_path, f"{self.username}.lock"), "w") as f:
                    f.write(f"{date_start}")
            except:
                pass

            print(f"\n{date_current} ({len(tweet_ids)})")

            if len(tweet_ids) > 0:
                for tweet_id in reversed(tweet_ids):
                    self.archive_tweet(tweet_id)
                    tweets_total += 1

            date_start = (datetime.datetime.strptime(date_start, "%Y-%m-%d") + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

        print(f"\nFinished! {tweets_total} tweets archived.")


    def archive_tweet(self, tweet_id, max_retries = 5):
        start_time = time.time()

        try:
            with open(os.path.join(data_path, f"{self.username}.csv")) as f:
                for row in csv.reader(f, delimiter="|"):
                    if row[0] == tweet_id:
                        return
        except FileNotFoundError:
            pass

        tweet_url = f"https://twitter.com/{self.username}/status/{tweet_id}"
        screenshot_file = os.path.join(data_path, "screenshots", f"{tweet_id}.png")

        for i in range(max_retries):
            try:
                browser = Browser(tor=self.tor)
                browser.request(tweet_url)

                time.sleep(i)

                tweet_date_element = browser.driver.find_element(By.XPATH, f"//a[translate(@href, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='/{self.username}/status/{tweet_id}']")
                tweet_element = tweet_date_element.find_element(By.XPATH, f"../../../../../../../../../..")

                break
            except NoSuchElementException as e:
                print(f"Page Load failed! Retrying... ({i+1}/{max_retries})")

                browser.quit()

                if i == max_retries-1:
                    return

        tweet_type = "T"

        try:
            tweet_text = tweet_element.find_element(By.CSS_SELECTOR, "article div > div > div:nth-child(3) div[id^='id_']").text.replace("\n", " ").replace("  ", " ")
        except NoSuchElementException as e:
            tweet_text = ""

        if tweet_text.startswith("Replying to @"):
            tweet_type = "C"

            try:
                tweet_text = tweet_element.find_element(By.CSS_SELECTOR, "article div > div > div:nth-child(3) > div:nth-child(2) div[id^='id_']").text.replace("\n", " ").replace("  ", " ")
            except NoSuchElementException as e:
                tweet_text = ""

        if len(tweet_id) > 10:
            tweet_date = datetime.datetime.fromtimestamp(int(((int(tweet_id) >> 22) + 1288834974657) / 1000)).isoformat()
        else:
            try:
                tweet_date = datetime.datetime.strptime(tweet_date_element.find_element(By.CSS_SELECTOR, "span").text, "%I:%M %p · %b %d, %Y").isoformat()
            except NoSuchElementException as e:
                browser.quit()
                return

        try:
            with open(os.path.join(data_path, f"{self.username}.csv"), "a+") as f:
                csv.writer(f, delimiter="|").writerow([tweet_id, tweet_date, tweet_type, tweet_text])

            screenshot = tweet_element.screenshot_as_png
            Image.open(BytesIO(screenshot)).save(screenshot_file)

            total_time = time.time() - start_time

            print(f"{tweet_url} ({total_time:.2f}s)")

            if self.tor is not None and total_time > 15:
                print("Page Load too slow! Establishing new Tor Circuit...")

                self.tor.renew_circuit()
        except Exception as e:
            pass

        browser.quit()


if __name__ == "__main__":
    use_tor = bool(os.getenv("USE_TOR", 0))

    if use_tor:
        tor = Tor().connect()
    else:
        tor = None

    try:
        username = sys.argv[1].lower()
    except IndexError:
        print("No Username given! Exiting...")
        quit()
         
    print(f"Username: @{username}")

    try:
        date_start = sys.argv[2]
    except IndexError:
        date_start = None

    try:
        date_end = sys.argv[3]
    except IndexError:
        date_end = datetime.datetime.today().strftime("%Y-%m-%d")

    try:
        data_path = os.path.join("data", username)

        try:
            os.makedirs(os.path.join(data_path, "screenshots"))
        except OSError:
            pass

        if date_start is None:
            try:
                with open(os.path.join(data_path, f"{username}.lock")) as f:
                    date_start = f.read().replace("\n", "")

                print(f"Lockfile found!")
            except FileNotFoundError:
                date_start = Twitter(username, tor).get_joined_date()

        try:
            datetime.datetime.strptime(date_start, "%Y-%m-%d")
            datetime.datetime.strptime(date_end, "%Y-%m-%d")
        except ValueError:
            print("Invalid Date Format! Exiting...")
            quit()

        print(f"Start: {date_start}")
        print(f"End: {date_end}")

        Twitter(username, tor).scrape_tweets(date_start, date_end)
    except KeyboardInterrupt:
        try:
            browser.quit()
        except:
            pass

        if tor is not None:
            tor.quit()

        print("Exiting...")
