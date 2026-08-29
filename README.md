# Azure SQL Cost & Resource Analytics

An analytics database built on **Azure SQL (serverless)** over live data from my own Azure subscription — resource inventory, tags, and daily cost exports — answering the operational questions a real cloud team asks: *what does each resource group cost, what's untagged, and where is spend trending?*

This is the **data-layer chapter** of a three-repo portfolio:

| Repo | Skill story |
|---|---|
| [azure-webapp-iac](../../../azure-webapp-iac) | Landing zone, networking, governance — Terraform + Azure DevOps CI/CD |
| [azure-container-iac](../../../azure-container-iac) | Containers, multi-environment promotion, managed identity |
| **this repo** | Schema design, intermediate SQL, query performance |

The infrastructure here is deliberately minimal (see [Design decisions](#design-decisions)) — the CI/CD and networking patterns are demonstrated in the other two repos. This one is about the SQL.

## Architecture

```mermaid
erDiagram
    subscriptions ||--o{ resources : contains
    resources ||--o{ resource_tags : has
    resources ||--o{ cost_entries : accrues
```

*(Full ER diagram with columns lands with the schema — Phase 1, Session 4.)*

## Roadmap

- [ ] **Phase 1 — Schema design & data load**
  - [x] Repo scaffolding
  - [ ] Terraform: serverless Azure SQL with auto-pause
  - [ ] Schema DDL (`objects/01_schema.sql`)
  - [ ] ER diagram + normalization decision notes
  - [ ] Data export (`az resource list` + Cost Management CSV)
  - [ ] Python load script (idempotent, env-var connection string)
- [ ] **Phase 2 — Core query library** (joins, aggregation, subqueries)
- [ ] **Phase 3 — Window functions & CTEs**
- [ ] **Phase 4 — Views, indexing & performance** (execution-plan before/after)
- [ ] **Phase 5 (optional) — Portfolio integration**

Phases land as pull requests; queries are committed incrementally as they're written.

## Repo structure

```
terraform/   Infrastructure — SQL server, serverless DB, firewall rule
objects/     Database internals — schema DDL, later views & stored procedures
queries/     Numbered analytical queries (.sql), each headed by the business question it answers
load/        Python script that parses the exports and loads the tables
docs/        Design notes too long for this README
data/        Raw exports — local only, gitignored (contains subscription details)
```

The rule of thumb: if running a file **changes what exists** in the database (`CREATE ...`), it's in `objects/`; if it **reads and returns results** (`SELECT`), it's in `queries/`.

## Design decisions

*(Written as decisions are made — the "why," not just the "what.")*

- **Serverless with auto-pause** — the database idles near $0 and resumes on connection. Unlike the landing zone repo, which is destroyed and rebuilt between sessions, this database *persists*: it accumulates months of cost data, which is what makes the trend queries (LAG, running totals) meaningful.
- **Client-IP firewall rule, not a private endpoint** — *(to be written in Session 2: the threat-model contrast with the landing zone.)*
- **Normalized to 3NF** — *(to be written in Session 4: anomalies, why tags are rows not columns, and when denormalizing would be the right call instead.)*

## Cost

Serverless General Purpose (0.5–1 vCore, auto-pause at 60 min, 2 GB max): effectively **~$0–2/month** at this usage pattern. Storage is the only always-on charge.

## Running it

*(Filled in as the pieces land.)*

1. `terraform apply` from `terraform/` — creates the server, database, and firewall rule
2. Run `objects/01_schema.sql` against the database
3. Export data: `az resource list --output json > data/inventory.json` + Cost Management CSV → `data/`
4. `python load/load_data.py` (connection string via `SQL_CONNECTION_STRING` env var)
