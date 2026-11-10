# Website Uptime Monitor

Checks your websites every 5 minutes and emails the addresses you set for each
site when it goes **down**, while it **stays down** (reminder every 6 h by default),
and when it **recovers**. Runs free on GitHub Actions — no server needed.

## Setup (about 10 minutes)

1. **Create a private GitHub repo** and upload these files
   (keep the `.github/workflows/monitor.yml` folder structure).

2. **Edit `sites.yml`** — add each website with its own alert emails.

3. **Create a Gmail App Password** for the account that will send alerts:
   Google Account → Security → turn on 2-Step Verification → search "App passwords"
   → create one called "Site Monitor" → copy the 16-character password.

4. **Add repo secrets**: repo → Settings → Secrets and variables → Actions → New repository secret

   | Secret      | Value (Gmail)                 |
   |-------------|-------------------------------|
   | SMTP_HOST   | smtp.gmail.com                |
   | SMTP_PORT   | 587                           |
   | SMTP_USER   | your Gmail address            |
   | SMTP_PASS   | the 16-character app password |
   | ALERT_FROM  | (optional) e.g. `Site Monitor <you@gmail.com>` |

   Any other SMTP provider works too (Zoho, Outlook, Brevo, cPanel mail) — just use its host/port.

5. **Test it**: Actions tab → "Website uptime monitor" → **Run workflow**.
   Open the run to see each site's status. To test an alert, temporarily add a
   fake URL like `https://this-does-not-exist-12345.com`.

## Per-site options

```yaml
- name: Client Website
  url: https://example.org
  emails: [you@example.com, client@example.org]
  expected_status: 200       # optional: require an exact status code
  must_contain: "Welcome"    # optional: page must contain this text
```

`must_contain` is useful for catching sites that "load" but show an error page
or a blank white screen (common with broken WordPress plugins).

## Good to know

- **False alarms**: each failure is re-checked (`retries`) before an email goes out.
- **Schedule**: GitHub may delay scheduled runs by a few minutes at busy times;
  5 minutes is the shortest interval GitHub allows.
- **Inactive repos**: GitHub pauses schedules in *public* repos after 60 days
  without commits. Use a private repo, or just push any small change occasionally.
- `status.json` is written by the bot to remember which sites are down — don't edit it.
