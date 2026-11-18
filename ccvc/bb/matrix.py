#!/usr/bin/env python3
"""Deney matrisi: düğüm sayıları ve bağlantı oranları (kullanıcı tanımı, 2026-09-15).

Kaynak: MWCCVC'nin kendi Dagdeviren veri kümesinin yapısı.

    KÜÇÜK   n ∈ {10, 15, 20, 25}        m/n ∈ {2, 4, 6, 8}
    ORTA    n ∈ {50, 100, 150, 200}     m/n ∈ {2, 4, 6, 8}
    BÜYÜK   n ∈ {250, 500, 750, 1000}   m/n ∈ {2, 4, 6, 8, 10}

ÖLÇÜLDÜ (2026-09-15): istenen 52 hücrenin 49'u veri kümesinde mevcut. Eksik üçü
eksik değil, **matematiksel olarak imkânsız**, çünkü basit çizgede en fazla
C(n,2) kenar olabilir:

    n=10, m/n=6  -> m=60  > C(10,2)=45
    n=10, m/n=8  -> m=80  > 45
    n=15, m/n=8  -> m=120 > C(15,2)=105

Genel sınır: m/n <= (n-1)/2. `feasible_cells()` bunu zorlar, dolayısıyla
koşucu tanımsız hücre istemez.

TOHUM DENGESİZLİĞİ (raporda söylenmeli): küçük ve orta hücrelerde 10 tohum,
büyük hücrelerde **1 tohum** var. Deney disiplini en az 3 tohum istiyor,
dolayısıyla büyük grup sonuçları ya tek koşum diye etiketlenir ya da ek örnek
üretilir. `seeds_available()` gerçek sayıyı döndürür, varsayım yapmaz.

EMÜLATÖR TAVANI: mininet-wifi istasyon başına bir süreç koşar, 200 düğüm tavan.
Yani simülatör bütün matrisi, emülatör yalnız küçük+orta grubu koşar.
Emülatörün rolü ölçek değil, simülatör sayaçlarının gerçek kanalda doğrulanması.
"""
from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass
from math import comb
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

DATASET_ENV = "MWCCVC_DATASET"
_DEFAULT_DATASET = "MWCCVC/backend/data/DagdevirenDataset"

SMALL_N: Tuple[int, ...] = (10, 15, 20, 25)
MEDIUM_N: Tuple[int, ...] = (50, 100, 150, 200)
LARGE_N: Tuple[int, ...] = (250, 500, 750, 1000)

SMALL_RATIOS: Tuple[int, ...] = (2, 4, 6, 8)
MEDIUM_RATIOS: Tuple[int, ...] = (2, 4, 6, 8)
LARGE_RATIOS: Tuple[int, ...] = (2, 4, 6, 8, 10)

#: mininet-wifi'de istasyon başına bir süreç; bunun üstü tek makinede pratik değil
EMULATOR_MAX_N = 200

GROUPS: Tuple[Tuple[str, Tuple[int, ...], Tuple[int, ...]], ...] = (
    ("small", SMALL_N, SMALL_RATIOS),
    ("medium", MEDIUM_N, MEDIUM_RATIOS),
    ("large", LARGE_N, LARGE_RATIOS),
)


@dataclass(frozen=True)
class Cell:
    """Matrisin bir hücresi. `m` türetilir, uydurulmaz."""

    group: str
    n: int
    ratio: int

    @property
    def m(self) -> int:
        return self.n * self.ratio

    @property
    def max_edges(self) -> int:
        return comb(self.n, 2)

    @property
    def possible(self) -> bool:
        """Basit çizgede bu kadar kenar olabilir mi."""
        return self.m <= self.max_edges

    @property
    def fits_emulator(self) -> bool:
        return self.n <= EMULATOR_MAX_N

    @property
    def stem(self) -> str:
        return f"n{self.n}_m{self.m}"

    def why_impossible(self) -> Optional[str]:
        if self.possible:
            return None
        return (
            f"m={self.m} > C({self.n},2)={self.max_edges}; "
            f"bu n için en büyük oran {(self.n - 1) / 2:.1f}"
        )


def all_cells() -> List[Cell]:
    """İstenen matrisin tamamı, imkânsızlar dahil."""
    return [Cell(g, n, r) for g, ns, rs in GROUPS for n in ns for r in rs]


def feasible_cells(emulator_only: bool = False) -> List[Cell]:
    """Gerçekten kurulabilir hücreler. Tanımsız olanlar sessizce atılmaz, filtrelenir."""
    out = [c for c in all_cells() if c.possible]
    if emulator_only:
        out = [c for c in out if c.fits_emulator]
    return out


def impossible_cells() -> List[Cell]:
    return [c for c in all_cells() if not c.possible]


# --------------------------------------------------------------------------
# veri kümesiyle eşleme
# --------------------------------------------------------------------------
def dataset_dir() -> Optional[str]:
    """Veri kümesi dizini; ortam değişkeni ya da bilinen konumlar."""
    env = os.environ.get(DATASET_ENV)
    if env and os.path.isdir(env):
        return env
    local = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                         "data", "DagdevirenDataset")
    if os.path.isdir(local):
        return local
    for base in (os.getcwd(), "/tmp"):
        for hit in glob.glob(
            os.path.join(base, "**", _DEFAULT_DATASET), recursive=True
        ):
            if os.path.isdir(hit):
                return hit
    return None


def _index(directory: str) -> Dict[Tuple[int, int], List[int]]:
    idx: Dict[Tuple[int, int], List[int]] = {}
    for path in glob.glob(os.path.join(directory, "*.txt")):
        m = re.match(r"n(\d+)_m(\d+)_s(\d+)\.txt$", os.path.basename(path))
        if m:
            idx.setdefault((int(m.group(1)), int(m.group(2))), []).append(
                int(m.group(3))
            )
    return {k: sorted(v) for k, v in idx.items()}


def seeds_available(cell: Cell, directory: Optional[str] = None) -> List[int]:
    """Bu hücre için veri kümesinde GERÇEKTEN kaç tohum var. Varsayım yok."""
    d = directory or dataset_dir()
    if d is None:
        return []
    return _index(d).get((cell.n, cell.m), [])


def instance_path(
    cell: Cell, seed: int, directory: Optional[str] = None
) -> Optional[str]:
    d = directory or dataset_dir()
    if d is None:
        return None
    p = os.path.join(d, f"{cell.stem}_s{seed}.txt")
    return p if os.path.exists(p) else None


def load_instance(path: str) -> Tuple[Dict[int, float], List[Tuple[int, int]]]:
    """Dagdeviren biçimi: önce `id ağırlık`, sonra `u v` satırları."""
    if re.fullmatch(r"n\d+_m\d+_s\d+\.txt", os.path.basename(path)):
        from ccvc.greedy.dataset import read_instance
        instance = read_instance(path)
        return dict(instance.weights), list(instance.edges)
    weights: Dict[int, float] = {}
    edges: List[Tuple[int, int]] = []
    for line in open(path):
        parts = line.split()
        if len(parts) != 2:
            continue
        a, b = parts
        if "." in b:
            weights[int(a)] = float(b)
        else:
            u, v = int(a), int(b)
            edges.append((u, v) if u <= v else (v, u))
    return weights, sorted(set(edges))


# --------------------------------------------------------------------------
# kapsam raporu
# --------------------------------------------------------------------------
def coverage(directory: Optional[str] = None) -> Dict[str, object]:
    """Matrisin veri kümesiyle ne kadar örtüştüğü. Rapora doğrudan girer."""
    d = directory or dataset_dir()
    cells = all_cells()
    possible = [c for c in cells if c.possible]
    present = [c for c in possible if seeds_available(c, d)]
    thin = [c for c in present if len(seeds_available(c, d)) < 3]
    return {
        "dataset_dir": d,
        "requested": len(cells),
        "impossible": len(cells) - len(possible),
        "possible": len(possible),
        "present_in_dataset": len(present),
        "missing_from_dataset": len(possible) - len(present),
        "cells_with_fewer_than_3_seeds": len(thin),
        "instances_total": sum(len(seeds_available(c, d)) for c in present),
        "emulator_cells": len([c for c in present if c.fits_emulator]),
    }


def main() -> None:
    imp = impossible_cells()
    print("İMKÂNSIZ HÜCRELER (matris tanımsız, veri kümesi eksik değil)")
    for c in imp:
        print(f"  {c.group:6s} n={c.n:<5} m/n={c.ratio:<3} -> {c.why_impossible()}")
    d = dataset_dir()
    print(f"\nveri kümesi: {d or 'BULUNAMADI'}")
    cov = coverage(d)
    for key, val in cov.items():
        print(f"  {key:32s} {val}")
    if d:
        print(
            f"\n{'grup':7s} {'n':>5} {'m/n':>4} {'m':>6} {'tohum':>6} {'emülatör':>9}"
        )
        for c in feasible_cells():
            s = seeds_available(c, d)
            print(
                f"{c.group:7s} {c.n:>5} {c.ratio:>4} {c.m:>6} {len(s):>6} "
                f"{'evet' if c.fits_emulator else 'hayır':>9}"
            )


if __name__ == "__main__":
    main()
