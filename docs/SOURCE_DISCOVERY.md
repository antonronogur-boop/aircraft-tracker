# Source coverage audit & RSS discovery — 2026-11-08

Method: coverage audit first (`scripts/coverage_audit.py`), then feed discovery for the gap countries' official sources (`scripts/source_discovery.py`, read-only), then targeted additions (`config/source_expansion.json` → `scripts/add_sources.py`). RSS/Atom preferred, not mandatory.

## Coverage (60 days to 2026-11-02, W45 corpus)

| Group | ADEQUATE | PARTIAL | GAP |
|---|---|---|---|
| Immediate region (17) | Ukraine, Poland | Hungary, Russia, Romania, Czechia, Lithuania | Serbia, Belarus, Bosnia and Herzegovina, Austria, Slovakia, Croatia, Slovenia, Bulgaria, Estonia, Latvia |
| Middle East (7) | Israel, Saudi Arabia | Türkiye, Egypt, Jordan | Iran, UAE |
| Africa (7) | Ethiopia | Egypt, Algeria, Morocco | Nigeria, South Africa, Libya |
| Indo-Pacific (6) | Taiwan, Japan, South Korea, India, Australia | China | — |

No priority country has an official (air force / MoD / NATO) source in collection: all ten existing feeds are specialist defence media.

## Feed discovery results

| Country | Candidate | Result (verified 2026-11-08) | Action |
|---|---|---|---|
| Serbia | Ministry of Defence (mod.gov.rs) | RSS 2.0 `https://www.mod.gov.rs/rss.php?eng`, 20 items, newest 2026-11-07, Serbian Cyrillic titles | **added ACS-0016** (Tier 1, Haiku gate, no English keyword prefilter) |
| Poland / CEE | Defence24 | RSS 2.0 `https://defence24.com/_rss`, 50 items, newest 2026-11-07 | **added ACS-0017** (Tier 3, Haiku gate) |
| Romania | MApN (english.mapn.ro) | no RSS/Atom; news at `/event/index.php`, `/cpresa/index.php` | page-polling candidate |
| Others (HU, PL MON, SK, CZ, HR, SI, AT, UA, BG, BY, BA, NATO AIRCOM, IL, TR, JP, TW, KR, IN, AU, CN) | see `config/coverage_sources.json` | not yet verified from this environment | run `python scripts/source_discovery.py` |

State-controlled sources (Russian, Belarusian, Chinese, Iranian, North Korean official/state media) may be used with attribution; all publications of one state group count as **one** evidence lineage (`config/coverage_sources.json → state_controlled`).
