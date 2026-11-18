"""Download the pinned MWCCVC dataset, validate it, and record byte hashes.

This is a data import, not an algorithm experiment. Git commands target only
the dedicated source checkout; no network namespace or service is touched.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
from ccvc.greedy.central import REVISION, SOURCE_SHA256
from ccvc.greedy.dataset import DEFAULT_DATASET, FILENAME, read_instance

URL = "https://github.com/egerberkuslu/MWCCVC.git"


def fetch(checkout: Path, destination: Path):
    if not checkout.exists():
        checkout.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", str(checkout)], check=True, capture_output=True)
        commands = [
            ["remote", "add", "origin", URL],
            ["sparse-checkout", "set", "--no-cone", "/backend/app/algorithms.py",
             "/backend/data/DagdevirenDataset/", "/README.md"],
            ["fetch", "--depth", "1", "--filter=blob:none", "origin", REVISION],
            ["checkout", "--detach", "FETCH_HEAD"],
        ]
        for command in commands:
            subprocess.run(["git", "-C", str(checkout), *command], check=True)
    revision = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        raise ValueError(f"Source checkout is {revision}, expected pinned revision {REVISION}")
    source = checkout / "backend/data/DagdevirenDataset"
    paths = sorted(path for path in source.glob("*.txt") if FILENAME.fullmatch(path.name))
    if not paths:
        raise ValueError("Pinned repository has no Dagdeviren instances")
    instances = [read_instance(path) for path in paths]
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    for instance in instances:
        target = destination / instance.path.name
        if target.exists() and target.read_bytes() != instance.path.read_bytes():
            raise ValueError(f"Existing dataset file differs: {target}; refusing to overwrite it")
        if not target.exists():
            shutil.copyfile(instance.path, target)
        records.append({"file": target.name, "n": instance.n, "m": instance.m,
                        "seed": instance.seed, "sha256": instance.sha256,
                        "connected": True, "weight_transform": "none"})
    cells = Counter((instance.n, instance.m) for instance in instances)
    manifest = {"source_repository": URL.removesuffix(".git"), "source_revision": REVISION,
                "source_subdirectory": "backend/data/DagdevirenDataset",
                "algorithms_sha256": SOURCE_SHA256, "files": records,
                "file_count": len(records), "cell_count": len(cells),
                "bytes": sum(instance.path.stat().st_size for instance in instances),
                "validation": "Exact filename counts, unique vertices/edges, positive finite weights, connected input",
                "cells": [{"n": n, "m": m, "seeds": count,
                           "small_sample_only": count < 3} for (n, m), count in sorted(cells.items())],
                "algorithm_experiments_executed": False}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({key: manifest[key] for key in ("source_revision", "file_count", "cell_count", "bytes",
                                                    "algorithm_experiments_executed")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=PROJECT / "external_sources/MWCCVC")
    parser.add_argument("--destination", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args()
    fetch(args.checkout, args.destination)
