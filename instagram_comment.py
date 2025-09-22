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
from selenium.common.exceptions import (
    SessionNotCreatedException,
    TimeoutException,
    StaleElementReferenceException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ENV_USERNAME_KEY = "INSTAGRAM_USERNAME"
ENV_PASSWORD_KEY = "INSTAGRAM_PASSWORD"
ENV_COMMENT_KEY = "INSTAGRAM_COMMENT"
ENV_PROFILE_KEY = "INSTAGRAM_PROFILE_URL"
ENV_CHROME_PROFILE_DIR = "CHROME_USER_DATA_DIR"
ENV_CHROME_HEADLESS = "CHROME_HEADLESS"


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


def get_optional(values: Dict[str, str], key: str) -> str | None:
    """Return an optional environment variable value or ``None`` when missing."""

    value = values.get(key)
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def str_to_bool(value: str | None, *, default: bool = True) -> bool:
    """Return the boolean interpretation of ``value``."""

    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _create_chrome_options(*, headless: bool, user_data_dir: Path | None) -> Options:
    """Return a configured ``Options`` instance for Chrome."""

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--remote-debugging-port=0")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    if user_data_dir is not None:
        options.add_argument(f"--user-data-dir={user_data_dir}")
    return options


def build_driver(
    user_data_dir: Path | None = None,
    *,
    headless: bool = True,
) -> webdriver.Chrome:
    """Configure and return a Chrome WebDriver instance.

    When Chrome fails to boot (commonly with ``DevToolsActivePort`` errors) the
    driver is retried with progressively more permissive settings. This keeps
    the automation usable on systems where headless mode or persistent
    profiles are unstable without forcing users to pre-tune their
    configuration.
    """

    attempts: list[tuple[bool, Path | None, str | None]] = [
        (headless, user_data_dir, None),
    ]

    if headless:
        attempts.append(
            (
                False,
                user_data_dir,
                "Chrome failed to start headless; retrying with a visible browser window.",
            )
        )

    if user_data_dir is not None:
        attempts.append(
            (
                False,
                None,
                "Chrome failed to start with the persistent profile; retrying without it.",
            )
        )

    last_error: SessionNotCreatedException | None = None
    for headless_attempt, profile_dir, message in attempts:
        options = _create_chrome_options(
            headless=headless_attempt, user_data_dir=profile_dir
        )
        try:
            return webdriver.Chrome(options=options)
        except SessionNotCreatedException as exc:
            last_error = exc
            error_message = exc.msg or ""
            if "DevToolsActivePort" not in error_message and "crashed" not in error_message:
                raise
            if message:
                print(message, file=sys.stderr)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Chrome driver failed to start for an unknown reason")


def login(driver: webdriver.Chrome, username: str, password: str) -> None:
    """Log into Instagram with the provided credentials."""

    login_url = "https://www.instagram.com/accounts/login/"
    driver.get(login_url)
    wait = WebDriverWait(driver, 20)

    def _login_page_loaded(driver: webdriver.Chrome) -> bool:
        return (
            "accounts/login" not in driver.current_url
            or driver.find_elements(By.NAME, "username")
        )

    wait.until(_login_page_loaded)

    if "accounts/login" not in driver.current_url:
        wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//a[contains(@href, '/explore/')]")
            )
        )
        return

    username_field = driver.find_element(By.NAME, "username")
    password_field = driver.find_element(By.NAME, "password")

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

    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "main")))
    click_wait = WebDriverWait(driver, 5)

    post_selectors = [
        "article a[href*='/p/']",
        "main section a[href*='/p/']",
        "main div[role='presentation'] a[href*='/p/']",
    ]

    for _ in range(10):
        for selector in post_selectors:
            post_links = driver.find_elements(By.CSS_SELECTOR, selector)
            if post_links:
                first_post = post_links[0]
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", first_post
                )
                try:
                    click_wait.until(
                        lambda d, element=first_post: all(
                            (element.is_displayed(), element.is_enabled())
                        )
                    )
                    first_post.click()
                    return
                except (StaleElementReferenceException, TimeoutException):
                    continue
                except WebDriverException:
                    continue
        driver.execute_script("window.scrollBy(0, 400)")
        time.sleep(0.5)

    raise RuntimeError("Could not locate any posts on the profile page")


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

    user_data_dir: Path | None = None
    try:
        env_values = load_env(env_path)
        username = get_required(env_values, ENV_USERNAME_KEY)
        password = get_required(env_values, ENV_PASSWORD_KEY)
        comment = get_required(env_values, ENV_COMMENT_KEY)
        profile_url = get_required(env_values, ENV_PROFILE_KEY)
        headless = str_to_bool(get_optional(env_values, ENV_CHROME_HEADLESS), default=True)
        profile_dir_value = get_optional(env_values, ENV_CHROME_PROFILE_DIR)
        if profile_dir_value and profile_dir_value.strip().lower() in {
            "none",
            "disable",
            "disabled",
        }:
            user_data_dir = None
        else:
            user_data_dir = Path(profile_dir_value or ".selenium-profile").expanduser()
            user_data_dir.mkdir(parents=True, exist_ok=True)
    except (FileNotFoundError, EnvConfigError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    driver = build_driver(user_data_dir=user_data_dir, headless=headless)
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
