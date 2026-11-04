"""How much does per-cell wind (services/wind.py) change UTCI and routes? (H8)

For every 청주 ASOS hour 09-18 in summer (Jun-Aug) and winter (Dec-Feb) the
campus UTCI is computed with

- uniform : the ASOS speed everywhere (the app today)
- K       : ASOS ws × K(x, y; sector, season)              (main)
- K_mean  : ASOS ws × campus mean of that K, the same everywhere
            (separates "less wind overall" from "a different pattern")
- K_e3, K_e10 : K with the wake e-folding length at 3 H and 10 H (sensitivity)

and routes between fixed pairs of campus buildings are found with

- app cost      : routing.WalkNetwork.routes as served (heat above the shade baseline)
- two-sided cost: length × (1 + α s), s = [(U − 26)+ + (9 − U)+] / 5,
                  the same α ladder and detour limits, so cold counts too.

A pair's route "changes" in an hour when the balanced or the coolest route
differs (any edge) from the one found with uniform wind. H8, fixed in
advance: per-cell wind matters if that happens in ≥ 10 % of the time.
"K_vs_K_mean" compares K with K_mean instead: the pattern alone.

Run from the repository root:

    PYTHONPATH=backend .venv/bin/python scripts/analyze_wind_effect.py [--workers 8] [--limit N]

Writes docs/wind/results.json and figures to docs/wind/.
"""

from __future__ import annotations

import argparse
import csv
import json
import multiprocessing as mp
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings  # noqa: E402
from app.db.repository import BuildingRepository  # noqa: E402
from app.main import load_campus_boundary  # noqa: E402
from app.services import routing  # noqa: E402
from app.services.microclimate import MicroclimateModel  # noqa: E402
from app.services.solar import SEOUL_TZ, calculate_solar_position  # noqa: E402
from app.services.surfaces import in_leaf, load_land_cover, load_street_trees  # noqa: E402
from app.services.terrain import Terrain  # noqa: E402
from app.services.thermal import relative_humidity, utci  # noqa: E402
from app.services.weather import WeatherStore, WeatherUnavailable  # noqa: E402
from app.services.wind import SECTORS, WindField, sector_of  # noqa: E402

OUT = ROOT / "docs" / "wind"
SEASONS = {"summer": (6, 7, 8), "winter": (12, 1, 2)}
HOURS = range(9, 19)
COLD_LIMIT_C = 9.0  # bottom of UTCI "no thermal stress"
# Fixed origin/destination buildings: the main teaching, library, admin and
# dormitory buildings spread over campus. Every pair among them is used.
OD_BUILDINGS = [
    "중앙도서관 신관 (N12)",
    "대학본부 (N10)",
    "개신문화관 (E2)",
    "공학관 (E8-1)",
    "자연과학대학 본관 (S1-1)",
    "경영대학 본관 (N13)",
    "사범대학 강의동 (E1-2)",
    "수의과대학 및 동물의료센터 (E12-1)",
    "법학전문대학원 (N2)",
    "예지관",
]
VARIANTS = ("uniform", "K", "K_mean", "K_e3", "K_e10")
DELTA_BINS = np.arange(-15.0, 15.0001, 0.1)
# ΔUTCI histograms and route comparisons are against uniform wind.

G: dict = {}  # model, network, wind fields, ... built once and shared with forked workers


def build() -> None:
    t0 = time.time()
    buildings = BuildingRepository(database_url=None, snapshot_path=settings.building_data_path).list_buildings()
    ground, canopies = load_land_cover(settings.landcover_data_path)
    model = MicroclimateModel(
        load_campus_boundary(),
        buildings,
        terrain=Terrain(settings.terrain_data_path),
        ground=ground,
        canopies=canopies
        + load_street_trees(settings.tree_canopy_data_path)
        + load_street_trees(settings.street_trees_data_path),
    )
    fields = {"K": WindField(model), "K_e3": WindField(model, wake_e_fold=3.0), "K_e10": WindField(model, wake_e_fold=10.0)}
    for field in fields.values():
        field.precompute()
    model.wind_field = fields["K"]
    network = routing.WalkNetwork(settings.walk_network_data_path)
    by_name = {b.name: b for b in buildings}
    od_nodes = []
    for name in OD_BUILDINGS:
        centre = by_name[name].geometry.centroid
        od_nodes.append(network.snap(centre.x, centre.y))
    pairs = [(i, j) for i in range(len(od_nodes)) for j in range(i + 1, len(od_nodes))]
    n = network.node_count
    G.update(
        model=model,
        fields=fields,
        network=network,
        od_nodes=od_nodes,
        pairs=pairs,
        rows=np.concatenate([network.edge_a, network.edge_b]),
        cols=np.concatenate([network.edge_b, network.edge_a]),
        n=n,
        weather=WeatherStore(settings.weather_data_path, settings.campus_latitude, settings.campus_longitude),
    )
    print(f"built model, wind fields and network in {time.time() - t0:.0f} s", flush=True)


def asos_hours(limit: int | None) -> list[tuple[str, datetime, float, float]]:
    hours = []
    with settings.weather_data_path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            stamp = datetime.strptime(row["tm"], "%Y-%m-%d %H:%M").replace(tzinfo=SEOUL_TZ)
            season = next((s for s, months in SEASONS.items() if stamp.month in months), None)
            if season is None or stamp.hour not in HOURS or not row["ws"] or not row["wd"]:
                continue
            hours.append((season, stamp, float(row["ws"]), float(row["wd"])))
    if limit:
        step = max(1, len(hours) // limit)
        hours = hours[::step][:limit]
    return hours


# -- routing (same rules as routing.WalkNetwork.routes, many pairs at once) --------------


def predecessors(weights: np.ndarray, sources: list[int]) -> np.ndarray:
    matrix = csr_matrix((np.concatenate([weights, weights]), (G["rows"], G["cols"])), shape=(G["n"], G["n"]))
    _, pred = dijkstra(matrix, indices=sources, return_predecessors=True)
    return pred


def walk(pred_row: np.ndarray, start: int, end: int) -> tuple[int, ...]:
    nodes = [end]
    while nodes[-1] != start:
        nodes.append(int(pred_row[nodes[-1]]))
    return tuple(reversed(nodes))


def edges_of(nodes: tuple[int, ...]) -> list[int]:
    edge_of = G["network"].edge_of
    return [edge_of[(min(a, b), max(a, b))] for a, b in zip(nodes, nodes[1:])]


def choose(stress: np.ndarray | None) -> dict[tuple[int, int], tuple[tuple, tuple]]:
    """Per pair (balanced, coolest) node tuples; both the shortest when stress is None/zero."""
    network, od, pairs = G["network"], G["od_nodes"], G["pairs"]
    sources = sorted({od[i] for i, _ in pairs})
    index = {s: k for k, s in enumerate(sources)}
    shortest_pred = G["shortest_pred"]
    shortest = {(i, j): walk(shortest_pred[index[od[i]]], od[i], od[j]) for i, j in pairs}
    if stress is None or not stress.any():
        return {p: (shortest[p], shortest[p]) for p in pairs}
    preds = [predecessors(network.length * (1 + alpha * stress), sources) for alpha in routing.ALPHAS]
    out = {}
    for i, j in pairs:
        s_len = float(network.length[edges_of(shortest[(i, j)])].sum())
        candidates = []
        for pred in preds:
            nodes = walk(pred[index[od[i]]], od[i], od[j])
            e = edges_of(nodes)
            candidates.append((float(network.length[e].sum()), float((network.length[e] * stress[e]).sum()), nodes))
        chosen = []
        for limit in (routing.BALANCED_DETOUR, routing.COOLEST_DETOUR):
            allowed = [c for c in candidates if c[0] <= s_len * limit]
            chosen.append(min(allowed, key=lambda c: (c[1], c[0]))[2] if allowed else shortest[(i, j)])
        out[(i, j)] = tuple(chosen)
    return out


def app_stress(edge_utci: np.ndarray, shade_utci: float, daylight: bool) -> np.ndarray | None:
    if not daylight:
        return None
    filled = np.where(np.isfinite(edge_utci), edge_utci, np.nanmedian(edge_utci))
    return np.maximum(filled - max(routing.COMFORT_LIMIT_C, shade_utci), 0) / routing.HEAT_SCALE_C


def two_sided_stress(edge_utci: np.ndarray) -> np.ndarray:
    filled = np.where(np.isfinite(edge_utci), edge_utci, np.nanmedian(edge_utci))
    return (np.maximum(filled - routing.COMFORT_LIMIT_C, 0) + np.maximum(COLD_LIMIT_C - filled, 0)) / routing.HEAT_SCALE_C


def overlap(a: tuple, b: tuple) -> float:
    """Share of route a's length that route b also uses."""
    length = G["network"].length
    ea, eb = edges_of(a), set(edges_of(b))
    return float(sum(length[e] for e in ea if e in eb) / length[ea].sum()) if ea else 1.0


# -- one hour ---------------------------------------------------------------------------


def one_hour(item: tuple[str, datetime, float, float]) -> dict | None:
    season, when, ws, wd = item
    model, network = G["model"], G["network"]
    try:
        weather = G["weather"].at(when)
    except WeatherUnavailable:
        return None
    solar = calculate_solar_position(when, settings.campus_latitude, settings.campus_longitude)
    base = model.fields(when, solar, weather)
    day = when.date()
    leaf = in_leaf(day)
    sector = sector_of(wd, weather.wind_ms)
    air = np.full(model.valid.shape, weather.air_temp_c)
    rh = relative_humidity(air, weather.dew_point_c)
    k_main = G["fields"]["K"].factor(sector, leaf)
    k_mean = float(np.nanmean(k_main))
    # The sun is traced once; UTCI with per-cell wind is what model.fields(...,
    # wind_direction_deg=wd) returns (checked in check_against_app).
    comfort = {
        "uniform": base.utci,
        "K": np.where(model.valid, utci(air, base.mrt, G["fields"]["K"].wind_ms(weather.wind_ms, wd, day), rh), np.nan),
        "K_mean": np.where(model.valid, utci(air, base.mrt, weather.wind_ms * k_mean, rh), np.nan),
    }
    for name in ("K_e3", "K_e10"):
        wind = G["fields"][name].wind_ms(weather.wind_ms, wd, day)
        comfort[name] = np.where(model.valid, utci(air, base.mrt, wind, rh), np.nan)

    valid = model.valid
    sun = base.sunlit[valid]
    sunny, shady = sun >= 0.5, sun < 0.5
    result = {
        "season": season, "when": when.isoformat(), "ws": ws, "wd": wd, "model_ws": weather.wind_ms,
        "sector": sector, "leaf": leaf, "altitude": solar.altitude, "air": weather.air_temp_c,
        "k_mean": k_mean, "k_p5": float(np.nanpercentile(k_main, 5)), "k_p95": float(np.nanpercentile(k_main, 95)),
        "wind_cells_at_floor_uniform": float(weather.wind_ms < 0.5),
        "wind_cells_at_floor_K": float(np.mean(weather.wind_ms * k_main[valid] < 0.5)),
        "utci": {}, "routes": {},
    }
    for name, values in comfort.items():
        v = values[valid]
        delta = v - base.utci[valid]
        result["utci"][name] = {
            "mean": float(np.nanmean(v)),
            "p5": float(np.nanpercentile(v, 5)),
            "p95": float(np.nanpercentile(v, 95)),
            "delta_mean": float(np.nanmean(delta)),
            "delta_sun": float(np.nanmean(delta[sunny])) if sunny.any() else None,
            "delta_shade": float(np.nanmean(delta[shady])) if shady.any() else None,
            "sun_minus_shade": float(np.nanmean(v[sunny]) - np.nanmean(v[shady])) if sunny.any() and shady.any() else None,
            "hist_sun": np.histogram(np.clip(delta[sunny], -15, 15), DELTA_BINS)[0].tolist() if name == "K" else None,
            "hist_shade": np.histogram(np.clip(delta[shady], -15, 15), DELTA_BINS)[0].tolist() if name == "K" else None,
        }

    daylight = solar.altitude > 0
    chosen: dict[str, dict] = {}
    for name, values in comfort.items():
        edge = network.sample(model.fill_under_buildings(values), model.grid)
        shade = float(np.nanpercentile(values, routing.SHADE_PERCENTILE))
        chosen[("app", name)] = choose(app_stress(edge, shade, daylight))
        chosen[("two_sided", name)] = choose(two_sided_stress(edge))
    comparisons = [(name, "uniform", name) for name in VARIANTS[1:]] + [("K_vs_K_mean", "K_mean", "K")]
    for cost in ("app", "two_sided"):
        for name, ref_name, other_name in comparisons:
            ref, other = chosen[(cost, ref_name)], chosen[(cost, other_name)]
            changed = coolest = big = 0
            for pair in G["pairs"]:
                b0, c0 = ref[pair]
                b1, c1 = other[pair]
                if b0 != b1 or c0 != c1:
                    changed += 1
                    if min(overlap(b0, b1), overlap(c0, c1)) < 0.9:
                        big += 1
                coolest += c0 != c1
            # Pairs whose coolest route is anything other than the shortest under the reference.
            active = sum(1 for p in G["pairs"] if ref[p][1] != G["shortest"][p])
            result["routes"][f"{cost}:{name}"] = {"changed": changed, "coolest_changed": coolest, "big": big, "active": active}
    return result


def init_shortest() -> None:
    network, od, pairs = G["network"], G["od_nodes"], G["pairs"]
    sources = sorted({od[i] for i, _ in pairs})
    G["shortest_pred"] = predecessors(network.length, sources)
    index = {s: k for k, s in enumerate(sources)}
    G["shortest"] = {(i, j): walk(G["shortest_pred"][index[od[i]]], od[i], od[j]) for i, j in pairs}


def check_against_app() -> None:
    """The batched selection must reproduce routing.WalkNetwork.routes."""
    model, network = G["model"], G["network"]
    when = datetime(2025, 8, 5, 14, tzinfo=SEOUL_TZ)
    solar = calculate_solar_position(when, settings.campus_latitude, settings.campus_longitude)
    fields = model.fields(when, solar, G["weather"].at(when))
    edge = network.sample(model.fill_under_buildings(fields.utci), model.grid)
    shade = float(np.nanpercentile(fields.utci, routing.SHADE_PERCENTILE))
    mine = choose(app_stress(edge, shade, True))
    od = G["od_nodes"]
    for pair in G["pairs"][:12]:
        found = network.routes(od[pair[0]], od[pair[1]], edge, shade, daylight=True)
        app_nodes = {tuple(r.nodes) for r in found}
        assert set(mine[pair]) <= app_nodes | {tuple(found[0].nodes)}, pair
        assert app_nodes <= set(mine[pair]) | {tuple(found[0].nodes)}, pair
    print("batched route selection matches routing.py on 12 pairs", flush=True)
    weather = G["weather"].at(when)
    via_model = model.fields(when, solar, weather, wind_direction_deg=270).utci
    air = np.full(model.valid.shape, weather.air_temp_c)
    direct = utci(air, fields.mrt, G["fields"]["K"].wind_ms(weather.wind_ms, 270, when.date()),
                  relative_humidity(air, weather.dew_point_c))
    assert np.allclose(via_model[model.valid], direct[model.valid], equal_nan=True)
    print("per-cell UTCI matches model.fields(..., wind_direction_deg)", flush=True)


# -- report -----------------------------------------------------------------------------


def summarise(records: list[dict]) -> dict:
    summary: dict = {"pairs": len(G["pairs"]), "od_buildings": OD_BUILDINGS, "seasons": {}}
    for season in SEASONS:
        rows = [r for r in records if r["season"] == season]
        if not rows:
            continue
        s: dict = {"hours": len(rows), "period": [rows[0]["when"], rows[-1]["when"]]}
        s["asos_ws_mean"] = float(np.mean([r["model_ws"] for r in rows]))
        s["asos_ws_below_floor"] = float(np.mean([r["model_ws"] < 0.5 for r in rows]))
        s["k_mean"] = float(np.mean([r["k_mean"] for r in rows]))
        s["k_p5_p95"] = [float(np.mean([r["k_p5"] for r in rows])), float(np.mean([r["k_p95"] for r in rows]))]
        s["cells_at_floor_K"] = float(np.mean([r["wind_cells_at_floor_K"] for r in rows]))
        s["utci"] = {}
        for name in VARIANTS:
            u = [r["utci"][name] for r in rows]

            def avg(key):
                values = [x[key] for x in u if x[key] is not None]
                return float(np.mean(values)) if values else None

            s["utci"][name] = {
                k: avg(k) for k in ("mean", "p5", "p95", "delta_mean", "delta_sun", "delta_shade", "sun_minus_shade")
            }
            s["utci"][name]["spread_p95_p5"] = float(np.mean([x["p95"] - x["p5"] for x in u]))
            s["utci"][name]["hourly_delta_mean_p5_p50_p95"] = np.percentile([x["delta_mean"] for x in u], [5, 50, 95]).tolist()
        for part in ("sun", "shade"):
            hist = np.sum([r["utci"]["K"][f"hist_{part}"] for r in rows], axis=0)
            centres = (DELTA_BINS[:-1] + DELTA_BINS[1:]) / 2
            cdf = np.cumsum(hist) / max(hist.sum(), 1)
            s["utci"]["K"][f"cell_delta_{part}_p5_p50_p95"] = [float(centres[np.searchsorted(cdf, q)]) for q in (0.05, 0.5, 0.95)]
        s["routes"] = {}
        pairs = len(G["pairs"])
        for key in rows[0]["routes"]:
            changed = np.array([r["routes"][key]["changed"] for r in rows])
            s["routes"][key] = {
                "pair_hours_changed": float(changed.sum() / (pairs * len(rows))),
                "pair_hours_coolest_changed": float(sum(r["routes"][key]["coolest_changed"] for r in rows) / (pairs * len(rows))),
                "pair_hours_changed_over_10pct_length": float(sum(r["routes"][key]["big"] for r in rows) / (pairs * len(rows))),
                "hours_any_pair_changed": float(np.mean(changed > 0)),
                "pair_hours_not_shortest_reference": float(sum(r["routes"][key]["active"] for r in rows) / (pairs * len(rows))),
            }
        summary["seasons"][season] = s
    return summary


def figures(records: list[dict]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = ["AppleGothic", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False
    model, field = G["model"], G["fields"]["K"]

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.4), constrained_layout=True)
    for ax, leaf, title in ((axes[0], True, "서풍(270°), 잎 있음"), (axes[1], False, "서풍(270°), 잎 없음")):
        k = field.factor(sector_of(270), leaf)
        image = ax.imshow(k, vmin=0, vmax=1, cmap="viridis")
        ax.set_title(f"풍속 계수 K — {title}")
        ax.set_xticks([])
        ax.set_yticks([])
    fig.colorbar(image, ax=axes, shrink=0.8, label="K = 칸 풍속 / ASOS 풍속")
    fig.savefig(OUT / "k_map_west.png", dpi=130)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    centres = (DELTA_BINS[:-1] + DELTA_BINS[1:]) / 2
    for ax, season in zip(axes, SEASONS):
        rows = [r for r in records if r["season"] == season]
        for part, label, colour in (("sun", "양지(sunlit ≥ 0.5)", "#d9822b"), ("shade", "그늘", "#2b6cb0")):
            hist = np.sum([r["utci"]["K"][f"hist_{part}"] for r in rows], axis=0)
            ax.plot(centres, hist / max(hist.sum(), 1), label=label, color=colour)
        ax.set_xlim(-3, 8)
        ax.set_title(f"{'여름' if season == 'summer' else '겨울'}: 칸별 바람 − 균일 바람 UTCI")
        ax.set_xlabel("ΔUTCI (°C)")
        ax.set_ylabel("칸·시각 비율 (0.1 °C 구간)")
        ax.legend()
    fig.savefig(OUT / "delta_utci_hist.png", dpi=130)
    plt.close(fig)

    summary = summarise(records)
    fig, ax = plt.subplots(figsize=(9, 4), constrained_layout=True)
    labels, values = [], []
    for season in SEASONS:
        for cost in ("app", "two_sided"):
            for name in ("K", "K_mean", "K_e3", "K_e10", "K_vs_K_mean"):
                labels.append(f"{'여름' if season == 'summer' else '겨울'}\n{'앱' if cost == 'app' else '양방향'}\n{name}")
                values.append(100 * summary["seasons"][season]["routes"][f"{cost}:{name}"]["pair_hours_changed"])
    ax.bar(range(len(values)), values, color="#4a5568")
    ax.axhline(10, color="#c53030", linestyle="--", label="H8 기준 10 %")
    ax.set_xticks(range(len(values)), [l.replace("K_vs_K_mean", "K↔K_mean") for l in labels], fontsize=6)
    ax.set_ylabel("경로가 바뀐 (시각×쌍) 비율 (%)")
    ax.legend()
    fig.savefig(OUT / "route_change.png", dpi=130)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None, help="evenly spaced subset of hours, for a quick run")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    build()
    init_shortest()
    check_against_app()
    hours = asos_hours(args.limit)
    print(f"{len(hours)} hours", flush=True)
    t0 = time.time()
    records = []
    context = mp.get_context("fork")
    with context.Pool(args.workers) as pool:
        for k, record in enumerate(pool.imap(one_hour, hours, chunksize=4)):
            if record is not None:
                records.append(record)
            if k % 200 == 0:
                print(f"  {k}/{len(hours)} ({time.time() - t0:.0f} s)", flush=True)
    records.sort(key=lambda r: r["when"])
    summary = summarise(records)
    morph = {
        f"{sector}:{'leaf' if leaf else 'bare'}": G["fields"]["K"].morphometry(sector, leaf)
        for sector in (0, 4, 8, 12) for leaf in (True, False)
    }
    summary["morphometry"] = morph
    summary["sector_share"] = {
        season: np.bincount([r["sector"] if r["sector"] is not None else SECTORS for r in records if r["season"] == season],
                            minlength=SECTORS + 1).tolist()
        for season in SEASONS
    }
    (OUT / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    slim = [{k: v for k, v in r.items() if k != "utci"} | {"utci": {n: {k: v for k, v in u.items() if not k.startswith("hist")}
                                                                 for n, u in r["utci"].items()}} for r in records]
    (OUT / "hours.json").write_text(json.dumps(slim, ensure_ascii=False, default=float), encoding="utf-8")
    figures(records)
    print(json.dumps({s: v["routes"] for s, v in summary["seasons"].items()}, indent=1))
    print(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
