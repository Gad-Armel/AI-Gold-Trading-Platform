# Microstructure runtime data

The paper runner creates partitioned tick and feature Parquet datasets here.
`run_microstructure_catalog.py` creates `scalping_research.duckdb` after data is
available. These generated files are excluded from the release archive.
