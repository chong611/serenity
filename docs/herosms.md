# HeroSMS CLI — kimi.com registration numbers

`scripts/herosms.py` is a single-file, standard-library-only command line tool
for [HeroSMS](https://hero-sms.com/). HeroSMS speaks the SMS-Activate
`handler_api.php` protocol, so the tool needs no extra dependencies.

Use it to **find a virtual number under $0.15, buy it, and receive the SMS
verification code** while signing up for kimi.com (or any other service).

## 1. Set your API key (it is a secret — never commit it)

The tool reads the key from, in priority order:

1. `--api-key` on the command line (avoid — visible in shell history)
2. the `HEROSMS_API_KEY` environment variable **(recommended)**
3. a key file: `--key-file PATH`, or `./.herosms.key`, or `~/.herosms.key`

```bash
export HEROSMS_API_KEY=your_api_key_here
python3 scripts/herosms.py balance
```

`.herosms.key` and `herosms.key` are already in `.gitignore`, so a local key
file will not be committed by accident.

## 2. Find the service code for kimi

HeroSMS does not publish a fixed code for kimi, and it can differ per account,
so **discover it** instead of guessing:

```bash
python3 scripts/herosms.py services --search kimi
# if nothing matches, try the vendor name:
python3 scripts/herosms.py services --search moonshot
# or browse the whole list:
python3 scripts/herosms.py services | less
```

The left column is the code you pass to `--service` below (e.g. `kimi`).

## 3. Find a number below $0.15

```bash
python3 scripts/herosms.py prices --service kimi --max 0.15
```

Example output (cheapest first, only in-stock numbers within budget):

```
   COST   STOCK   CID  COUNTRY
  0.090      42     0  Russia
  0.130       5     6  Indonesia

Cheapest: Russia (country id 0) at 0.090. Buy it with:
  python3 scripts/herosms.py order --service kimi --country 0 --max 0.15
```

`COST` is in your account currency (USD on HeroSMS). `CID` is the country id
you pass to `--country`. `--max` defaults to `0.15`; pass `--max -1` to show
every price.

## 4a. One-shot guided flow (recommended)

`register` buys the cheapest in-budget number, prints it, waits for the SMS
code, and — if no code arrives before `--timeout` — **cancels for a refund**
automatically:

```bash
python3 scripts/herosms.py register --service kimi --max 0.15
```

```
Balance: 12.34
────────────────────────────────────────────────
  Phone number : 79001112233
  Activation id: 987654321
────────────────────────────────────────────────
→ Enter this phone number on kimi.com and request the SMS code.
  Waiting for the code to arrive…

✅ SMS code: 445566
```

Enter the phone number on kimi.com's signup page, request the code, and the
tool prints it as soon as it arrives. Pin a country with `--country <id>`, add
`--complete` to auto-finalize once the code lands, or `--keep` to leave the
activation open on timeout instead of refunding.

## 4b. Step by step (full control)

```bash
# buy a number (spends money; capped at --max, default 0.15)
python3 scripts/herosms.py order --service kimi --country 0 --max 0.15
#   -> activation id: 987654321 / phone: 79001112233

# poll for the code (blocks until it arrives or --timeout elapses)
python3 scripts/herosms.py code --id 987654321 --wait

# after kimi.com accepts the code, finalize:
python3 scripts/herosms.py done --id 987654321
#   ...or if no SMS came, get your money back:
python3 scripts/herosms.py cancel --id 987654321
```

## Command reference

| Command | What it does |
|---|---|
| `balance` | Show account balance. |
| `services [--search TEXT]` | List/search service codes (find `kimi`). |
| `countries [--search TEXT]` | List/search country ids. |
| `prices --service S [--max N] [--country ID] [--top N]` | Cheapest in-stock numbers within budget. |
| `order --service S [--country ID] [--max N] [--operator OP]` | Buy a number. |
| `code --id ID [--wait] [--timeout S] [--interval S]` | Poll for the SMS code. |
| `ready --id ID` | Tell HeroSMS the number was submitted (status 1). |
| `resend --id ID` | Request another SMS (status 3). |
| `done --id ID` | Complete the activation (status 6). |
| `cancel --id ID` | Cancel & refund (status 8). |
| `activations` | List active activations. |
| `register --service S [...]` | Guided: buy cheapest in-budget number + wait for code. |

Global flags: `--json` (machine-readable output), `--api-key`, `--key-file`,
`--base-url`, `--http-timeout`.

## Notes & safety

- **Money:** `order` and `register` spend real balance. Both cap the price at
  `--max` (default `$0.15`), so a purchase fails with `WRONG_MAX_PRICE` rather
  than overspending. `register` auto-cancels for a refund if no SMS arrives in
  time. Refunds are only possible inside HeroSMS's free-cancel window.
- **Cancellation window:** a very fast `cancel` can return `EARLY_CANCEL_DENIED`
  (HeroSMS enforces a short minimum hold). Wait a few seconds and retry.
- **Respect terms of service.** Use this only for accounts you are allowed to
  create; do not use it for bulk or abusive registration.
- This tool is standalone and does not touch the Serenity dashboard data.
