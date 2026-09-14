# alpha — the public demo of SearchForAlpha Lab.
#
# One Python container: waitress serves the Dash app built by demo/server.py.
# Nothing in the image can reach a market-data vendor or a broker:
#   - the data is the frozen snapshot committed at demo/fixtures/;
#   - ib_async is not installed (demo/requirements.txt leaves it out);
#   - lib/live/ (the paper-trading runner, broker and guards) is deleted below;
#   - and demo.sealing refuses sockets, yfinance and the order-path imports at
#     runtime, in case any of the above ever regresses.

ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies before source, so editing a callback does not reinstall pandas.
COPY repo/demo/requirements.txt /app/demo/requirements.txt
RUN pip install --no-cache-dir -r /app/demo/requirements.txt

COPY repo/lib/ /app/lib/
COPY repo/config/ /app/config/
COPY repo/scripts/ /app/scripts/
COPY repo/demo/ /app/demo/

# The order path is not merely switched off in this image: it is absent.
# Tests and capture configs have no business in a public container either.
RUN rm -rf /app/lib/live /app/lib/tests /app/demo/shotkit.demo.config.mjs \
 && mkdir -p /app/state /app/data \
 && useradd --create-home --uid 10001 demo \
 && chown demo:demo /app/state /app/data

USER demo

EXPOSE 8050
CMD ["python", "-m", "demo.server"]
