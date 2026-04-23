# SearchForAlpha task runner. Run with `just <target>`.

default:
    @just --list

install:
    pip install -e ".[dev]"

test:
    python -m pytest lib/tests/ -v

dash:
    python main.py

cli *args:
    sfa {{args}}

lint:
    ruff check lib
    ruff format --check lib

fmt:
    ruff format lib

mypy:
    mypy lib/cli lib/bayesian_optimization.py lib/walkforward lib/promotion lib/live lib/store

clean-state:
    rm -f state/optuna.db
    rm -f state/running/*.pid
