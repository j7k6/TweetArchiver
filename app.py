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
import socket
import sys
import time
import urllib
import shutil
import stem
import stem.connection
import stem.process
from stem.control import Controller
from stem import Signal


use_tor = bool(os.getenv("USE_TOR", 0))
tor_cmd = os.getenv("TOR_CMD", "/opt/homebrew/bin/tor")
tor_socks_port = randrange(10000, 20000)
tor_control_port = randrange(20000, 30000)


def init_browser():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--width=2000")
    options.add_argument("--height=3000")
    options.set_preference("intl.accept_languages", "en-us"); 

    if use_tor:
        options.set_preference("network.proxy.type", 1)
        options.set_preference("network.proxy.socks", "127.0.0.1")
        options.set_preference("network.proxy.socks_port", tor_socks_port)
        options.set_preference("network.proxy.socks_remote_dns", False)

    return Firefox(options=options)


def new_tor_circuit():
    try:
        with Controller.from_port() as controller:
            controller.authenticate()
            controller.signal(Signal.NEWNYM)

        print("New Tor Circuit established.")
    except Exception as e:
        print("Tor is not running!")


def archive_tweet(username, tweet_id):
    start_time = time.time()

    try:
        with open(os.path.join(data_path, f"{username}.csv")) as f:
            for row in csv.reader(f, delimiter="|"):
                if row[0] == tweet_id:
                    return
    except FileNotFoundError:
        pass

    tweet_url = f"https://twitter.com/{username}/status/{tweet_id}"
    screenshot_file = os.path.join(data_path, "screenshots", f"{tweet_id}.png")

    max_retries = 5

    for i in range(max_retries):
        try:
            browser = browser_handler(tweet_url)
            time.sleep(i)

            tweet_date_element = browser.find_element(By.XPATH, f"//a[translate(@href, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='/{username}/status/{tweet_id}']")
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

    if use_tor and len(tweet_id) > 10:
        tweet_date = datetime.datetime.fromtimestamp(int(((int(tweet_id) >> 22) + 1288834974657) / 1000)).isoformat()
    else:
        try:
            tweet_date = datetime.datetime.strptime(tweet_date_element.find_element(By.CSS_SELECTOR, "span").text, "%I:%M %p · %b %d, %Y").isoformat()
        except NoSuchElementException as e:
            browser.quit()
            return

    try:
        with open(os.path.join(data_path, f"{username}.csv"), "a+") as f:
            csv.writer(f, delimiter="|").writerow([tweet_id, tweet_date, tweet_type, tweet_text])

        screenshot = tweet_element.screenshot_as_png
        Image.open(BytesIO(screenshot)).save(screenshot_file)

        total_time = time.time() - start_time

        print(f"{tweet_url} ({total_time:.2f}s)")

        if total_time > 15:
            print("Page Load too slow! Establishing new Tor Circuit...")

            new_tor_circuit()
    except Exception as e:
        pass

    browser.quit()


def browser_handler(url):
    connection_error = True
    twitter_error = True

    wait_delay = 1
    retry_delay = 10
    error_messages = ["Sorry, you are rate limited. Please wait a few moments then try again.",
                      "Something went wrong. Try reloading."]

    if use_tor:
        wait_delay = 5

    while connection_error or twitter_error:
        try:
            browser = init_browser()
            browser.get(url)

            time.sleep(wait_delay)

            connection_error = False
        except Exception as e:
            print(f"Connection Error! retrying in {retry_delay} seconds...")
            
            if use_tor:
                new_tor_circuit()

            browser.quit()

            connection_error = True
            time.sleep(retry_delay)
            continue

        for msg in error_messages:
            try:
                browser.find_element(By.XPATH, f"//span[text()='{msg}']")
                browser.quit()

                print(f"Twitter Error ['{msg}']! retrying in {retry_delay} seconds...")

                if use_tor:
                    new_tor_circuit()
                
                twitter_error = True

                time.sleep(retry_delay)
                break
            except NoSuchElementException:
                twitter_error = False

    return browser


def get_joined_date(username):
    browser = browser_handler(f"https://twitter.com/{username}")

    try:
        joined = browser.find_element(By.XPATH, "//span[contains(text(), 'Joined')]").text.split(" ")
        date_joined = f"{joined[2]}-{time.strptime(joined[1], '%B').tm_mon:02}-01"

        browser.quit()

        return date_joined
    except NoSuchElementException as e:
        print("Error!")

        browser.quit()
        quit()


def scrape_tweets(username, date_start, date_end):
    tweets_total = 0

    while datetime.datetime.strptime(date_start, "%Y-%m-%d") <= datetime.datetime.strptime(date_end, "%Y-%m-%d"):
        date_until = (datetime.datetime.strptime(date_start, "%Y-%m-%d") + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        date_current = date_start

        search_query = f"from:{username} exclude:retweets since:{date_start} until:{date_until}"
        search_url = f"https://twitter.com/search?q={urllib.parse.quote(search_query)}&src=typed_query&f=live"

        browser = browser_handler(search_url)

        tweets = []

        try:
            browser.find_element(By.XPATH, f"//span[text()='No results for \"{search_query}\"']")
        except NoSuchElementException as e:
            t = -1

            while t < len(tweets):
                t = len(tweets)

                browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)

                tweets = browser.find_elements(By.CSS_SELECTOR, "article")

        tweet_ids = []

        for tweet in tweets:
            try:
                tweet_id = tweet.find_element(By.CSS_SELECTOR, "time").find_element(By.XPATH, "..").get_attribute("href").split("/")[-1]
                tweet_ids.append(tweet_id)
            except NoSuchElementException as e:
                pass

        browser.quit()

        try:
            with open(os.path.join(data_path, f"{username}.lock"), "w") as f:
                f.write(f"{date_start}")
        except:
            pass

        print(f"\n{date_current} ({len(tweet_ids)})")

        if len(tweet_ids) > 0:
            for tweet_id in reversed(tweet_ids):
                archive_tweet(username, tweet_id)
                tweets_total += 1

        date_start = (datetime.datetime.strptime(date_start, "%Y-%m-%d") + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"\nFinished! {tweets_total} tweets archived.")


if __name__ == "__main__":
    if use_tor:
        tor_data_directory = f"/tmp/tordata{tor_socks_port}"
        tor_config = {
                "SocksPort": str(tor_socks_port),
                "ControlPort": str(tor_control_port),
                "CookieAuthentication": "0",
        #        "ExitNodes": "{de}",
                "DataDirectory": tor_data_directory
            }

        try:
            tor_process = stem.process.launch_tor_with_config(config=tor_config, tor_cmd=tor_cmd, take_ownership=True)
            print(f"Tor running on SocksPort {tor_socks_port}...")
        except Exception as e:
            print(e)
            quit()

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
                date_start = get_joined_date(username)

        try:
            datetime.datetime.strptime(date_start, "%Y-%m-%d")
            datetime.datetime.strptime(date_end, "%Y-%m-%d")
        except ValueError:
            print("Invalid Date Format! Exiting...")
            quit()

        print(f"Start: {date_start}")
        print(f"End: {date_end}")

        scrape_tweets(username, date_start, date_end)
    except KeyboardInterrupt:
        try:
            browser.quit()
        except:
            pass

        if use_tor:
            try:
                tor_process.kill()
                shutil.rmtree(tor_data_directory, ignore_errors=True)
            except:
                pass

        print("Exiting...")
