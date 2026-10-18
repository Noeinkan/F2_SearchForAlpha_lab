"""Keep the workspace's own files on the data volume across redeploys.

The workspace writes with relative paths (``state/``, ``results/``,
``export/``, ``config/watchlists.json`` ...) from its working directory. In
the image, ``/app/state``, ``/app/results``, ``/app/export`` and
``/app/config`` are symlinks into the volume (``SFA_DATA_DIR``, ``/data``);
the image's own copy of ``config/`` is kept at ``/app/config.dist``.

Every start refreshes ``config/`` from the image -- the repo stays the source
of truth for strategy parameters, the ticker universe and the rest -- except
the files the user edits from the dashboard, which are only seeded when
missing. Symlinking whole directories, not single files, is what keeps the
atomic ``os.replace`` writes in ``watchlist_storage``/``preset_storage``
working: their temp file lands in the same directory as the target.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger("hosted.persist")

# Written by the dashboard (watchlists, presets) or by `sfa promote`.
USER_OWNED_CONFIG = frozenset({"watchlists.json", "ui_presets.json", "param_history.yaml"})
DATA_SUBDIRS = ("state", "results", "export", "config")


def prepare(data_dir: str | os.PathLike | None, dist_config: str | os.PathLike) -> Path | None:
    """Create the volume layout and refresh ``config/`` from the image copy.

    Returns the data directory, or ``None`` when ``data_dir`` is unset (a
    local run, where the working directory is the checkout itself).
    """
    if not data_dir:
        return None
    root = Path(data_dir)
    for name in DATA_SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)

    dist = Path(dist_config)
    target = root / "config"
    refreshed = seeded = 0
    for src in sorted(dist.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(dist)
        dst = target / rel
        if rel.name in USER_OWNED_CONFIG and len(rel.parts) == 1:
            if dst.exists():
                continue
            seeded += 1
        else:
            refreshed += 1
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    logger.info("data volume %s: %d config files refreshed from the image, %d seeded", root, refreshed, seeded)
    return root
