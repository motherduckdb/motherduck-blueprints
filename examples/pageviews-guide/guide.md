# Wikipedia pageviews

## When to use

Read this before answering a question about how often a Wikipedia article was viewed, or before building a Dive on the `wikipedia_pageviews` share.

## Source and refresh

- The `wikipedia-pageviews` Flight loads the [Wikimedia Pageviews API](https://wikimedia.org/api/rest_v1/#/Pageviews%20data) every day at 06:17 UTC.
- Each run loads the last 30 complete days for the configured articles and replaces rows it already holds, so a rerun does not duplicate data.
- Only the articles listed in the Flight's `articles` config are present. An article that is absent was not loaded; it does not have zero views.
- The most recent day in the table is yesterday or the day before, because Wikimedia publishes a day after it ends.

## Tables

### `main.pageviews_daily`

One row per project, article, access method, agent type, and day.

| Column | Meaning |
| --- | --- |
| `project` | Wikipedia site, for example `en.wikipedia.org`. |
| `article` | Article title as it appears in the URL, with underscores for spaces. |
| `access` | `all-access`, `desktop`, `mobile-app`, or `mobile-web`. The default load holds `all-access` only. |
| `agent` | `user`, `spider`, `automated`, or `all-agents`. The default load holds `user` only. |
| `granularity` | Always `daily`. |
| `viewed_on` | The day, as a `DATE` in UTC. |
| `views` | Pageviews on that day. |
| `loaded_at_utc` | When the row was loaded. Use it to check freshness, not for analysis. |

### `main.pageviews_article_summary`

One row per article with totals over the loaded window. Use it for a single number per article. Use `pageviews_daily` for anything over time.

## Rules

- Filter or group by `access` and `agent` whenever more than one value is loaded. Summing `all-access` with `desktop` counts the same views twice.
- Compare complete days only. Exclude `current_date` and check `max(viewed_on)` before reporting on "this week".
- Article titles are case-sensitive: `DuckDB` and `Duckdb` are different articles.

## Query patterns

Daily views for one article:

```sql
SELECT viewed_on, views
FROM wikipedia_pageviews.main.pageviews_daily
WHERE article = 'DuckDB' AND access = 'all-access' AND agent = 'user'
ORDER BY viewed_on;
```

Views per article over the last seven loaded days:

```sql
SELECT article, sum(views) AS views_last_7_days
FROM wikipedia_pageviews.main.pageviews_daily
WHERE viewed_on > (SELECT max(viewed_on) FROM wikipedia_pageviews.main.pageviews_daily) - 7
GROUP BY article
ORDER BY views_last_7_days DESC;
```

## Sources and checks

- Columns and keys: `flights/wikipedia-pageviews-ingest/src/flight.py`.
- Schedule and loaded articles: `flights/wikipedia-pageviews-ingest/blueprint.yml`.
- Not covered: per-country views and redirects, which the API endpoint used here does not return.
