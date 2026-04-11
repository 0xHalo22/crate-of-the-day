# crate-of-the-day

one hand-picked [rust crate](https://crates.io) highlighted every day, committed to git.

a daily dose of ecosystem serendipity. the algorithm is simple: pull the
recently-updated crates from crates.io, filter out obvious test/spam packages,
pick the first one that looks real and that we haven't highlighted in the
last 30 days, write it up.

## how it works

a [github actions workflow](.github/workflows/scrape.yml) runs once a day,
hits the [public crates.io API](https://crates.io/data-access), picks a crate
with a non-trivial description and some minimum download count, and commits a
dated markdown file to `highlights/`.

## browse

- [`latest.md`](./latest.md) — today's pick
- [`highlights/YYYY-MM-DD.md`](./highlights) — the full archive

## credits

crate metadata is pulled from [crates.io](https://crates.io) via their public
JSON API. all crates are the work of their respective authors and are
licensed under whatever license each crate specifies.
