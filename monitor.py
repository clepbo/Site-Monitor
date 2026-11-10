"""
Simple website uptime monitor.

Reads sites.yml, checks every site, and emails the configured addresses when
a site goes DOWN, while it stays down (optional reminders), and when it
RECOVERS. State is kept in status.json so you only get emails on changes.

Email settings come from environment variables (GitHub Secrets):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, ALERT_FROM (optional)
If SMTP_HOST is not set, alerts are printed instead of sent (dry run).
"""

import json
import os
import smtplib
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
CONFIG_FILE = ROOT / "sites.yml"
STATE_FILE = ROOT / "status.json"
USER_AGENT = "Mozilla/5.0 (compatible; SiteMonitor/1.0)"


# ---------------------------------------------------------------- checking
def check_once(site, timeout):
    """Return (is_up, detail, response_ms)."""
    req = urllib.request.Request(site["url"], headers={"User-Agent": USER_AGENT})
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = resp.read(500_000).decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        status, body = e.code, ""
    except urllib.error.URLError as e:
        return False, f"Could not connect: {e.reason}", None
    except Exception as e:  # timeouts, SSL errors, resets
        return False, f"{type(e).__name__}: {e}", None

    ms = int((time.monotonic() - start) * 1000)
    expected = site.get("expected_status")
    if expected is not None and status != int(expected):
        return False, f"HTTP {status} (expected {expected})", ms
    if expected is None and status >= 400:
        return False, f"HTTP {status}", ms
    needle = site.get("must_contain")
    if needle and needle not in body:
        return False, f'HTTP {status} but page is missing the text "{needle}"', ms
    return True, f"HTTP {status}", ms


def check_site(site, timeout, retries):
    is_up, detail, ms = check_once(site, timeout)
    for _ in range(retries):
        if is_up:
            break
        time.sleep(5)
        is_up, detail, ms = check_once(site, timeout)
    return is_up, detail, ms


# ---------------------------------------------------------------- emailing
def send_email(to_addrs, subject, body):
    host = os.environ.get("SMTP_HOST")
    if not host:
        print(f"\n[DRY RUN – no SMTP_HOST set] To: {', '.join(to_addrs)}\nSubject: {subject}\n{body}\n")
        return
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASS", "")

    msg = EmailMessage()
    msg["From"] = os.environ.get("ALERT_FROM") or user
    msg["To"] = ", ".join(to_addrs)
    msg["Subject"] = subject
    msg.set_content(body)

    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
            s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls(context=ctx)
            s.login(user, password)
            s.send_message(msg)
    print(f"Email sent to {', '.join(to_addrs)}: {subject}")


def fmt_duration(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h {m}m" if h else f"{m}m"


# ---------------------------------------------------------------- main
def main():
    config = yaml.safe_load(CONFIG_FILE.read_text())
    settings = config.get("settings", {}) or {}
    timeout = settings.get("timeout_seconds", 15)
    retries = settings.get("retries", 2)
    remind_hours = settings.get("remind_every_hours", 6)

    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    now = time.time()
    now_txt = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    any_down = False

    for site in config.get("sites", []):
        name, url = site["name"], site["url"]
        emails = site.get("emails") or []
        prev = state.get(url, {"up": True})

        is_up, detail, ms = check_site(site, timeout, retries)
        print(f"{'UP  ' if is_up else 'DOWN'}  {name:<30} {detail}" + (f"  ({ms} ms)" if ms else ""))

        entry = {"name": name, "up": is_up, "detail": detail}

        if not is_up:
            any_down = True
            down_since = prev.get("down_since", now) if not prev["up"] else now
            last_alert = prev.get("last_alert", 0) if not prev["up"] else 0
            entry["down_since"] = down_since
            entry["last_alert"] = last_alert

            first_failure = prev["up"]
            reminder_due = remind_hours and (now - last_alert) >= remind_hours * 3600
            if emails and (first_failure or reminder_due):
                prefix = "🔴 DOWN" if first_failure else "🔴 STILL DOWN"
                send_email(
                    emails,
                    f"{prefix}: {name}",
                    f"{name} is not responding.\n\n"
                    f"URL:      {url}\n"
                    f"Problem:  {detail}\n"
                    f"Checked:  {now_txt}\n"
                    f"Down for: {fmt_duration(now - down_since)}\n\n"
                    f"You'll get another email when it's back up.",
                )
                entry["last_alert"] = now
        else:
            if not prev["up"] and emails:
                send_email(
                    emails,
                    f"🟢 RECOVERED: {name}",
                    f"{name} is back up.\n\n"
                    f"URL:        {url}\n"
                    f"Status:     {detail}\n"
                    f"Checked:    {now_txt}\n"
                    f"Was down:   {fmt_duration(now - prev.get('down_since', now))}",
                )

        state[url] = entry

    # drop sites removed from the config
    configured = {s["url"] for s in config.get("sites", [])}
    state = {u: v for u, v in state.items() if u in configured}
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")
    return 0  # never fail the job just because a site is down


if __name__ == "__main__":
    sys.exit(main())
