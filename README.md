# state branch

Data for the memecoin paper bot (`main` holds the code). Only the hot loop writes the books.

- `books/<arm>.json`: one book per arm (`claude` = picks, `control` = random gate pass).
- `orders/`: the inbox. Claude's runs drop order files here; the loop applies them in order and
  moves each to `orders/done/` with its result.
- `book.md`: the report. `health.json`: the loop's last tick and error count.
  `watchdog.json`: the watchdog's alert state.

Paper only: no wallet, no keys, no real orders.
