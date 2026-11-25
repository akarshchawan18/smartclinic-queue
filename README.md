# SmartClinic Queue

## Folder layout

```text
Tokensystem/
  main.py
  analytics.py
  requirements.txt
  templates/
    analytics.html
    base.html
    join.html
    login.html
    poster.html
    staff.html
    status.html
    _logo.html
    _macros.html
  static/
    sound.js
    status.js
    style.css
```

## Where to change what
| I want to change... | Edit |
|---|---|
| Colours, fonts, spacing, button style | `static/style.css` (brand colours in section 1) |
| Text on the patient form | `templates/join.html` |
| Status messages ("Your turn...") | `static/status.js` |
| Staff screen layout | `templates/staff.html` |
| Logo | `templates/_logo.html` |
| Clinic name, phone, address, doctor list | Environment variables in PyCharm |
| Queue rules, WhatsApp message, PIN check | `main.py` |

Template and CSS edits show after a browser refresh (Ctrl+F5). Python edits need a restart.

## Run (PyCharm)
Install once: `"C:\python 311\python.exe" -m pip install -r requirements.txt`
Run `main.py` (it starts the server). Open http://localhost:8000/join

## Settings (PyCharm environment variables)
`CLINIC_NAME` (default SmartClinic Demo), `TAGLINE`, `CENTER_PHONE`, `CENTER_ADDRESS`,
`DOCTORS` (comma-separated queues, e.g. `Sample Collection,Radiology,Ultrasound`),
`BASE_URL` (e.g. http://192.168.0.106:8000), `STAFF_PIN`, `APP_SECRET`, `DB_PATH`,
`WA_TOKEN`, `WA_PHONE_ID`, `WA_TEMPLATE`, `WA_LANG`, `WA_API_VERSION`.

## WhatsApp template (Utility)
Name `queue_token`, body:
`Hello! Your token number is {{1}} for {{2}}. Track your queue live: {{3}} Thank you for choosing us.`
Leave `WA_TOKEN` / `WA_PHONE_ID` empty to run in demo mode (message printed in the console).

## Known gaps (fix before a paying client)
No limit on wrong PIN attempts; WhatsApp send is not retried; single server process (SQLite);
Standard features (remote check-in, leave-now alert, reply buttons) are not built yet.
