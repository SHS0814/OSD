"""Sensor test: how campus sensor temperatures relate to 청주 ASOS and to the v1 shade model.

Reads every CSV/JSON in data/raw/sensors/ (services/sensors.py), flags bad
readings, and for each sensor answers the questions that decide whether v2
should correct air temperature from sensors (docs/04-data-usage-plan.md §5):

1. How far is the sensor from ASOS, by day and by night? The night offset
   has no sun in it, so it is the sensor's own bias (enclosure, the Pi's heat,
   a wall nearby), not a campus microclimate.
2. Does what is left in the daytime follow the sun the model says reaches the
   sensor's cell (sunlit fraction × global irradiance), and with what lag?
3. Does a correction Ta = Ta_ASOS + a + b·sunlit·G predict held-out data
   better than ASOS alone? Held out by sensor when there are at least
   MIN_SENSORS_FOR_LOSO sensors, otherwise by day.

Writes docs/sensor-test/results.md plus figures; nothing in data/ changes.

    PYTHONPATH=backend python scripts/analyze_sensors.py [data/raw/sensors]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from shapely.geometry import Point, shape  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.repository import BuildingRepository  # noqa: E402
from app.services import sensors  # noqa: E402
from app.services.geometry import to_projected  # noqa: E402
from app.services.microclimate import MicroclimateModel  # noqa: E402
from app.services.solar import calculate_solar_position  # noqa: E402
from app.services.surfaces import load_land_cover, load_street_trees  # noqa: E402
from app.services.terrain import Terrain  # noqa: E402
from app.services.weather import WeatherStore, WeatherUnavailable  # noqa: E402

OUTPUT_DIR = ROOT / "docs" / "sensor-test"
STEP = timedelta(minutes=10)
MIN_SENSORS_FOR_LOSO = 3
# Night for the offset: well after sunset and before dawn, when the sensor,
# the ground and the air have stopped exchanging sunlight.
NIGHT_HOURS = range(0, 6)
MAX_LAG_STEPS = 6  # ±60 min
# Sun versus shade: a sensor counts as sunny or shaded by the model's mean
# sunlit fraction at its point over 10-15 h.
SUNNY_MIN = 0.6
SHADED_MAX = 0.3
SUN_BINS = [-1, 0, 200, 400, 600, 1100]  # W/m², hour mean from ASOS icsr


def load_campus():
    collection = json.loads(settings.campus_boundary_path.read_text(encoding="utf-8"))
    return shape(collection["features"][0]["geometry"])


def build_model(buildings) -> MicroclimateModel:
    ground, canopies = load_land_cover(settings.landcover_data_path)
    return MicroclimateModel(
        load_campus(),
        buildings,
        terrain=Terrain(settings.terrain_data_path),
        ground=ground,
        canopies=canopies
        + load_street_trees(settings.tree_canopy_data_path)
        + load_street_trees(settings.street_trees_data_path),
    )


def nearest_building(buildings, lon: float, lat: float) -> tuple[str, float]:
    point = to_projected(Point(lon, lat))
    best = min(buildings, key=lambda b: to_projected(b.geometry).distance(point))
    return best.name, to_projected(best.geometry).distance(point)


def open_cell(model: MicroclimateModel, cell):
    """The sensor's cell, or the nearest open-ground cell within 20 m when it is mostly building."""
    if cell is None:
        return None
    row, col = cell
    for reach in range(3):
        candidates = [
            (abs(dr) + abs(dc), (row + dr, col + dc))
            for dr in range(-reach, reach + 1)
            for dc in range(-reach, reach + 1)
            if 0 <= row + dr < model.grid.rows and 0 <= col + dc < model.grid.cols
            and model.valid[row + dr, col + dc]
        ]
        if candidates:
            return min(candidates)[1]
    return None


def model_series(
    model: MicroclimateModel, store: WeatherStore, cells: dict, points: dict, start, end
) -> dict[str, pd.DataFrame]:
    """Every STEP: ASOS state and the model's sun at each sensor.

    ``sunlit`` is traced from the sensor's own 2 m pixel: at the edge of a wood
    the 10 m cell mean would dilute the shade the sensor actually sits in.
    The sky view factor is the cell's.
    """
    names = list(cells)
    x = np.array([points[name][0] for name in names])
    y = np.array([points[name][1] for name in names])
    rows: dict[str, list] = {name: [] for name in names}
    when = start.floor("10min").to_pydatetime()
    end = end.floor("10min").to_pydatetime()
    sky_cache: dict = {}
    while when <= end:
        try:
            weather = store.at(when)
        except WeatherUnavailable:
            when += STEP
            continue
        solar = calculate_solar_position(when, settings.campus_latitude, settings.campus_longitude)
        day = when.date()
        if day not in sky_cache:
            sky_cache[day] = model.sky_view(day)
        sunlit = model.sunlit_at(solar, day, x, y)
        for index, name in enumerate(names):
            rows[name].append(
                {
                    "time": pd.Timestamp(when),
                    "kma_temp": weather.air_temp_c,
                    "ghi": weather.global_horizontal,
                    "cloud": weather.cloud_fraction,
                    "wind": weather.wind_ms,
                    "solar_altitude": solar.altitude,
                    "sunlit": float(sunlit[index]),
                    "sky_view": float(sky_cache[day][cells[name]]),
                }
            )
        when += STEP
    frames = {}
    for name, records in rows.items():
        frame = pd.DataFrame(records)
        frame["sun_load"] = frame["sunlit"] * frame["ghi"]  # W/m² reaching an open sensor
        frames[name] = frame
    return frames


def fit_line(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    slope, intercept = np.polyfit(x, y, 1)
    return float(intercept), float(slope)


def rmse(error: pd.Series) -> float:
    return float(np.sqrt(np.mean(np.square(error))))


def cross_validate(table: pd.DataFrame, group: str) -> pd.DataFrame:
    """Held-out RMSE of three air-temperature estimates for the sensor reading.

    M0: ASOS as is (what v1 uses everywhere).
    M1: ASOS + a constant offset learnt from the other groups.
    M2: ASOS + a + b·sun_load learnt from the other groups.
    """
    results = []
    for held, test in table.groupby(group):
        train = table[table[group] != held]
        if train.empty:
            continue
        offset = float(train["dT"].mean())
        a, b = fit_line(train["sun_load"].to_numpy(), train["dT"].to_numpy())
        # The same on device-corrected temperatures (each sensor minus its own
        # night offset): what a map can use, since the offset belongs to the
        # device, not the place.
        c_offset = float(train["residual"].mean())
        ca, cb = fit_line(train["sun_load"].to_numpy(), train["residual"].to_numpy())
        results.append(
            {
                group: held,
                "n": len(test),
                "M0_rmse": rmse(test["temp"] - test["kma_temp"]),
                "M1_rmse": rmse(test["temp"] - (test["kma_temp"] + offset)),
                "M2_rmse": rmse(test["temp"] - (test["kma_temp"] + a + b * test["sun_load"])),
                "C0_rmse": rmse(test["residual"]),
                "C1_rmse": rmse(test["residual"] - c_offset),
                "C2_rmse": rmse(test["residual"] - (ca + cb * test["sun_load"])),
                "C2_slope_per_100Wm2": cb * 100,
            }
        )
    return pd.DataFrame(results)


def lag_correlation(table: pd.DataFrame) -> pd.Series:
    """Correlation of the daytime residual with sun_load shifted by k steps (k>0: sensor lags the sun)."""
    day = table[table["solar_altitude"] > 5].copy()
    out = {}
    for k in range(-MAX_LAG_STEPS, MAX_LAG_STEPS + 1):
        shifted = table["sun_load"].shift(k).reindex(day.index)
        valid = shifted.notna() & day["residual"].notna()
        out[k * int(STEP.total_seconds() // 60)] = float(np.corrcoef(day.loc[valid, "residual"], shifted[valid])[0, 1])
    return pd.Series(out, name="r")


def sun_versus_shade(hourly_residuals: dict, midday_sunlit: dict) -> tuple[pd.DataFrame, str]:
    """Sunny-group minus shaded-group device-corrected temperature, by sunshine.

    Both groups carry the same hardware, and at night (no sun) the difference
    should be ~0. With sun it grows by the enclosure's radiative heating plus
    any real sun/shade air difference, so it bounds the enclosure error from
    above.
    """
    sunny = [name for name, value in midday_sunlit.items() if value >= SUNNY_MIN]
    shaded = [name for name, value in midday_sunlit.items() if value <= SHADED_MAX]
    if not sunny or not shaded:
        return pd.DataFrame(), f"Needs both sunny (≥{SUNNY_MIN}) and shaded (≤{SHADED_MAX}) sensors; skipped."
    residual = pd.DataFrame({name: frame["residual"] for name, frame in hourly_residuals.items()})
    radiation = pd.concat([frame["G"] for frame in hourly_residuals.values()]).groupby(level=0).first()
    difference = (residual[sunny].mean(axis=1) - residual[shaded].mean(axis=1)).dropna()
    radiation = radiation.reindex(difference.index)
    table = difference.groupby(pd.cut(radiation, SUN_BINS)).agg(["mean", "std", "count"])
    table.index = [f"{int(max(b.left, 0))}–{int(b.right)}" if b.left >= 0 else "0 (night)" for b in table.index]
    table.index.name = "G (W/m²)"
    day = radiation > 50
    slope, intercept = np.polyfit(radiation[day] / 100.0, difference[day], 1) if day.sum() > 2 else (np.nan, np.nan)
    note = (
        f"Sunny: {', '.join(sunny)}. Shaded: {', '.join(shaded)}. "
        f"Daytime fit: difference ≈ {intercept:+.2f} + {slope:+.2f}·G/100 °C."
    )
    return table, note


def plot_sensor(name: str, table: pd.DataFrame, hourly: pd.DataFrame, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(13, 10), sharex=False, gridspec_kw={"height_ratios": [3, 2, 2]})
    ax = axes[0]
    ax.plot(table["time"], table["temp"], lw=0.9, label=f"{name} (10-min median)")
    ax.plot(table["time"], table["kma_temp"], lw=0.9, label="ASOS 131 (interpolated)")
    ax.plot(table["time"], table["kma_temp"] + table.attrs["night_offset"], lw=0.7, ls="--",
            color="gray", label="ASOS + night offset")
    ax.set_ylabel("°C")
    ax.legend(loc="upper left", fontsize=8)
    twin = ax.twinx()
    twin.fill_between(table["time"], table["sun_load"], color="orange", alpha=0.2, lw=0)
    twin.set_ylabel("sunlit × G (W/m²)")
    ax.set_title(f"{name}: sensor vs ASOS, with the model's sun at the sensor cell")

    ax = axes[1]
    hourly = hourly.copy()
    hourly["hour"] = hourly["time"].dt.hour
    data = [hourly.loc[hourly["hour"] == h, "dT"].to_numpy() for h in range(24)]
    ax.boxplot(data, positions=range(24), widths=0.6, showfliers=False)
    ax.set_xlabel("hour (KST, end of hour)")
    ax.set_ylabel("sensor − ASOS (°C)")
    ax.set_title("Hourly difference by hour of day")

    ax = axes[2]
    day = table[table["solar_altitude"] > 5]
    ax.scatter(day["sun_load"], day["residual"], s=4, alpha=0.4)
    ax.set_xlabel("sunlit × G at sensor cell (W/m²)")
    ax.set_ylabel("daytime residual (°C)")
    ax.set_title("Daytime residual (after night offset) vs modelled sun")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def markdown(frame: pd.DataFrame, floatfmt: int = 2) -> str:
    frame = frame.copy()
    header = "| " + " | ".join(str(c) for c in [frame.index.name or "", *frame.columns]) + " |"
    rule = "|" + "---|" * (len(frame.columns) + 1)
    lines = [header, rule]
    for index, row in frame.iterrows():
        cells = [f"{v:.{floatfmt}f}" if isinstance(v, (float, np.floating)) else str(v) for v in row]
        lines.append("| " + " | ".join([str(index), *cells]) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", type=Path, default=ROOT / "data" / "raw" / "sensors")
    args = parser.parse_args()
    args.directory = args.directory.resolve()
    # Each period of data in a folder of its own gets its own results folder.
    default = ROOT / "data" / "raw" / "sensors"
    output = OUTPUT_DIR if args.directory.resolve() == default.resolve() else OUTPUT_DIR / args.directory.name
    output.mkdir(parents=True, exist_ok=True)

    campus = load_campus()
    readings = sensors.load_directory(args.directory)
    flagged = sensors.flag_quality(readings, campus)
    site_table = sensors.sites(flagged)
    qc_table = sensors.flag_counts(flagged)
    ten_min = sensors.resample(flagged, "10min", label="left")
    hourly_sensor = sensors.resample(flagged, "1h", label="right")

    store = WeatherStore(settings.weather_data_path, settings.campus_latitude, settings.campus_longitude)
    buildings = BuildingRepository(database_url=None, snapshot_path=settings.building_data_path).list_buildings()
    model = build_model(buildings)

    kma = pd.read_csv(settings.weather_data_path)
    kma["time"] = pd.to_datetime(kma["tm"]).dt.tz_localize(sensors.TIMEZONE)
    kma = kma.set_index("time")

    cells, points, places = {}, {}, {}
    for name, site in site_table.iterrows():
        projected = to_projected(Point(site["lon"], site["lat"]))
        points[name] = (projected.x, projected.y)
        cell = open_cell(model, sensors.grid_cell(model.grid, site["lon"], site["lat"]))
        places[name] = nearest_building(buildings, site["lon"], site["lat"])
        print(f"{name}: cell {cell}, {places[name][1]:.0f} m from {places[name][0]}")
        if cell is None:
            print(f"  {name}: no open-ground model cell nearby, skipped")
            continue
        cells[name] = cell
    all_series = model_series(model, store, cells, points, site_table["start"].min(), site_table["end"].max())

    summaries, pooled, lags = [], [], {}
    hourly_residuals, midday_sunlit = {}, {}
    for name in cells:
        building, building_m = places[name]
        series = all_series[name]
        table = ten_min[ten_min["sensor"] == name].merge(series, on="time", how="inner")
        table["dT"] = table["temp"] - table["kma_temp"]

        hourly = hourly_sensor[hourly_sensor["sensor"] == name].set_index("time")
        hourly = hourly.join(kma[["ta", "icsr"]], how="inner").reset_index()
        hourly["dT"] = hourly["temp"] - hourly["ta"]
        night = hourly[hourly["time"].dt.hour.isin(NIGHT_HOURS)]
        daytime = hourly[hourly["icsr"].fillna(0) > 0]
        night_offset = float(night["dT"].median())
        table.attrs["night_offset"] = night_offset
        table["residual"] = table["dT"] - night_offset
        a, b = fit_line(hourly["ta"].to_numpy(), hourly["temp"].to_numpy())
        r_kma = float(np.corrcoef(hourly["ta"], hourly["temp"])[0, 1])
        day_rows = table[table["solar_altitude"] > 5]
        r_sun = float(np.corrcoef(day_rows["sun_load"], day_rows["residual"])[0, 1])
        lags[name] = lag_correlation(table)
        row, col = model.fine_pixel(np.array([points[name][0]]), np.array([points[name][1]]))
        under_crown = bool(model.canopy_top[row[0], col[0]] > model.ground[row[0], col[0]] + 1.1)
        midday = table[(table["time"].dt.hour >= 10) & (table["time"].dt.hour < 15)]
        clear = midday[midday["ghi"] > 400]
        midday_sunlit[name] = float(midday["sunlit"].mean())
        hourly_residuals[name] = pd.DataFrame(
            {"residual": hourly["dT"] - night_offset, "G": hourly["icsr"].fillna(0) * 1e6 / 3600}
        ).set_axis(hourly["time"])

        summaries.append(
            {
                "sensor": name,
                "nearest_building": f"{building} ({building_m:.0f} m)",
                "under_crown": "yes" if under_crown else "no",
                "midday_sunlit": midday["sunlit"].mean(),
                "clear_midday_residual": clear["residual"].mean(),
                "cell_sky_view": round(float(table["sky_view"].iloc[0]), 2),
                "hours": len(hourly),
                "dT_mean": hourly["dT"].mean(),
                "dT_night_median": night_offset,
                "dT_day_mean": daytime["dT"].mean(),
                "dT_sd": hourly["dT"].std(),
                "r_vs_asos": r_kma,
                "fit_sensor=a+b·asos": f"{a:.1f} + {b:.2f}·T",
                "r_residual_vs_sun": r_sun,
                "best_lag_min": int(lags[name].abs().idxmax()),
            }
        )
        plot_sensor(name, table, hourly, output / f"{name.replace(' ', '_')}.png")
        table["sensor"] = name
        table["day"] = table["time"].dt.date
        pooled.append(table)

    if not pooled:
        raise SystemExit("no sensor could be placed on the model grid")
    pooled_table = pd.concat(pooled, ignore_index=True)
    group = "sensor" if pooled_table["sensor"].nunique() >= MIN_SENSORS_FOR_LOSO else "day"
    cv = cross_validate(pooled_table, group)
    cv_total = cv.drop(columns=[group, "n"]).mean()
    shade_table, shade_note = sun_versus_shade(hourly_residuals, midday_sunlit)

    summary = pd.DataFrame(summaries).set_index("sensor")
    lines = [
        "# Sensor test results (generated)",
        "",
        f"Generated by `scripts/analyze_sensors.py` from `{args.directory.relative_to(ROOT)}`. "
        "Do not edit by hand; interpretation is in docs/05-sensor-test.md.",
        "",
        f"Sensors: {len(site_table)}. Weather: 청주 ASOS 131 (`{settings.weather_data_path.name}`).",
        "",
        "## Sites",
        "",
        markdown(site_table.drop(columns=["start", "end"]).assign(
            start=site_table["start"].dt.strftime("%m-%d %H:%M"), end=site_table["end"].dt.strftime("%m-%d %H:%M")
        ), 6),
        "",
        "## Quality flags (readings)",
        "",
        markdown(qc_table, 1),
        "",
        "## Sensor vs ASOS (hourly, °C)",
        "",
        markdown(summary, 2),
        "",
        f"Night = {NIGHT_HOURS.start:02d}–{NIGHT_HOURS.stop:02d} h; day = hours with ASOS radiation. "
        "Residual = 10-min sensor − ASOS − night offset; sun = model sunlit fraction at the sensor's 2 m pixel × G. "
        "under_crown: the sensor's pixel is under a mapped crown. midday = 10–15 h; clear = G > 400 W/m².",
        "",
        "## Lag correlation of the daytime residual with the modelled sun",
        "",
        markdown(pd.DataFrame(lags).T.rename_axis("sensor"), 2),
        "",
        "Columns are minutes; positive = the sensor responds after the modelled sun.",
        "",
        f"## Held-out RMSE (by {group}, 10-min, °C)",
        "",
        markdown(cv.set_index(group), 2),
        "",
        f"Mean: M0 (ASOS) {cv_total['M0_rmse']:.2f}, M1 (+offset) {cv_total['M1_rmse']:.2f}, "
        f"M2 (+a+b·sun) {cv_total['M2_rmse']:.2f}. "
        f"Device-corrected (each sensor minus its night offset): C0 (ASOS) {cv_total['C0_rmse']:.2f}, "
        f"C1 (+offset) {cv_total['C1_rmse']:.2f}, C2 (+a+b·sun) {cv_total['C2_rmse']:.2f}; "
        f"C2 slope {cv_total['C2_slope_per_100Wm2']:.2f} °C per 100 W/m².",
        "",
        "## Sunny minus shaded sensors (device-corrected, hourly, °C)",
        "",
        markdown(shade_table, 2) if not shade_table.empty else "",
        "",
        shade_note,
        "",
        "## Figures",
        "",
        *[f"![{name}]({name.replace(' ', '_')}.png)" for name in summary.index],
        "",
    ]
    (output / "results.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
