"""The sign-in pages and the two emails. Plain server-rendered HTML.

These pages sit in front of the Dash app, so they cannot use it: no React, no
Dash assets, one inline stylesheet in the terminal's dark palette. Every value
that came from a visitor goes through ``esc``.
"""

from __future__ import annotations

import html
import time
from urllib.parse import quote

from demo.access.mailer import Mail
from demo.access.settings import AccessSettings
from demo.access.store import Visitor

PRODUCT = "SearchForAlpha Lab"

_CSS = """
:root{color-scheme:dark;--bg:#0b0b0b;--panel:#141414;--line:#2a2a2a;--text:#e8e8e8;--muted:#a8a8a8;
  --accent:#FFA726;--warn:#FFCA28;--bad:#EF5350;--good:#66BB6A;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:var(--bg);color:var(--text);font:15px/1.55 var(--sans);
  display:flex;align-items:flex-start;justify-content:center;padding:clamp(24px,8vh,96px) 16px 48px}
main{width:100%;max-width:460px}
main.wide{max-width:1280px}
.brand{font:600 12px/1 var(--mono);letter-spacing:.14em;color:var(--accent);text-transform:uppercase;margin:0 0 18px}
.brand span{color:var(--muted)}
.card{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:24px}
h1{font-size:21px;line-height:1.3;margin:0 0 10px}
p{margin:0 0 14px}
.muted{color:var(--muted)}
.small{font-size:13px}
label{display:block;font:600 12px/1 var(--mono);letter-spacing:.06em;color:var(--muted);text-transform:uppercase;margin:18px 0 8px}
input[type=email],input[type=text],input[type=password]{width:100%;padding:11px 12px;border-radius:4px;border:1px solid #3a3a3a;
  background:#0f0f0f;color:var(--text);font:16px var(--sans)}
input.code{font:600 26px/1 var(--mono);letter-spacing:.35em;text-align:center}
input:focus{outline:2px solid var(--accent);outline-offset:1px;border-color:transparent}
button,.button{display:inline-block;width:100%;margin-top:16px;padding:12px 14px;border:0;border-radius:4px;background:var(--accent);
  color:#111;font:700 14px/1 var(--sans);letter-spacing:.02em;cursor:pointer;text-align:center;text-decoration:none}
button.link{width:auto;margin:0;padding:0;background:none;color:var(--accent);font:inherit;text-decoration:underline}
a{color:var(--accent)}
.alert{border-left:3px solid var(--warn);background:#1b1a14;padding:10px 12px;border-radius:3px;margin:0 0 16px;font-size:14px}
.alert.bad{border-left-color:var(--bad);background:#1d1414}
.alert.good{border-left-color:var(--good);background:#131b14}
.privacy{margin-top:22px;padding-top:16px;border-top:1px solid var(--line);font-size:12.5px;color:var(--muted)}
.privacy p{margin:0 0 8px}
.row{display:flex;gap:12px;flex-wrap:wrap;align-items:center;justify-content:space-between;margin-top:16px;font-size:13px}
"""


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fmt_date(ts: float | None) -> str:
    if not ts:
        return "—"
    day = time.gmtime(ts)
    return f"{day.tm_mday} {time.strftime('%b %Y', day)}"


def fmt_time(ts: float | None) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ts)) if ts else "—"


def page(title: str, body: str, *, wide: bool = False) -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta name=\"robots\" content=\"noindex,nofollow\">"
        f"<title>{esc(title)} — {PRODUCT} demo</title><style>{_CSS}</style></head><body>"
        f"<main class=\"{'wide' if wide else ''}\"><p class=\"brand\">{PRODUCT} <span>· public demo</span></p>"
        f"{body}</main></body></html>"
    )


def _alert(message: str | None, tone: str = "") -> str:
    return f'<p class="alert {tone}" role="alert">{esc(message)}</p>' if message else ""


def privacy_note(settings: AccessSettings) -> str:
    months = max(1, round(settings.retention_days / 30))
    return (
        '<div class="privacy">'
        f"<p><strong>What is stored.</strong> Your email address, when you sign in, the IP address you sign in from, "
        "and which parts of the demo you use (pages opened, backtests, optimiser runs, tickers loaded).</p>"
        "<p><strong>Why.</strong> To give each person one trial, and to see how the demo is used so it can get better. "
        "Nothing is sold or shared, and you are not added to any mailing list.</p>"
        f"<p><strong>For how long.</strong> Deleted {months} months after your last visit, or as soon as you ask: "
        f'<a href="mailto:{esc(settings.contact_email)}">{esc(settings.contact_email)}</a>.</p>'
        "</div>"
    )


def signin_page(settings: AccessSettings, *, next_path: str, email: str = "", error: str | None = None) -> str:
    body = (
        '<div class="card">'
        f"<h1>Try the research terminal free for {settings.trial_days} days</h1>"
        "<p class=\"muted\">Charts, indicators, backtests and the strategy optimiser on a frozen market snapshot. "
        "Enter your email and we will send you a sign-in code — no password, no card.</p>"
        f"{_alert(error, 'bad')}"
        '<form method="post" action="/access" novalidate>'
        f'<input type="hidden" name="next" value="{esc(next_path)}">'
        '<label for="email">Email</label>'
        f'<input id="email" name="email" type="email" autocomplete="email" inputmode="email" required value="{esc(email)}" autofocus>'
        "<button type=\"submit\">Email me a sign-in code</button>"
        "</form>"
        f"{privacy_note(settings)}"
        "</div>"
    )
    return page("Sign in", body)


def sent_page(
    settings: AccessSettings,
    *,
    address: str,
    next_path: str,
    error: str | None = None,
    notice: str | None = None,
) -> str:
    body = (
        '<div class="card">'
        "<h1>Check your inbox</h1>"
        f"{_alert(notice, 'good')}{_alert(error, 'bad')}"
        f"<p>If <strong>{esc(address)}</strong> can receive mail, a 6-digit code is on its way. "
        f"Type it below, or open the link in the email. Both work for {settings.code_minutes} minutes.</p>"
        '<form method="post" action="/access/code" novalidate>'
        f'<input type="hidden" name="email" value="{esc(address)}">'
        f'<input type="hidden" name="next" value="{esc(next_path)}">'
        '<label for="code">Sign-in code</label>'
        '<input id="code" name="code" class="code" type="text" inputmode="numeric" autocomplete="one-time-code" '
        'pattern="[0-9 ]*" maxlength="7" required autofocus>'
        '<button type="submit">Sign in</button>'
        "</form>"
        '<div class="row muted">'
        f'<a href="/access?next={esc(quote(next_path, safe="/"))}">Use a different address</a>'
        '<span>Nothing arrived? Check spam, then ask again in a minute.</span>'
        "</div>"
        "</div>"
    )
    return page("Check your inbox", body)


def link_confirm_page(*, address: str, token: str, next_path: str = "/") -> str:
    # The link in the email lands here and signs in only on a click. Mail
    # security scanners open every link they see; a link that signed in on a
    # GET would be spent by the scanner before its owner ever clicked it.
    body = (
        '<div class="card">'
        "<h1>Sign in to the demo</h1>"
        f"<p>Continue as <strong>{esc(address)}</strong>.</p>"
        '<form method="post" action="/access/verify">'
        f'<input type="hidden" name="t" value="{esc(token)}">'
        f'<input type="hidden" name="next" value="{esc(next_path)}">'
        '<button type="submit">Open the demo</button>'
        "</form>"
        "</div>"
    )
    return page("Sign in", body)


def link_dead_page() -> str:
    body = (
        '<div class="card">'
        "<h1>That link has expired</h1>"
        "<p>Sign-in links work once, for a few minutes. Ask for a new one and it will arrive straight away.</p>"
        '<a class="button" href="/access">Get a new sign-in code</a>'
        "</div>"
    )
    return page("Link expired", body)


def ended_page(settings: AccessSettings, visitor: Visitor | None) -> str:
    if visitor is not None and visitor.revoked_at:
        headline = "Your demo access has been switched off"
        detail = "If you think that is a mistake, write and say so."
    else:
        until = fmt_date(visitor.expires_at) if visitor else None
        headline = "Your free trial has ended"
        detail = (
            f"Your {settings.trial_days}-day access ended on {until}. " if until else ""
        ) + "If you would like more time, or to talk about using it for real, get in touch — it is a person who answers."
    body = (
        '<div class="card">'
        f"<h1>{esc(headline)}</h1>"
        f"<p>{esc(detail)}</p>"
        f'<a class="button" href="mailto:{esc(settings.contact_email)}?subject={esc("SearchForAlpha Lab demo")}">'
        f"Write to {esc(settings.contact_email)}</a>"
        '<form method="post" action="/access/signout" class="row"><button class="link" type="submit">Sign out</button></form>'
        "</div>"
    )
    return page("Trial ended", body)


def account_html(visitor: Visitor) -> str:
    """The signed-in line ``demo.banner`` carries inside the dashboard."""
    return (
        '<span class="sfa-demo-account">Signed in as '
        f"<b>{esc(visitor.address)}</b> · free trial until {esc(fmt_date(visitor.expires_at))} · "
        '<form method="post" action="/access/signout">'
        '<button type="submit" class="sfa-demo-signout">Sign out</button></form></span>'
    )


def code_mail(settings: AccessSettings, *, to: str, code: str, link: str) -> Mail:
    spaced = f"{code[:3]} {code[3:]}"
    text = (
        f"Your {PRODUCT} demo sign-in code is {spaced}\n\n"
        f"Or open this link: {link}\n\n"
        f"The code and the link work once, for {settings.code_minutes} minutes.\n"
        f"Your first sign-in starts a {settings.trial_days}-day free trial.\n\n"
        "If you did not ask for this, ignore it: nothing happens without the code.\n"
    )
    body = (
        '<div style="font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#111;max-width:480px">'
        f"<p>Your {PRODUCT} demo sign-in code is</p>"
        f'<p style="font:700 30px/1 ui-monospace,Menlo,Consolas,monospace;letter-spacing:.2em;margin:18px 0">{esc(spaced)}</p>'
        f'<p><a href="{esc(link)}" style="display:inline-block;background:#FFA726;color:#111;padding:11px 16px;'
        'border-radius:4px;text-decoration:none;font-weight:700">Open the demo</a></p>'
        f'<p style="color:#555;font-size:13px">The code and the link work once, for {settings.code_minutes} minutes. '
        f"Your first sign-in starts a {settings.trial_days}-day free trial. If you did not ask for this, ignore it.</p>"
        "</div>"
    )
    return Mail(to=to, subject=f"{spaced} is your {PRODUCT} demo code", text=text, html=body)


def ended_mail(settings: AccessSettings, *, to: str, visitor: Visitor) -> Mail:
    if visitor.revoked_at:
        line = "Demo access for this address has been switched off."
    else:
        line = f"The {settings.trial_days}-day free trial for this address ended on {fmt_date(visitor.expires_at)}."
    text = (
        f"Someone asked to sign in to the {PRODUCT} demo with this address.\n\n{line}\n\n"
        f"If you would like more time, reply to {settings.contact_email}.\n"
    )
    body = (
        '<div style="font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#111;max-width:480px">'
        f"<p>Someone asked to sign in to the {PRODUCT} demo with this address.</p><p>{esc(line)}</p>"
        f'<p>If you would like more time, write to <a href="mailto:{esc(settings.contact_email)}">{esc(settings.contact_email)}</a>.</p>'
        "</div>"
    )
    return Mail(to=to, subject=f"Your {PRODUCT} demo trial", text=text, html=body)
