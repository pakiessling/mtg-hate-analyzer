# MTG Meta Hate Cards

Reports which "hate cards" (defined by you in `_input/hatecards.txt`) show up in
each archetype's maindeck and sideboard, and renders a printer-friendly
single-page PDF.

Data comes from the public [Videre API](https://api.videreproject.com)
(`/archetypes/:format`), which returns aggregated per-archetype card-adoption
stats for any MTGO format.

**📊 Latest report for Modern Amulet Titan (auto-updated weekly): https://pakiessling.github.io/mtg-hate-analyzer/**

## Quick start

```bash
uv sync                                    # install deps
make fetch-hate ARGS="--format modern"     # fetch + build reports (txt + json)
make generate-pdf                          # render the single-page PDF
# ...or both at once:
make videre-report ARGS="--format legacy"
```

Outputs:
- `_output/reports/hate_cards_report_<ts>.txt` — human-readable report
- `_output/reports/hate_cards_<ts>.json` — structured data (drives the PDF)
- `_output/paper/hate_cards_<ts>.pdf` — printable single-page A4 report

### `videre_hate.py` options

| Flag | Default | Meaning |
|---|---|---|
| `--format` | `modern` | MTGO format (`modern`, `legacy`, `pioneer`, `vintage`, …) |
| `--min-date` / `--max-date` | API default (~last 31 days) | Event window `YYYY-MM-DD` |
| `--limit` | `100` | Max archetype rows to fetch |
| `--min-decks` | `5` | Drop archetypes with fewer decklists |
| `--min-pct` | `20` | Hide hate cards run in fewer than this % of the archetype's decks |
| `--hate-file` | `_input/hatecards.txt` | Alternate hate-card list |

### Defining hate cards

Edit `_input/hatecards.txt`. One card name per line; `# section` comments both
document and **categorize** the cards below them (categories become the colored
chips + legend in the PDF):

```text
# graveyard
surgical extraction
leyline of the void
# counters
force of negation
```

### Scheduled runs (GitHub Actions)

`.github/workflows/videre-report.yml` runs weekly (and on manual dispatch),
builds the PDF, and commits it to the `reports` branch. It uses the public API
(no secrets) and stays within GitHub's free Actions minutes.

## Output

The structured JSON (`_output/reports/hate_cards_<ts>.json`) drives the PDF:

```jsonc
{
  "format": "Modern",
  "source": "Videre API /archetypes/modern",
  "window": {"min_date": "2026-06-25", "max_date": "2026-07-26", "days": 31},
  "min_pct": 20,
  "generated": "2026-07-26T14:35:50+00:00",
  "archetypes": [
    {
      "name": "Boros Energy",
      "count": 208,
      "maindeck": [{"name": "Blood Moon", "avg": 1.2, "pct": 73, "category": "land hate"}],
      "sideboard": [{"name": "Damping Sphere", "avg": 1.1, "pct": 25, "category": "land hate"}]
    }
  ]
}
```

Per card: `name`, `avg` (average copies where present), `pct` (% of the
archetype's decks running it), and `category` (from the hate-card file section).

The PDF is a single A4 page: one row per archetype (with deck count), separate
maindeck/sideboard columns, category-colored chips, a legend, and a header
showing the format, analyzed date window, adoption threshold, and generation
time. Font sizes auto-scale to fit one page.

## Requirements

- Python 3.12+ and [uv](https://github.com/astral-sh/uv)
- `requests` — HTTP client for the Videre API
- `weasyprint` — HTML → PDF rendering

**WeasyPrint needs native libraries** to render the PDF (the fetch/report steps
work without them; only `make generate-pdf` needs them):

- **Linux/CI:** `sudo apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev libcairo2` (the GitHub workflow already does this).
- **Windows:** install the [GTK3 runtime](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases) so `libgobject-2.0-0` is on the PATH.
- **macOS:** `brew install pango`.

See the [WeasyPrint install docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html) for details.

## Credits

Inspired by the original [mtgscrap](https://github.com/Thegg53/mtgscrap) project
by Thegg53, which scraped hate-card data from MTGGoldfish. This version reworks
it to source data from the Videre API instead.
