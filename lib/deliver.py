"""Getting a sitrep off the laptop, without leaving your password lying about.

TWO CHANNELS, BOTH BRING-YOUR-OWN.

This project is public and free, so it cannot ship an API key for a mail
service -- there is no "our server" to send through, and there should not be.
Every user brings their own credentials, which is more setup and is also the
only arrangement where nobody in the middle is reading your car's data because
we introduced them to it.

  smtp   your own mail server. Gmail with an app password, Fastmail, a box you
         run. Nothing but your own mail provider ever sees the message.
  ntfy   a push notification to a phone. Self-hostable, and the default public
         server is fine for the redacted summary, which is the point of the
         summary being the default.

WHERE THE PASSWORD LIVES, AND WHY NOT IN THE CONFIG.

omacar-sitrep.json is an ordinary config file. It gets read by the app, copied
into bug reports, and committed by somebody who did not think about it. So the
password is NOT in it and this module will not read one from it.

It comes from the environment, or from a separate secret file that must be
mode 0600. If that file is readable by anybody else, sending is REFUSED rather
than done insecurely -- a warning would be ignored, and the whole point of the
check is the case where somebody has not thought about permissions at all.

Nothing here logs a credential, and errors are reported without the password
even when the server includes it in a rejection message.
"""

import json
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage

SECRETS = os.path.join(os.path.expanduser(
    os.environ.get("XDG_CONFIG_HOME", "~/.config")),
    "omarchy", "omacar-sitrep.secret")

TIMEOUT = 20


class Refused(Exception):
    """Sending was not attempted, and the message says why in plain words."""


def _secret_file():
    """The secrets blob, or {} -- refusing outright if it is world-readable."""
    try:
        st = os.stat(SECRETS)
    except OSError:
        return {}
    if st.st_mode & 0o077:
        raise Refused(
            f"{SECRETS} is readable by other users (mode "
            f"{st.st_mode & 0o777:o}). Run: chmod 600 {SECRETS}")
    try:
        with open(SECRETS, encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def secret(name, env):
    """A credential, from the environment first, then the 0600 file."""
    v = os.environ.get(env)
    if v:
        return v
    return str(_secret_file().get(name) or "") or None


def _scrub(text, *creds):
    """An error message with any credential that leaked into it removed.

    Mail servers quote the login in rejections often enough that this is not
    theoretical, and an error string ends up in logs and bug reports.
    """
    s = str(text)
    for c in creds:
        if c and len(c) >= 4:
            s = s.replace(c, "***")
    return s


# ------------------------------------------------------------------- smtp

def send_smtp(channel, subject, body):
    host = str(channel.get("host") or "").strip()
    port = int(channel.get("port") or 587)
    user = str(channel.get("user") or "").strip()
    to = channel.get("to")
    to = [to] if isinstance(to, str) else list(to or [])
    sender = str(channel.get("from") or user or "").strip()
    if not host or not to or not sender:
        raise Refused("smtp channel needs host, from and to")

    password = secret("smtp_password", "OMACAR_SMTP_PASSWORD")
    if user and not password:
        raise Refused(
            "no SMTP password. Set OMACAR_SMTP_PASSWORD, or put "
            f'{{"smtp_password": "..."}} in {SECRETS} with chmod 600.')

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    # A sitrep is a notification, not correspondence. Marking it as such keeps
    # it out of vacation responders and, more usefully, out of other people's
    # spam heuristics for unattended daily mail.
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(body)

    try:
        if port == 465:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, timeout=TIMEOUT,
                                  context=ctx) as s:
                if user:
                    s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=TIMEOUT) as s:
                s.ehlo()
                if s.has_extn("starttls"):
                    s.starttls(context=ssl.create_default_context())
                    s.ehlo()
                elif user:
                    # Refusing to send a password over a cleartext link is the
                    # one place this module is deliberately unhelpful.
                    raise Refused(
                        f"{host}:{port} offers no STARTTLS and a password was "
                        "given; refusing to send credentials in the clear.")
                if user:
                    s.login(user, password)
                s.send_message(msg)
    except Refused:
        raise
    except (smtplib.SMTPException, OSError) as e:
        raise Refused("smtp: " + _scrub(e, password, user)) from None
    return {"channel": "smtp", "to": to, "host": host}


# ------------------------------------------------------------------- ntfy

def send_ntfy(channel, subject, body):
    url = str(channel.get("url") or "").strip()
    if not url:
        topic = str(channel.get("topic") or "").strip()
        if not topic:
            raise Refused("ntfy channel needs url or topic")
        url = "https://ntfy.sh/" + topic

    token = secret("ntfy_token", "OMACAR_NTFY_TOKEN")
    data = body.encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    # Latin-1 because these are HTTP header values; a degree sign in a title
    # would otherwise raise on send rather than on a screen somebody can see.
    req.add_header("Title", subject.encode("utf-8").decode("latin-1", "replace"))
    req.add_header("Tags", "car")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            r.read()
    except (urllib.error.URLError, OSError) as e:
        raise Refused("ntfy: " + _scrub(e, token)) from None
    return {"channel": "ntfy", "url": url.split("?")[0]}


SENDERS = {"smtp": send_smtp, "ntfy": send_ntfy}


def send(subject, body, channels):
    """Send to every configured channel. One failing does not stop the rest.

    Returns a list of results, each either {"ok": True, ...} or
    {"ok": False, "error": "..."} -- because a sitrep that reached the phone
    but not the inbox is a partial success worth recording as one, and because
    the caller files the outcome either way.
    """
    out = []
    for ch in (channels or []):
        if not isinstance(ch, dict):
            continue
        kind = str(ch.get("kind") or "").lower()
        fn = SENDERS.get(kind)
        if not fn:
            out.append({"ok": False, "channel": kind or "?",
                        "error": f"no such channel kind: {kind or '(none)'}"})
            continue
        if ch.get("enabled") is False:
            continue
        try:
            res = fn(ch, subject, body)
            res["ok"] = True
            out.append(res)
        except Refused as e:
            out.append({"ok": False, "channel": kind, "error": str(e)})
        except Exception as e:  # a transport must never take the daemon down
            out.append({"ok": False, "channel": kind,
                        "error": f"{type(e).__name__}: {_scrub(e)}"})
    return out
