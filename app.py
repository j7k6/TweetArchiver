#!/usr/bin/env python3

from PIL import Image
from io import BytesIO
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver import Firefox
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
import csv
import datetime
import os
import re
import sys
import time
import urllib


def init_browser():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--width=2000")
    options.add_argument("--height=3000")
    options.set_preference("intl.accept_languages", "en-us"); 

    return Firefox(options=options)


def archive_tweet(username, tweet_id):
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
            tweet_date_element = browser.find_element(By.XPATH, f"//a[translate(@href, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='/{username}/status/{tweet_id}']")
            tweet_element = tweet_date_element.find_element(By.XPATH, f"../../../../../../../../../..")
            break
        except NoSuchElementException as e:
            print(f"Element not found! Retrying... ({i+1}/{max_retries})")
            browser.quit()

            if i == max_retries-1:
                print(f"Giving up... ({tweet_id})")
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
        with open(os.path.join(data_path, f"{username}.csv"), "a+") as f:
            csv.writer(f, delimiter="|").writerow([tweet_id, tweet_date, tweet_type, tweet_text])

        screenshot = tweet_element.screenshot_as_png
        Image.open(BytesIO(screenshot)).save(screenshot_file)

        print(tweet_url)
    except Exception as e:
        pass

    browser.quit()


def browser_handler(url):
    connection_error = True
    twitter_error = True

    retry_delay = 30
    error_messages = ["Sorry, you are rate limited. Please wait a few moments then try again.",
                      "Something went wrong. Try reloading."]

    while connection_error or twitter_error:
        try:
            browser = init_browser()
            browser.get(url)

            time.sleep(1)

            connection_error = False
        except Exception as e:
            print(f"Connection Error! retrying in {retry_delay} seconds...")

            browser.quit()

            connection_error = True
            time.sleep(retry_delay)
            continue

        for msg in error_messages:
            try:
                browser.find_element(By.XPATH, f"//span[text()='{msg}']")
                browser.quit()

                print(f"Twitter Error ['{msg}']! retrying in {retry_delay} seconds...")
                
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

        print(f"\n{date_current} ({len(tweet_ids)})")

        if len(tweet_ids) > 0:
            for tweet_id in reversed(tweet_ids):
                archive_tweet(username, tweet_id)
                tweets_total += 1

        try:
            with open(os.path.join(data_path, f"{username}.lock"), "w") as f:
                f.write(f"{date_start}")
        except:
            pass

        date_start = (datetime.datetime.strptime(date_start, "%Y-%m-%d") + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"\nFinished! {tweets_total} tweets archived.")


if __name__ == "__main__":
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
        except Exception:
            pass

        print("Exiting...")
