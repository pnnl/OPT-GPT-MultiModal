# OPT-GPT-MultiModal

Streamlit dashboard for freight fuel-allocation optimization across Highway, Rail, and Maritime modes. The source repository is public. Its software is offered under the custom, restricted-use draft in [`LICENSE`](LICENSE), which must be completed and approved by the copyright holder before reliance. The input datasets and SQL Server databases are separate resources and must remain in approved private storage.

## Data and security model

- Do **not** add proprietary CSV/Parquet files, database backups/exports, credentials, or real connection strings to this repository. The ignore rules block common data-file extensions, but review every staged file before pushing.
- The app reads data on the server. Highway and Rail database access and Maritime file paths are supplied at runtime, not from this repository. The app does not provide raw data-file download functionality; keep the underlying databases and files on private, server-side storage, outside the repository and container image.
- The requested deployment is a public dashboard with no user login. Anyone who can reach the deployed service can use its controls and see the values it displays. The host must still be approved for the data classification, restrict database and filesystem access to the app service, and prevent direct network or storage access to the underlying data sources.
- **Server-side storage is not a data-disclosure control.** The current dashboard displays data-derived values, including route/facility choices, selected Maritime freight volumes, baseline metrics, and optimization results. Users may infer or reconstruct information by varying inputs and observing outputs. Data owners must explicitly approve every displayed field and the risk of repeated queries. If they do not, suppress or aggregate sensitive outputs and assess query-based inference before making the dashboard available.
- Use restricted, read-only database accounts and a secrets manager or protected environment variables. Never put secrets in source, `.env.example`, logs, or client-visible output.
- The SQL credentials previously present in the development copy should be rotated if they were ever used or committed.

## Runtime configuration

Set these values in the approved app host's secret/configuration manager (or as environment variables):

| Name | Purpose |
| --- | --- |
| `HIGHWAY_DATABASE_URL` | SQLAlchemy URL for the Highway SQL Server database, e.g. `mssql+pymssql://USER:PASSWORD@HOST:1433/ARPAEHwy` |
| `RAIL_DATABASE_URL` | SQLAlchemy URL for the Rail SQL Server database, e.g. `mssql+pymssql://USER:PASSWORD@HOST:1433/ARPAERail` |
| `MARITIME_FREIGHT_VOLUME_CSV` | Absolute path to protected `Freightvolume_years.csv` on the app host/mount |
| `MARITIME_SIMULATION_PARQUET` | Absolute path to protected `DF_sim.parquet` on the app host/mount |

`.env.example` contains placeholders only. Do not put real values in that file. Streamlit secrets are supported using the same names as top-level keys in the host's protected `secrets.toml`.

Each mode connects to or loads its data only when selected. SQL engines, query results, and Maritime files are cached by Streamlit to reduce repeated reads.

## Run locally (authorized environment only)

Python 3.11 is recommended. Install GLPK as an operating-system package (`glpk-utils` on Debian/Ubuntu or `glpk` on macOS), then:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export HIGHWAY_DATABASE_URL='mssql+pymssql://USER:PASSWORD@HOST:1433/ARPAEHwy'
export RAIL_DATABASE_URL='mssql+pymssql://USER:PASSWORD@HOST:1433/ARPAERail'
export MARITIME_FREIGHT_VOLUME_CSV='/secure/data/Freightvolume_years.csv'
export MARITIME_SIMULATION_PARQUET='/secure/data/DF_sim.parquet'
streamlit run Dashboard.py
```

Do this only on a machine authorized to access the databases and protected files. Do not use production credentials in a personal development environment unless approved.

## Container build

The Dockerfile installs GLPK and Python dependencies. Build from this directory:

```bash
docker build -t opt-gpt-multimodal .
```

At deployment, inject the four settings above as protected environment variables and mount the Maritime data read-only into the container. The container image intentionally does not contain the data or credentials. The deployment platform must provide private network connectivity to both SQL Servers and make the app reachable as a public, login-free service only after the data owner approves the displayed outputs and inference risk. Do not expose the database servers or raw data-file paths to the public.

## License

The custom restricted-use license draft is in [`LICENSE`](LICENSE). It currently contains copyright-holder and year placeholders and requires review and approval by the copyright holder before reliance. It is not a standard open-source license and does not grant rights to the underlying datasets.

## Before publishing changes

```bash
git status --short
git diff --cached --name-only
```

Ensure no data, secrets, `.env`, local configuration, or database dumps are staged. `.gitignore` is a precaution, not a substitute for reviewing staged files. If a secret has ever entered Git history, rotate it; deleting it from a later commit does not revoke it.