"""Automate Instagram login and comment using Selenium.

This script loads credentials from a .env file, logs into Instagram,
opens the target profile, and comments on the first post.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Dict

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ENV_USERNAME_KEY = "INSTAGRAM_USERNAME"
ENV_PASSWORD_KEY = "INSTAGRAM_PASSWORD"
ENV_COMMENT_KEY = "INSTAGRAM_COMMENT"
ENV_PROFILE_KEY = "INSTAGRAM_PROFILE_URL"


class EnvConfigError(RuntimeError):
    """Raised when the .env file is missing a required value."""


def load_env(path: str | os.PathLike[str] = ".env") -> Dict[str, str]:
    """Load key/value pairs from a simple ``.env`` file.

    Parameters
    ----------
    path:
        Path to the environment file. Defaults to ``.env`` in the current
        working directory.

    Returns
    -------
    dict
        Dictionary containing parsed key/value pairs.

    Notes
    -----
    The parser implements a tiny subset of the ``.env`` format: it
    ignores blank lines and comments, and treats everything after the
    first ``=`` character as the value. Basic single and double quotes
    are stripped from the start and end of the value when present.
    """

    env_path = Path(path)
    if not env_path.exists():
        raise FileNotFoundError(f"Environment file not found: {env_path}")

    values: Dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if value.startswith("\"") and value.endswith("\""):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        values[key.strip()] = value
    return values


def get_required(values: Dict[str, str], key: str) -> str:
    """Return a required key from ``values`` or raise ``EnvConfigError``."""

    try:
        value = values[key]
    except KeyError as exc:  # pragma: no cover - safety net
        raise EnvConfigError(f"Missing required environment variable: {key}") from exc

    if not value:
        raise EnvConfigError(f"Environment variable {key} is empty")
    return value


def build_driver() -> webdriver.Chrome:
    """Configure and return a headless Chrome WebDriver instance."""

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=options)


def login(driver: webdriver.Chrome, username: str, password: str) -> None:
    """Log into Instagram with the provided credentials."""

    driver.get("https://www.instagram.com/accounts/login/")
    wait = WebDriverWait(driver, 20)

    username_field = wait.until(
        EC.presence_of_element_located((By.NAME, "username"))
    )
    password_field = wait.until(
        EC.presence_of_element_located((By.NAME, "password"))
    )

    username_field.clear()
    username_field.send_keys(username)
    password_field.clear()
    password_field.send_keys(password)
    password_field.send_keys(Keys.ENTER)

    # Instagram may display dialogs (e.g. save login info) after logging in.
    # Wait for the main feed navigation to appear as a signal that login succeeded.
    wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/explore/')]")))


def navigate_to_first_post(driver: webdriver.Chrome, profile_url: str) -> None:
    """Open the first post on the provided Instagram profile."""

    driver.get(profile_url)
    wait = WebDriverWait(driver, 20)

    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article")))
    post_links = driver.find_elements(By.CSS_SELECTOR, "article a[href*='/p/']")
    if not post_links:
        raise RuntimeError("Could not locate any posts on the profile page")

    post_links[0].click()


def leave_comment(driver: webdriver.Chrome, comment: str) -> None:
    """Leave ``comment`` on the currently open Instagram post."""

    wait = WebDriverWait(driver, 20)
    textarea = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "textarea[aria-label='Add a comment…']"))
    )
    textarea.click()
    textarea = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "textarea[aria-label='Add a comment…']")))
    textarea.send_keys(comment)
    textarea.send_keys(Keys.ENTER)

    # Give Instagram a moment to submit the comment to avoid closing the driver too early.
    time.sleep(3)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the Instagram comment automation script."""

    argv = argv or sys.argv[1:]
    env_path = Path(argv[0]) if argv else Path(".env")

    try:
        env_values = load_env(env_path)
        username = get_required(env_values, ENV_USERNAME_KEY)
        password = get_required(env_values, ENV_PASSWORD_KEY)
        comment = get_required(env_values, ENV_COMMENT_KEY)
        profile_url = get_required(env_values, ENV_PROFILE_KEY)
    except (FileNotFoundError, EnvConfigError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    driver = build_driver()
    try:
        login(driver, username, password)
        navigate_to_first_post(driver, profile_url)
        leave_comment(driver, comment)
    except TimeoutException as exc:
        print(f"Automation timed out: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - unexpected failure logging
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 3
    finally:
        driver.quit()

    print("Comment posted successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
