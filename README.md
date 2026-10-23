# Structured JSON Logging for Python

A small, dependency-free logging module that turns Python's built-in `logging` into a
production-style pipeline for services, scheduled jobs and data pipelines.

**At a glance**

- Every event is **one line of JSON** with real, queryable fields instead of free-text sentences
- Written to **stdout** and a **rotating log file** at the same time, each with its own level
- Constant context (`service`, `environment`) is stamped on every event automatically
- **Uncaught exceptions**, in the main thread and in worker threads, are logged as `CRITICAL`
  instead of vanishing into stderr, and the process still exits with a failure code
- Timestamps are **UTC, ISO 8601**, so logs from different machines line up
- Standard library only. `pandas` is needed just for the analysis script

Built as part of the MCD Challenge D Protocol (Day 35).

## Contents

1. [Why this exists](#why-this-exists)
2. [Where it applies](#where-it-applies)
3. [Quick start](#quick-start)
4. [Usage patterns](#usage-patterns)
5. [The log format](#the-log-format)
6. [Configuration reference](#configuration-reference)
7. [How it works](#how-it-works)
8. [Operating it](#operating-it)
9. [Security, privacy and compliance](#security-privacy-and-compliance)
10. [Limits](#limits)
11. [Troubleshooting](#troubleshooting)
12. [Project layout and demo](#project-layout-and-demo)
13. [Roadmap](#roadmap)
14. [Requirements and author](#requirements-and-author)

## Why this exists

Imagine five branches submitting their day's sales at 21:00 and one manager phones to say
"my submission failed". With ordinary logging you have a line like `ERROR Commit failed`.
Which branch? Which sale? Did the retry work? And if the program crashed outright, the
traceback went to a terminal nobody was watching and never reached the log file.

`baseline.py` reproduces exactly that, using plain `logging.basicConfig`. This module fixes
each problem it shows:

| Problem with plain logging | What this module does |
|---|---|
| The facts (branch, transaction) are buried inside a sentence | They are separate JSON fields you can filter and count |
| A traceback spans many lines, so one event looks like six | The traceback is a string field with escaped newlines: one event, one line |
| Timestamps are local time with a comma (`11:39:16,001`) | UTC ISO 8601 (`2026-10-22T09:09:00.706+00:00`) |
| An uncaught crash prints to stderr and never reaches the log file | `sys.excepthook` and `threading.excepthook` route it into the same JSON stream as `CRITICAL` |
| `FileHandler` grows forever until the disk fills | `RotatingFileHandler` caps total size |

With structured logs, the phone call becomes a filter: `branch == "Eldoret"` between 21:00
and 21:10 shows a `503` from a locked database followed 29 seconds later by the same
`transaction_id` saved successfully. A transient problem that healed itself, answered in a
minute.

## Where it applies

Logging is not specific to one business. Anything that runs without a person watching it
needs a trustworthy record of what it did. Structured (JSON) logging is the common format
because it can be searched, counted and alerted on by machines, not just read by people.

### By sector

| Sector | Typical events worth logging | What structured logs give you | Take care with |
|---|---|---|---|
| Retail and e-commerce | POS-to-head-office syncs, stock updates, order and refund events, failed payments | Trace one sale across branches; spot the branch with repeated duplicates or timeouts | Customer names and phone numbers |
| Fintech and mobile money | Payment callbacks, reconciliation runs, retried or duplicate transactions | Show exactly what happened to a transaction; find retries and timeouts fast | PINs, card numbers and full account details must never be logged; mask phone numbers |
| Banking, SACCOs, microfinance | Loan and interest batch jobs, statement generation, account access | An audit trail of what ran, when, and with what outcome | Strict access control and retention rules for the logs themselves |
| Logistics and supply chain | Scan events, driver-app syncs, route calculations, delivery confirmations | Follow a parcel or a driver's sync history end to end | Location data is personal data |
| Agriculture and agritech | Price-feed ingestion, field-gateway readings, farmer-registration batches | Data-quality events (rejected rows, late feeds) become countable | Farmer personal data |
| Healthcare | Integration jobs between systems, access to patient records | Who touched what, and when | Log record identifiers, never clinical content |
| Telecoms and utilities | High-volume event and billing-record processing | Volume is where rotation and a central aggregator matter most | Volume and subscriber data |
| Education and public sector | Registration systems, results processing, e-services | Incident review and accountability | Personal data of students and citizens |
| SaaS and start-ups | API requests, background jobs, billing events | Debug production without logging into servers | Log storage cost grows with traffic |
| Data engineering and analytics | ETL/ELT runs, data-quality checks, scheduled reports, file-ingestion pipelines | Job-level visibility; the logs themselves are a dataset you can query with pandas or SQL | Per-row logging (log per batch instead) |

### By role inside an organisation

- **Backend developers** debug production issues from evidence instead of guesses
- **Data engineers** monitor pipelines and see which job failed, on which file, and why
- **DevOps and SRE teams** build alerts ("more than 5 errors in a minute") on top of the fields
- **Support and operations staff** trace a customer's or branch's complaint to the exact event
- **Security and compliance teams** use logs as an audit trail
- **Analysts and managers** count failures, retries and slow jobs over time

### By kind of system

Web APIs, background workers, scheduled jobs (Windows Task Scheduler, cron), file watchers and
ingestion pipelines, command-line tools, internal utilities, and gateway scripts at the edge.

### By scale, and where this module fits

| Scale | Approach |
|---|---|
| One script, service or machine | **This module's sweet spot.** JSON to stdout plus a rotating file on disk |
| Containers or several services | Write JSON to stdout and let the platform collect it |
| Many machines | Ship the JSON to a central platform: Elasticsearch/OpenSearch with Kibana, Grafana Loki, Datadog, Splunk, AWS CloudWatch Logs, Google Cloud Logging or Azure Monitor. All of these can parse JSON logs. A shipper such as Filebeat, Fluent Bit or Promtail tails the files |

This module does not ship logs anywhere. It produces the **format and files** those tools
expect. It is sized for small services, jobs and internal tools, and for learning how the
pieces fit together. For a large system, adopt a maintained library such as `structlog` or
`python-json-logger` (and consider OpenTelemetry for traces and metrics) on top of a central
platform. The concepts here carry over directly.

## Quick start

```
conda create -n logging-lab python=3.11 pandas -y
conda activate logging-lab
python demo.py
python analyze_logs.py
```

To use it in your own project, copy `app_logging.py` next to your code and call
`setup_logging()` once at startup (see below).

## Usage patterns

### A script or scheduled job

```python
import logging
from app_logging import setup_logging

setup_logging(service="nightly_import", environment="production")
logger = logging.getLogger("nightly_import")

logger.info("Import started", extra={"file": "sales_data.csv"})
logger.info("Import finished", extra={"file": "sales_data.csv", "rows": 3699})
```

Call `setup_logging()` **once**, at program start. Everything you log afterwards, from any
module, goes through the same two handlers.

### Handled errors

```python
try:
    save_sale(sale)
except Exception:
    logger.exception("Failed to save sale",
                     extra={"branch": sale.branch, "transaction_id": sale.transaction_id})
```

`logger.exception` logs at `ERROR` and attaches the traceback as the `exception` field. Use it
inside an `except` block, and log the error **once**, where you handle it, not at every layer.

### Uncaught crashes

Nothing to write. `setup_logging()` installs the hooks, so a crash like this:

```python
raise RuntimeError("Unhandled crash")
```

is logged as `CRITICAL` (logger name `uncaught`) with the full traceback, and the process
still exits with code 1, so a scheduler or CI job still sees a failure. `Ctrl+C` is left alone.
A crash inside a worker thread is logged the same way, with a `thread_name` field.

### A FastAPI service

```python
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app_logging import setup_logging

setup_logging(service="sales_api", environment="production")
logger = logging.getLogger("sales_api.api")

app = FastAPI()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error",
                     extra={"path": request.url.path, "method": request.method})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.post("/sales", status_code=201)
async def create_sale(sale: SaleIn):  # SaleIn: your Pydantic model, defined elsewhere
    logger.info("Sale received",
                extra={"branch": sale.branch, "transaction_id": sale.transaction_id})
    return {"status": "saved"}
```

This pattern was checked with FastAPI's `TestClient`: the endpoint's events appear as JSON with
`service` and `environment` attached, and an unhandled error is logged with its exception block
while the client receives a clean `500`. Two things to know when running it under **uvicorn**:
uvicorn keeps its own server and access logs in its own plain-text format (they are not
captured by this setup), and for an unhandled error it will additionally print its own
traceback.

### A file watcher or ingestion pipeline

Replace ad-hoc `print` or helper-function logging with structured events:

```python
logger = logging.getLogger("file_watcher")
logger.info("Routed file", extra={"source": file_path.name, "destination": str(dest_path)})
logger.warning("File locked, will retry next poll", extra={"source": file_path.name})
```

## The log format

One event per line, for example (wrapped here for reading):

```json
{"timestamp": "2026-10-22T09:37:46.107+00:00", "level": "ERROR", "logger": "sales_api.demo",
 "message": "Failed to save sale", "module": "demo", "function": "submit_sale", "line": 47,
 "branch": "Eldoret", "transaction_id": "TXN-1003", "service": "sales_api",
 "environment": "demo", "exception": {"type": "DatabaseLocked",
 "message": "database is locked", "traceback": "Traceback (most recent call last):\n ..."}}
```

| Field | Meaning |
|---|---|
| `timestamp` | When the event happened. UTC, ISO 8601, millisecond precision. Nairobi is UTC+3, so `18:03Z` is `21:03` local |
| `level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` |
| `logger` | The logger's dotted name, for example `sales_api.db` |
| `message` | A short human-readable summary |
| `module`, `function`, `line` | Where in the code the event was logged |
| `service`, `environment` | Constant context added by `setup_logging` |
| *any `extra` key* | Becomes a top-level field (`branch`, `transaction_id`, ...) |
| `exception` | Only present when an exception is attached: `type`, `message`, `traceback` |
| `thread_name` | Only on uncaught crashes inside a worker thread |

**Naming conventions that keep logs queryable:** use `snake_case`, use the *same* name for the
same thing everywhere (`branch`, never `Branch` or `shop`), log identifiers rather than free
text, and keep the message constant while the variable parts go into fields.

## Configuration reference

`setup_logging(...)` parameters:

| Parameter | Default | Meaning |
|---|---|---|
| `log_dir` | `logs/` next to `app_logging.py` | Folder for the log files |
| `log_name` | `"app.log"` | Name of the current log file |
| `console_level` | `logging.INFO` | Minimum level printed to stdout |
| `file_level` | `logging.DEBUG` | Minimum level written to the file |
| `max_bytes` | `1_000_000` | Size at which the file rotates |
| `backup_count` | `5` | How many rotated files to keep |
| `service` | `"sales_api"` | Value of the `service` field. Change it per application |
| `environment` | `"development"` | Value of the `environment` field |
| `capture_uncaught` | `True` | Install the crash hooks |

## How it works

```
logger.error("Commit failed", extra={...})
        |
        v
  Logger (name + level gate)  -->  LogRecord created
        |
        v
  Handler level gate, then Filter (adds service / environment)
        |
        +--> StreamHandler(stdout)          + JsonFormatter --> console
        +--> RotatingFileHandler(app.log)   + JsonFormatter --> app.log, app.log.1, ...
```

| Piece | What it does |
|---|---|
| `JsonFormatter` | Turns one `LogRecord` into one JSON line. Any attribute on the record that a plain `LogRecord` does not have must have come from `extra`, so it is copied in as a field. `default=str` means an unusual value (a date, a decimal) can never crash a logging call |
| `ContextFilter` | Adds `service` and `environment`. A value passed per call via `extra` wins. It is attached to the **handlers**, not to a logger, because a filter on a logger skips records that propagate up from child loggers |
| `setup_logging()` | Configures the **root** logger once, so every logger in the program feeds the same handlers. It closes and removes old handlers first, so calling it twice never duplicates lines and never leaves a stale file handle (which matters on Windows) |
| `install_exception_hooks()` | Replaces `sys.excepthook` and `threading.excepthook`. It logs, then lets the process fail as it normally would |

Design decisions worth stating:

- **Two level gates.** The logger and each handler have their own level. By default the console
  stays quiet at `INFO` while the file keeps `DEBUG` detail.
- **stdout, explicitly.** `StreamHandler()` writes to stderr by default. Containers and log
  collectors expect stdout.
- **One event, one line.** `json.dumps` escapes newlines, so tracebacks cannot split an event.
- **Intercept, do not swallow.** A crash is logged but not hidden: exit code `1` is preserved.
- **File paths anchored to the module**, not the current directory, so the module behaves the
  same whichever folder you launch from.

## Operating it

### Levels

| Level | Use it for | Example |
|---|---|---|
| `DEBUG` | Diagnostic detail, normally off in production | "Validating payload" |
| `INFO` | Normal business events | "Sale saved" |
| `WARNING` | Unexpected but handled | "Duplicate sale rejected", a retry |
| `ERROR` | An operation failed | "Failed to save sale" |
| `CRITICAL` | The program cannot continue | An uncaught crash |

### Rotation and sizing

Total disk use is capped at roughly `max_bytes x (backup_count + 1)`. The sample logs in this
project average about **300 bytes per event**, so the defaults (1 MB, 5 backups, about 6 MB)
hold roughly **20,000 events**. At 100,000 events a day you would produce about 30 MB a day,
so size the limits to the retention you need, or ship the files to long-term storage.
Rotation deletes the oldest file once `backup_count` is exceeded.

Remember: `backup_count=0` or `max_bytes=0` means **never rotate**.

### Reading the logs

On Windows, simple text search works because each event is a single line:

```
findstr "Eldoret" logs\app.log
findstr ERROR logs\app.log
```

With [`jq`](https://jqlang.org) (a separate install):

```
jq 'select(.level == "ERROR" and .branch == "Eldoret")' logs/app.log
```

With pandas, where the logs become a table you can group and chart:

```python
import pandas as pd

df = pd.read_json("logs/app.log", lines=True)
df[df["level"] == "ERROR"].groupby("branch").size()
```

`analyze_logs.py` does this across the rotated files and prints counts by level, problems by
branch, and exception types.

### Shipping to a log platform

For several machines, point a log shipper at the files (or collect stdout from your
containers) and send them to your platform of choice. Because the events are already JSON, the
platform can index `branch`, `transaction_id` or `level` directly, and you can alert on them.

## Security, privacy and compliance

- **Log identifiers, not secrets.** Never log passwords, tokens, PINs, card numbers or full
  payment payloads. Mask phone numbers:

  ```python
  def mask_phone(phone: str) -> str:
      return phone[:4] + "*" * (len(phone) - 7) + phone[-3:]

  mask_phone("+254712345678")   # '+254******678'
  ```

- **Treat logs as sensitive data.** They get copied, shipped and backed up long after you
  forget them. Restrict who can read the files, and do not commit live logs to Git (this
  project's `.gitignore` excludes `logs/`; `sample_logs/` contains only simulated data).
- **Log forging is blunted.** Because values are JSON-encoded, a user-supplied string containing
  a newline or a fake `{"level": ...}` stays inside its own field and cannot forge an extra
  log line. This was tested.
- **Regulation.** Customer details are personal data. In Kenya the Data Protection Act, 2019
  applies, and data minimisation means logging only what you need. Payment-card rules (PCI DSS)
  forbid storing sensitive card data in logs, and frameworks such as ISO 27001 and SOC 2
  expect logging, monitoring and protection of the logs themselves. This is general guidance,
  not legal advice: check the rules that apply to your sector.

## Limits

- **One process per log file.** Rotation is not safe when several processes write the same
  file, and on Windows the rollover rename can fail with `PermissionError`. Use a single
  writer, or ship stdout to a log platform.
- **Logging is synchronous.** Each call writes on the calling thread. For busy async servers,
  move the writing to a background thread with `QueueHandler` and `QueueListener`.
- **Third-party libraries appear in your stream.** Handlers are on the root logger, so
  libraries that use `logging` (for example `httpx`) show up as JSON too. Quiet a noisy one
  with `logging.getLogger("httpx").setLevel(logging.WARNING)`.
- **Global hooks.** `capture_uncaught=True` replaces `sys.excepthook` for the whole process.
  Pass `capture_uncaught=False` if another tool already owns it.
- **Scope of the crash hooks.** They apply to scripts run with `python file.py`. Notebooks and
  frameworks such as uvicorn have their own exception handling and loggers.
- **Hand-built for learning.** The module is small enough to read in one sitting, which is the
  point, but it has no automated test suite yet (see the roadmap).

## Troubleshooting

These are the real problems met while building this module.

| Symptom | Cause | Fix |
|---|---|---|
| `ImportError: cannot import name 'setup_logging'` | Python is importing a different or stale copy of the module | Run `python -c "import app_logging; print(app_logging.__file__)"` to see which file loads. Keep exactly one `app_logging.py` |
| A block starting `--- Logging error ---` | An exception happened *inside* the formatter or handler. Logging prints it instead of crashing your app | Read the **last line of the traceback above `Call stack:`**. It names the real error, such as a typo in a keyword argument |
| Every line appears twice | Handlers were attached more than once | Call `setup_logging()` once, and do not also add handlers to child loggers |
| The log file never rotates | `backup_count` or `max_bytes` is `0` | Set both to positive numbers |
| `KeyError: "Attempt to overwrite 'filename' in LogRecord"` | An `extra` key clashes with a reserved `LogRecord` attribute (`name`, `message`, `module`, `filename`, `args`, `msg`, `lineno`, ...) | Rename the key (`file`, not `filename`). The error only fires when that level is enabled, so it can hide until DEBUG is switched on |
| A crash prints a raw traceback and is missing from the file | `capture_uncaught=False`, or you are in a notebook or framework | Enable the hooks, or log in the framework's own error handler |
| The console shows no DEBUG lines | `console_level` defaults to `INFO` | By design. The file still has them. Lower `console_level` if you want them printed |
| Files are not where you expect | `log_dir` was changed, or you expected the current folder | By default logs go in `logs/` next to `app_logging.py`. Pass `log_dir` to choose |
| Running from VS Code uses the wrong Python | The play button ignores your conda environment | Select the interpreter, and run from a terminal that shows `(logging-lab)` |

## Project layout and demo

```
app_logging.py    the module: JsonFormatter, ContextFilter, install_exception_hooks, setup_logging
demo.py           simulates a branch submission window and writes sample logs (with rotation)
analyze_logs.py   reads the JSON logs back with pandas
baseline.py       the "before": plain basicConfig logging and what is wrong with it
sample_logs/      output of demo.py: app.log plus rotated app.log.1 ... app.log.N
```

`demo.py` simulates 80 sale submissions across five branches (saved, duplicate, database
lock) plus a worker thread that crashes. The console is set to `WARNING`, so it stays quiet,
while the file keeps everything down to `DEBUG`. A deliberately small `max_bytes` forces
rotation so you can watch `app.log.1`, `app.log.2` and so on appear.

Example `analyze_logs.py` output (exact numbers can vary slightly between Python versions):

```
162 events across 5 files

Events by level
DEBUG       80
INFO        66
WARNING      9
ERROR        6
CRITICAL     1

Problems by branch (WARNING and above)
level    CRITICAL  ERROR  WARNING
branch
(none)          1      0        0
Eldoret         0      1        1
Kisumu          0      2        1
Mombasa         0      1        3
Nairobi         0      1        2
Nakuru          0      1        2

Exception types
DatabaseLocked    6
RuntimeError      1
```

The `(none)` row is the worker-thread crash, which has no branch. The point of the exercise:
because every line is JSON, "which branch has the most duplicate submissions?" is a one-line
pandas query instead of a search through sentences.

## Roadmap

Not implemented yet, in rough order of value:

1. **Automated tests** with `pytest` (including `caplog`) for the formatter, filter and hooks
2. **Correlation IDs** (a request or job id on every event) using `contextvars`, so one request
   can be followed across functions and async tasks
3. **A redaction filter** that masks sensitive fields automatically
4. **Non-blocking writes** with `QueueHandler` and `QueueListener` for busy async services
5. **Daily rotation** with `TimedRotatingFileHandler` as an alternative to size-based rotation
6. **Unified uvicorn logs**, so the server and access logs join the same JSON stream
7. **Packaging** as an installable package, and a worked example of shipping logs to a platform

## Requirements and author

- Python 3.8 or newer (`threading.excepthook`). The module itself uses only the standard library
- `pandas` for `analyze_logs.py`
- Developed on Windows with Anaconda and VS Code; the FastAPI pattern was checked with
  FastAPI's `TestClient`

**Author:** Musa ([@muva8496](https://github.com/muva8496))