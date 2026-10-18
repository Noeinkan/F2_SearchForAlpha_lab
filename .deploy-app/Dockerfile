# alpha-lab — the SearchForAlpha Lab research workspace, behind the owner login.
#
# One Python container: waitress serves the Dash app that hosted/server.py
# builds. Live Yahoo and SEC data, unlike the demo. No broker: ib_async is not
# installed (hosted/requirements.txt reuses the demo's pins) and lib/live/ is
# deleted below, so paper or live trading cannot start from this image.

ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SFA_DATA_DIR=/data \
    SFA_DIST_CONFIG=/app/config.dist

WORKDIR /app

# Dependencies before source, so editing a callback does not reinstall pandas.
COPY repo/demo/requirements.txt /app/demo/requirements.txt
COPY repo/hosted/requirements.txt /app/hosted/requirements.txt
RUN pip install --no-cache-dir -r /app/hosted/requirements.txt

COPY repo/lib/ /app/lib/
COPY repo/scripts/ /app/scripts/
COPY repo/hosted/ /app/hosted/
COPY repo/main.py /app/main.py
COPY repo/config/ /app/config.dist/

# The order path is absent, not switched off. The writable folders the
# workspace uses by relative path point into the data volume (hosted/persist.py).
RUN rm -rf /app/lib/live /app/lib/tests \
 && mkdir -p /data \
 && ln -s /data/state /app/state \
 && ln -s /data/results /app/results \
 && ln -s /data/export /app/export \
 && ln -s /data/config /app/config \
 && useradd --create-home --uid 10001 sfa \
 && chown sfa:sfa /data

USER sfa

EXPOSE 8050
CMD ["python", "-m", "hosted.server"]
