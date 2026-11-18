"""Reproducible station configuration, resolved outside the node decision path."""
from dataclasses import asdict, fields
import math


def link_attempts_for(mis_nbrs_max: int) -> int:
    """How many times the one-shot LINK handshake may be retried, by density.

    R_max IS A CAP, NOT A COST. Attempts after the first are spent only when an
    ACK does not arrive, so raising the cap is free for a neighbourhood where
    the first attempt already succeeds; it buys nothing there and costs nothing.

    THE DEFAULT OF 3 IS A BINDING CONSTRAINT AT TWENTY STATIONS. Measured on
    n20_m160, three seeds, three arms: with three attempts the handshake
    exhausted itself 14 to 134 times per run, and because a giving-up entry is
    never retried the neighbour stayed permanently one-way, so edges never
    formed and only one of nine runs was validator-clean. With eight attempts
    the same nine runs recorded ZERO give-ups, zero expiries and zero epoch
    restarts, discovery completed at 185-188 edges, and every run that does not
    use GHS came back valid: MIS-Connector in 59-72 slots and Anneal-Local in
    145-153. GHS-MST still returned nothing in all three, which is the separate
    limit of its own round complexity and not of the handshake.

    At ten and fifteen stations three attempts already sufficed (zero give-ups
    in eighteen runs), so the rule keeps three there and grows with the
    neighbourhood the planner expects.
    """
    return max(3, -(-int(mis_nbrs_max) // 2))


def station_params(kind, weights, channel, mis_nbrs_max, *, overrides=None, mode="sync", seed=0):
    from ccvc.bb.mnwifi.node_main import resolve_node_kind
    _, params_class = resolve_node_kind(kind)
    overrides = dict(overrides or {})
    unknown = set(overrides) - {field.name for field in fields(params_class)}
    if unknown:
        raise ValueError(f"Unknown deployment parameters for {kind}: {sorted(unknown)}")
    for field, expected in (("t_hello_ms", channel.t_hello_ms), ("mis_nbrs_max", mis_nbrs_max)):
        if field in overrides and overrides[field] != expected:
            raise ValueError(f"{field} must agree with the saved channel/topology plan")
    settings = {"t_hello_ms": channel.t_hello_ms, "mis_nbrs_max": mis_nbrs_max,
                "link_max_attempts": link_attempts_for(mis_nbrs_max), **overrides}
    if kind in ("gccvc", "grccvc", "gwccvc"):
        if "algorithm" in settings and settings["algorithm"] != kind:
            raise ValueError("Greedy algorithm parameter disagrees with node kind")
        settings["algorithm"] = kind
    if kind == "anneal":
        settings.setdefault("rng_seed", seed)
    params = params_class(**settings)
    if getattr(params, "trickle", False) and mode != "async":
        raise ValueError("Trickle is an asynchronous-only transmission policy")
    if kind == "anneal":
        # All nodes receive one saved deployment configuration. This global
        # maximum is not discovered locally and must be disclosed in the audit.
        params = params.resolved(list(weights.values()))
        values = (params.lam_c, params.lam_k, params.lam_b, params.t0, params.t_min_temp)
        if any(value is None or not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError("Annealing penalties and temperatures must be finite and positive")
        if min(params.lam_c, params.lam_k, params.lam_b) <= max(weights.values()):
            raise ValueError("Annealing penalties must exceed the deployment weight maximum")
    if kind == "wuli" and params.encoding not in ("full", "bloom", "chunked"):
        raise ValueError(f"Unknown Wu-Li encoding {params.encoding!r}")
    return asdict(params)
