# OPT-GPT-MultiModal

Streamlit dashboard for freight fuel-allocation optimization across Highway, Rail, and Maritime modes. The application code is public; its input datasets and SQL Server databases are proprietary and must remain in approved private storage.

## Data and security model

- Do **not** add proprietary CSV/Parquet files, database backups/exports, credentials, or real connection strings to this repository. The ignore rules block common data-file extensions, but review every staged file before pushing.
- The app reads data on the server. Highway and Rail database access and Maritime file paths are supplied at runtime, not from this repository.
- The host must be approved for the data classification, have private network access to the SQL Server databases and mounted/readable access to the Maritime files, and enforce authentication/authorization for users. The app code does not itself provide user authentication.
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

At deployment, inject the four settings above as protected environment variables and mount the Maritime data read-only into the container. The container image intentionally does not contain the data or credentials. The deployment platform must provide network connectivity to both SQL Servers and an authentication layer in front of the app.

## Before publishing changes

```bash
git status --short
git diff --cached --name-only
```

Ensure no data, secrets, `.env`, local configuration, or database dumps are staged. `.gitignore` is a precaution, not a substitute for reviewing staged files. If a secret has ever entered Git history, rotate it; deleting it from a later commit does not revoke it.