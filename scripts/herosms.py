#!/usr/bin/env python3
"""HeroSMS CLI — buy virtual numbers, find cheap ones, and receive SMS codes.

HeroSMS speaks the SMS-Activate ``handler_api.php`` protocol, so this single
file talks to it with nothing but the Python standard library.

Docs: https://hero-sms.com/api

Typical kimi.com registration workflow::

    # 1. What's the service code for kimi on HeroSMS?  Search for it.
    python3 scripts/herosms.py services --search kimi

    # 2. Find countries whose number for that service costs below $0.15.
    python3 scripts/herosms.py prices --service <code> --max 0.15

    # 3. Do the whole thing: buy the cheapest number, wait for the SMS code.
    python3 scripts/herosms.py register --service <code> --max 0.15

    #    (or drive each step yourself)
    python3 scripts/herosms.py order  --service <code> --max 0.15
    python3 scripts/herosms.py code   --id <activationId> --wait
    python3 scripts/herosms.py done   --id <activationId>     # or: cancel

The API key is a secret and is NEVER read from the command line by default.
Provide it via, in priority order:

    1. --api-key on the command line (avoid; visible in shell history)
    2. HEROSMS_API_KEY environment variable            (recommended)
    3. a key file: --key-file PATH, or ./ .herosms.key, or ~/.herosms.key

Example::

    export HEROSMS_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    python3 scripts/herosms.py balance
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://hero-sms.com/stubs/handler_api.php"
DEFAULT_MAX_PRICE = 0.15  # the user's budget: only consider numbers below this
DEFAULT_TIMEOUT = 300     # seconds to wait for an SMS before giving up
DEFAULT_POLL_INTERVAL = 5  # seconds between getStatus polls

ROOT = Path(__file__).resolve().parents[1]

# setStatus codes (SMS-Activate protocol).
STATUS_READY = 1     # tell the service the number was submitted, await code
STATUS_RETRY = 3     # request another SMS
STATUS_COMPLETE = 6  # finish the activation (code received & accepted)
STATUS_CANCEL = 8    # cancel and refund (only within the free window)

# Non-error markers the API returns as the first colon-separated token.
_OK_PREFIXES = ("ACCESS_", "STATUS_", "TZ_", "FULL_")

# Error tokens the handler_api endpoint can return instead of a payload.
_ERROR_TOKENS = {
    "BAD_ACTION", "BAD_KEY", "NO_KEY", "BANNED", "ACCOUNT_INACTIVE",
    "BAD_SERVICE", "WRONG_SERVICE", "BAD_STATUS", "WRONG_COUNTRY",
    "BAD_DURATION", "WRONG_CURRENCY", "NO_NUMBERS", "NO_BALANCE",
    "NO_ACTIVATION", "SERVICE_NOT_AVAILABLE", "SIM_OFFLINE",
    "OPERATORS_NOT_FOUND", "WRONG_ACTIVATION_ID", "WRONG_MAX_PRICE",
    "UNPROCESSABLE_ENTITY", "ORDER_ALREADY_EXISTS", "EARLY_CANCEL_DENIED",
    "FREE_CANCELLATION_EXPIRED", "ACTIVATION_NOT_ACTIVE", "ERROR_SQL",
    "CHANNELS_LIMIT", "NOT_FOUND", "SERVER_ERROR", "BAD_REQUEST",
}

_ERROR_HELP = {
    "BAD_KEY": "The API key was rejected. Check HEROSMS_API_KEY / --api-key.",
    "NO_KEY": "No API key was sent. Set HEROSMS_API_KEY or pass --api-key.",
    "NO_BALANCE": "Account balance is too low to buy a number. Top up first.",
    "NO_NUMBERS": "No numbers are currently in stock for that service/country "
                  "at that price. Try a different country or raise --max.",
    "WRONG_MAX_PRICE": "--max is below the seller's minimum for this number. "
                       "Raise --max or pick a cheaper country.",
    "BAD_SERVICE": "Unknown service code. Run 'services --search <name>' to "
                   "find the right code.",
    "WRONG_COUNTRY": "Unknown country id. Run 'countries' to list them.",
    "BANNED": "This account is banned by HeroSMS.",
    "EARLY_CANCEL_DENIED": "HeroSMS won't let you cancel yet (a short minimum "
                           "hold applies). Wait a bit and retry cancel.",
    "FREE_CANCELLATION_EXPIRED": "The free-cancel window has passed; no refund "
                                 "is available for this activation.",
}


class HeroSMSError(RuntimeError):
    """Raised when the API returns an error token."""

    def __init__(self, token: str, detail: str = ""):
        self.token = token
        help_text = _ERROR_HELP.get(token, "")
        msg = token
        if detail and detail != token:
            msg = f"{token}: {detail}"
        if help_text:
            msg = f"{msg}  ({help_text})"
        super().__init__(msg)


# --------------------------------------------------------------------------- #
# HTTP client
# --------------------------------------------------------------------------- #
class HeroSMS:
    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL,
                 timeout: float = 30.0):
        if not api_key:
            raise HeroSMSError("NO_KEY", "empty api key")
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout

    def _call(self, action: str, **params) -> str:
        query = {"api_key": self.api_key, "action": action}
        for key, value in params.items():
            if value is None:
                continue
            query[key] = value
        url = f"{self.base_url}?{urllib.parse.urlencode(query)}"
        req = urllib.request.Request(url, headers={"User-Agent": "herosms-cli/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", "replace").strip()
        except urllib.error.HTTPError as exc:  # pragma: no cover - network
            raise HeroSMSError("SERVER_ERROR", f"HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:  # pragma: no cover - network
            raise HeroSMSError("SERVER_ERROR", str(exc.reason)) from exc
        self._raise_for_error(body)
        return body

    @staticmethod
    def _raise_for_error(body: str) -> None:
        token = body.split(":", 1)[0].strip()
        if token.startswith(_OK_PREFIXES):
            return
        if token in _ERROR_TOKENS:
            raise HeroSMSError(token, body)

    def _call_json(self, action: str, **params):
        body = self._call(action, **params)
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise HeroSMSError("SERVER_ERROR",
                               f"expected JSON from {action}, got: {body[:200]}") from exc

    # -- read-only endpoints (cost nothing) --------------------------------- #
    def get_balance(self) -> float:
        # "ACCESS_BALANCE:100.00" (some deployments append a currency token)
        body = self._call("getBalance")
        parts = body.split(":")
        try:
            return float(parts[1])
        except (IndexError, ValueError):
            raise HeroSMSError("SERVER_ERROR", f"unparseable balance: {body}")

    def get_countries(self) -> dict:
        return self._call_json("getCountries")

    def get_services_list(self):
        # Newer endpoint; may be absent on some deployments.
        return self._call_json("getServicesList")

    def get_prices(self, service=None, country=None) -> dict:
        return self._call_json("getPrices", service=service, country=country)

    def get_active_activations(self):
        return self._call_json("getActiveActivations")

    # -- money-spending / stateful endpoints -------------------------------- #
    def get_number(self, service: str, country=None, max_price=None,
                   operator=None):
        # "ACCESS_NUMBER:<activationId>:<phone>"
        body = self._call("getNumber", service=service, country=country,
                          maxPrice=max_price, operator=operator)
        parts = body.split(":")
        if len(parts) < 3 or parts[0] != "ACCESS_NUMBER":
            raise HeroSMSError("SERVER_ERROR", f"unexpected getNumber reply: {body}")
        return parts[1], parts[2]  # (activation_id, phone_number)

    def get_status(self, activation_id) -> tuple[str, str | None]:
        # "STATUS_OK:12345" | "STATUS_WAIT_CODE" | "STATUS_WAIT_RETRY:12345" ...
        body = self._call("getStatus", id=activation_id)
        head, _, code = body.partition(":")
        return head, (code or None)

    def set_status(self, activation_id, status: int) -> str:
        return self._call("setStatus", id=activation_id, status=status)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _country_names(client: HeroSMS) -> dict:
    """id(str) -> english name, best effort (returns {} if unavailable)."""
    try:
        data = client.get_countries()
    except HeroSMSError:
        return {}
    names = {}
    if isinstance(data, dict):
        for key, meta in data.items():
            if isinstance(meta, dict):
                names[str(key)] = meta.get("eng") or meta.get("rus") or str(key)
    return names


def _flatten_prices(prices: dict, wanted_service=None):
    """getPrices JSON -> list of dicts {country, service, cost, count}."""
    rows = []
    if not isinstance(prices, dict):
        return rows
    for country_id, services in prices.items():
        if not isinstance(services, dict):
            continue
        for service, info in services.items():
            if wanted_service and service != wanted_service:
                continue
            if isinstance(info, dict):
                cost = info.get("cost")
                count = info.get("count", info.get("quant", 0))
            else:
                cost, count = info, None
            try:
                cost = float(cost)
            except (TypeError, ValueError):
                continue
            rows.append({
                "country": str(country_id),
                "service": service,
                "cost": cost,
                "count": int(count) if count is not None else None,
            })
    return rows


# --------------------------------------------------------------------------- #
# Command implementations
# --------------------------------------------------------------------------- #
def cmd_balance(client: HeroSMS, args) -> int:
    balance = client.get_balance()
    if args.json:
        print(json.dumps({"balance": balance}))
    else:
        print(f"Balance: {balance:.2f}")
    return 0


def cmd_services(client: HeroSMS, args) -> int:
    search = (args.search or "").lower()
    services = []
    try:
        data = client.get_services_list()
        raw = data.get("services", data) if isinstance(data, dict) else data
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            code = item.get("code") or item.get("id") or item.get("service")
            name = item.get("name") or item.get("title") or ""
            if code:
                services.append({"code": str(code), "name": str(name)})
    except HeroSMSError:
        # Fallback: derive available service codes from the price list.
        rows = _flatten_prices(client.get_prices())
        seen = {}
        for row in rows:
            seen.setdefault(row["service"], row["cost"])
        services = [{"code": code, "name": ""} for code in sorted(seen)]

    if search:
        services = [s for s in services
                    if search in s["code"].lower() or search in s["name"].lower()]
    services.sort(key=lambda s: s["code"])

    if args.json:
        print(json.dumps(services, ensure_ascii=False))
        return 0
    if not services:
        hint = f" matching {args.search!r}" if search else ""
        print(f"No services{hint}. If searching for kimi returns nothing, the "
              "code may differ — try 'moonshot', or list all with no --search.")
        return 1
    width = max(len(s["code"]) for s in services)
    for s in services:
        print(f"{s['code']:<{width}}  {s['name']}".rstrip())
    return 0


def cmd_countries(client: HeroSMS, args) -> int:
    names = _country_names(client)
    search = (args.search or "").lower()
    items = sorted(names.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0)
    if search:
        items = [(cid, name) for cid, name in items
                 if search in name.lower() or search == cid]
    if args.json:
        print(json.dumps([{"id": cid, "name": name} for cid, name in items],
                         ensure_ascii=False))
        return 0
    for cid, name in items:
        print(f"{cid:>4}  {name}")
    return 0


def cmd_prices(client: HeroSMS, args) -> int:
    prices = client.get_prices(service=args.service, country=args.country)
    rows = _flatten_prices(prices, wanted_service=args.service)
    # Keep only in-stock numbers within budget.
    rows = [r for r in rows if (r["count"] is None or r["count"] > 0)]
    if args.max is not None:
        rows = [r for r in rows if r["cost"] <= args.max + 1e-9]
    rows.sort(key=lambda r: (r["cost"], -(r["count"] or 0)))
    if args.top:
        rows = rows[: args.top]

    names = {} if args.json else _country_names(client)
    for r in rows:
        r["country_name"] = names.get(r["country"], r["country"])

    if args.json:
        print(json.dumps(rows, ensure_ascii=False))
        return 0
    if not rows:
        budget = f" below {args.max:g}" if args.max is not None else ""
        print(f"No in-stock numbers for service {args.service!r}{budget}. "
              "Try raising --max or a different service code.")
        return 1
    print(f"{'COST':>7}  {'STOCK':>6}  {'CID':>4}  COUNTRY")
    for r in rows:
        stock = "?" if r["count"] is None else r["count"]
        print(f"{r['cost']:>7.3f}  {stock:>6}  {r['country']:>4}  {r['country_name']}")
    print(f"\nCheapest: {rows[0]['country_name']} (country id {rows[0]['country']}) "
          f"at {rows[0]['cost']:.3f}. Buy it with:\n"
          f"  python3 scripts/herosms.py order --service {args.service} "
          f"--country {rows[0]['country']} --max {args.max if args.max is not None else DEFAULT_MAX_PRICE:g}")
    return 0


def cmd_order(client: HeroSMS, args) -> int:
    activation_id, phone = client.get_number(
        service=args.service, country=args.country, max_price=args.max,
        operator=args.operator)
    if args.json:
        print(json.dumps({"activation_id": activation_id, "phone": phone}))
    else:
        print(f"Ordered.  activation id: {activation_id}")
        print(f"Phone number: {phone}")
        print("Enter this number on kimi.com, then run:")
        print(f"  python3 scripts/herosms.py code --id {activation_id} --wait")
    return 0


def _print_code_result(head: str, code: str | None, args, activation_id) -> int:
    if head == "STATUS_OK":
        if args.json:
            print(json.dumps({"status": "OK", "code": code}))
        else:
            print(f"SMS code: {code}")
            print("When kimi.com accepts it, finalize with:")
            print(f"  python3 scripts/herosms.py done --id {activation_id}")
        return 0
    if args.json:
        print(json.dumps({"status": head, "code": code}))
    else:
        print(f"No code yet ({head}).")
    return 2


def cmd_code(client: HeroSMS, args) -> int:
    deadline = time.monotonic() + args.timeout
    while True:
        head, code = client.get_status(args.id)
        if head == "STATUS_OK":
            return _print_code_result(head, code, args, args.id)
        if head == "STATUS_CANCEL":
            if args.json:
                print(json.dumps({"status": "CANCEL", "code": None}))
            else:
                print("Activation was cancelled.")
            return 3
        if not args.wait or time.monotonic() >= deadline:
            return _print_code_result(head, code, args, args.id)
        if not args.json:
            waited = int(time.monotonic() - (deadline - args.timeout))
            print(f"  waiting for SMS… ({head}, {waited}s)", file=sys.stderr)
        time.sleep(args.interval)


def cmd_ready(client: HeroSMS, args) -> int:
    print(client.set_status(args.id, STATUS_READY))
    return 0


def cmd_resend(client: HeroSMS, args) -> int:
    print(client.set_status(args.id, STATUS_RETRY))
    return 0


def cmd_done(client: HeroSMS, args) -> int:
    print(client.set_status(args.id, STATUS_COMPLETE))
    return 0


def cmd_cancel(client: HeroSMS, args) -> int:
    print(client.set_status(args.id, STATUS_CANCEL))
    return 0


def cmd_activations(client: HeroSMS, args) -> int:
    data = client.get_active_activations()
    if args.json:
        print(json.dumps(data, ensure_ascii=False))
        return 0
    activations = data.get("activeActivations", data) if isinstance(data, dict) else data
    if not activations:
        print("No active activations.")
        return 0
    for a in activations:
        if isinstance(a, dict):
            print(f"  id={a.get('activationId', a.get('id', '?'))}  "
                  f"phone={a.get('phoneNumber', '?')}  "
                  f"service={a.get('serviceCode', a.get('service', '?'))}  "
                  f"status={a.get('activationStatus', a.get('status', '?'))}")
        else:
            print(f"  {a}")
    return 0


def cmd_register(client: HeroSMS, args) -> int:
    """Full guided flow: buy the cheapest in-budget number, wait for the code."""
    if not args.json:
        try:
            print(f"Balance: {client.get_balance():.2f}")
        except HeroSMSError:
            pass

    activation_id, phone = client.get_number(
        service=args.service, country=args.country, max_price=args.max,
        operator=args.operator)
    if not args.json:
        print("─" * 48)
        print(f"  Phone number : {phone}")
        print(f"  Activation id: {activation_id}")
        print("─" * 48)
        print("→ Enter this phone number on kimi.com and request the SMS code.")
        print("  Waiting for the code to arrive…")

    deadline = time.monotonic() + args.timeout
    code = None
    head = "STATUS_WAIT_CODE"
    while time.monotonic() < deadline:
        head, code = client.get_status(activation_id)
        if head == "STATUS_OK":
            break
        if head == "STATUS_CANCEL":
            break
        time.sleep(args.interval)

    if head == "STATUS_OK":
        if args.json:
            print(json.dumps({"activation_id": activation_id, "phone": phone,
                              "code": code, "status": "OK"}))
        else:
            print(f"\n✅ SMS code: {code}\n")
            print("Enter it on kimi.com to finish signing up. Then finalize:")
            print(f"  python3 scripts/herosms.py done --id {activation_id}")
        if args.complete:
            client.set_status(activation_id, STATUS_COMPLETE)
        return 0

    # No code arrived (or cancelled): refund by cancelling unless --keep.
    if not args.keep:
        try:
            client.set_status(activation_id, STATUS_CANCEL)
            cancelled = True
        except HeroSMSError:
            cancelled = False
    else:
        cancelled = False
    if args.json:
        print(json.dumps({"activation_id": activation_id, "phone": phone,
                          "code": None, "status": head, "cancelled": cancelled}))
    else:
        print(f"\n⏱  No SMS within {args.timeout}s ({head}).")
        if cancelled:
            print("Activation cancelled and refunded.")
        else:
            print(f"Activation kept open. Keep polling with:\n"
                  f"  python3 scripts/herosms.py code --id {activation_id} --wait\n"
                  f"or cancel for a refund:\n"
                  f"  python3 scripts/herosms.py cancel --id {activation_id}")
    return 2


# --------------------------------------------------------------------------- #
# API-key resolution & argument parsing
# --------------------------------------------------------------------------- #
def resolve_api_key(args) -> str:
    if args.api_key:
        return args.api_key.strip()
    env = os.environ.get("HEROSMS_API_KEY")
    if env:
        return env.strip()
    candidates = []
    if args.key_file:
        candidates.append(Path(args.key_file))
    candidates += [ROOT / ".herosms.key", Path.home() / ".herosms.key"]
    for path in candidates:
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    raise HeroSMSError(
        "NO_KEY",
        "no API key found. Set HEROSMS_API_KEY, pass --api-key, or create "
        "./.herosms.key")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="HeroSMS CLI: buy virtual numbers and receive SMS codes.")
    parser.add_argument("--api-key", help="HeroSMS API key (prefer HEROSMS_API_KEY env)")
    parser.add_argument("--key-file", help="path to a file containing the API key")
    parser.add_argument("--base-url", default=os.environ.get("HEROSMS_BASE_URL", DEFAULT_BASE_URL),
                        help=f"API endpoint (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--http-timeout", type=float, default=30.0,
                        help="per-request HTTP timeout in seconds")
    parser.add_argument("--json", action="store_true", help="machine-readable JSON output")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("balance", help="show account balance").set_defaults(func=cmd_balance)

    p = sub.add_parser("services", help="list/search service codes (find 'kimi')")
    p.add_argument("--search", help="filter services by code or name substring")
    p.set_defaults(func=cmd_services)

    p = sub.add_parser("countries", help="list/search country ids")
    p.add_argument("--search", help="filter by country name or exact id")
    p.set_defaults(func=cmd_countries)

    p = sub.add_parser("prices", help="find in-stock numbers under a price")
    p.add_argument("--service", required=True, help="service code, e.g. from 'services'")
    p.add_argument("--country", help="restrict to one country id")
    p.add_argument("--max", type=float, default=DEFAULT_MAX_PRICE,
                   help=f"max price to include (default {DEFAULT_MAX_PRICE}; use -1 for all)")
    p.add_argument("--top", type=int, default=20, help="show only the N cheapest")
    p.set_defaults(func=cmd_prices)

    p = sub.add_parser("order", help="buy a number (spends money)")
    p.add_argument("--service", required=True)
    p.add_argument("--country", help="country id (omit to let HeroSMS choose)")
    p.add_argument("--max", type=float, default=DEFAULT_MAX_PRICE,
                   help=f"max price you'll pay (default {DEFAULT_MAX_PRICE})")
    p.add_argument("--operator", help="preferred operator (optional)")
    p.set_defaults(func=cmd_order)

    p = sub.add_parser("code", help="poll for the received SMS code")
    p.add_argument("--id", required=True, help="activation id from 'order'")
    p.add_argument("--wait", action="store_true", help="keep polling until code/timeout")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                   help=f"seconds to wait when --wait (default {DEFAULT_TIMEOUT})")
    p.add_argument("--interval", type=int, default=DEFAULT_POLL_INTERVAL,
                   help=f"seconds between polls (default {DEFAULT_POLL_INTERVAL})")
    p.set_defaults(func=cmd_code)

    for name, func, help_text in (
        ("ready", cmd_ready, "tell HeroSMS the number was submitted (status 1)"),
        ("resend", cmd_resend, "request another SMS (status 3)"),
        ("done", cmd_done, "complete the activation (status 6)"),
        ("cancel", cmd_cancel, "cancel & refund the activation (status 8)"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--id", required=True, help="activation id")
        p.set_defaults(func=func)

    sub.add_parser("activations", help="list active activations").set_defaults(func=cmd_activations)

    p = sub.add_parser("register", help="guided: buy cheapest in-budget number + wait for code")
    p.add_argument("--service", required=True, help="service code (e.g. kimi)")
    p.add_argument("--country", help="country id (omit to let HeroSMS choose cheapest)")
    p.add_argument("--max", type=float, default=DEFAULT_MAX_PRICE,
                   help=f"max price you'll pay (default {DEFAULT_MAX_PRICE})")
    p.add_argument("--operator", help="preferred operator (optional)")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                   help=f"seconds to wait for the SMS (default {DEFAULT_TIMEOUT})")
    p.add_argument("--interval", type=int, default=DEFAULT_POLL_INTERVAL,
                   help=f"seconds between polls (default {DEFAULT_POLL_INTERVAL})")
    p.add_argument("--complete", action="store_true",
                   help="auto-complete (status 6) once the code arrives")
    p.add_argument("--keep", action="store_true",
                   help="on timeout, keep the activation instead of refunding")
    p.set_defaults(func=cmd_register)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    # "--max -1" means "no cap".
    if getattr(args, "max", None) is not None and args.max < 0:
        args.max = None
    try:
        api_key = resolve_api_key(args)
        client = HeroSMS(api_key, base_url=args.base_url, timeout=args.http_timeout)
        return args.func(client, args)
    except HeroSMSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
