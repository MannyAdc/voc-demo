"""DuckDB connections. Extensions are never installed or loaded behind our back."""
import duckdb

SAFE_CONFIG = {"autoinstall_known_extensions": False, "autoload_known_extensions": False}


def connect(path=":memory:"):
    return duckdb.connect(str(path), config=SAFE_CONFIG)
