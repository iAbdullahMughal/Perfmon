# Perfmon

## Instagram Comment Automation

This repository includes a Selenium automation script that logs into Instagram
using credentials stored in a `.env` file and posts a comment on the first post
of the configured profile.

### Requirements

* Python 3.10+
* Google Chrome or Chromium with a compatible ChromeDriver available on your `PATH`
* Python packages:
  * `selenium`

Install the Python dependency with:

```bash
pip install -r requirements.txt
```

### Environment configuration

Create a `.env` file in the project root (or supply a path to another `.env`
file when running the script) with the following keys:

```env
INSTAGRAM_USERNAME=your_username
INSTAGRAM_PASSWORD=your_password
INSTAGRAM_COMMENT=Nice photo!
INSTAGRAM_PROFILE_URL=https://www.instagram.com/your_username/
```

### Running the automation

```bash
python instagram_comment.py            # Uses ./.env by default
python instagram_comment.py custom.env  # Explicit env file path
```

The script launches a headless Chrome browser, signs into Instagram, navigates
to the supplied profile, opens the first post, and submits the configured
comment.
