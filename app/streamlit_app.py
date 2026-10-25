"""Euro Warming Monitor (the TempRadar project): how has the temperature changed
where you live?

The "synoptic chart" design: chart paper, graphite ink, Barlow, and warming stripes
under the history chart (theme in .streamlit/config.toml).

Run from the project folder (with .venv active):
    streamlit run app/streamlit_app.py
Reads the marts in Postgres, or exported Parquet files (see app/data.py).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import charts
from data import BASES, SQL, map_sql, open_source

load_dotenv()
st.set_page_config(page_title="Euro Warming Monitor", page_icon="🌡️", layout="wide")


# --- data, cached ------------------------------------------------------------------


@st.cache_resource
def source():
    return open_source()


@st.cache_data(ttl="1h", show_spinner=False)
def query(name: str, **params) -> pd.DataFrame:
    return source().query(SQL[name], **params)


@st.cache_data(ttl="1h", show_spinner=False)
def search(q: str) -> pd.DataFrame:
    return source().search(q, limit=15)


# The place shown first: Paris (its GeoNames id), or the biggest place in the data when
# Paris isn't in it (e.g. the small test area in CI)
DEFAULT_PLACE = 2988507


@st.cache_data(ttl="1h", show_spinner=False)
def default_place() -> int:
    if not source().query(SQL["place"], city_id=DEFAULT_PLACE).empty:
        return DEFAULT_PLACE
    df = source().query("select city_id from dim_city order by population desc nulls last limit 1")
    return int(df["city_id"].iloc[0])


@st.cache_data(ttl="1h", show_spinner=False)
def data_until() -> pd.Timestamp:
    """The newest month in the data (its first day)."""
    df = source().query(
        "select max(cast(year as integer) * 100 + month) as ym"
        " from mart_grid_latest_period where month > 0"
    )
    ym = int(df["ym"].iloc[0])
    return pd.Timestamp(ym // 100, ym % 100, 1)


@st.cache_data(ttl="1h", show_spinner="Loading the map…")
def map_squares(base: str, month: int) -> pd.DataFrame:
    return source().query(map_sql(base), month=month).dropna(subset=["value"])


@st.cache_data(ttl="1h", show_spinner=False)
def colour_limit(base: str, annual: bool) -> float:
    """One colour scale for all twelve months, so switching months keeps colours
    comparable, and its own for the year, whose changes are much smaller: wide enough
    for all but the most extreme 2% of cells."""
    months = "month = 0" if annual else "month > 0"
    values = source().query(
        f"select {BASES[base]} as v from mart_grid_latest_period where {months}"
    )["v"]
    limit = float(np.nanpercentile(np.abs(values), 98))
    return max(0.5, math.ceil(limit * 2) / 2)  # rounded up to 0.5 °C


def fmt_population(n) -> str:
    return "" if pd.isna(n) else f"{int(n):,}".replace(",", " ")


def coordinates(lat: float, lon: float) -> str:
    return f"{abs(lat):.2f}°{'N' if lat >= 0 else 'S'}, {abs(lon):.2f}°{'E' if lon >= 0 else 'W'}"


def signed(change: float, digits: int = 1) -> str:
    """A change in °C with its sign; ±0.0 °C when it rounds to zero."""
    change = round(change, digits) + 0.0  # + 0.0 turns -0.0 into 0.0
    return f"±{0:.{digits}f} °C" if change == 0 else f"{change:+.{digits}f} °C"


def on_phone() -> bool:
    """Whether the browser says it is a phone (its User-Agent has "Mobi"). Streamlit
    can't measure the screen, and the map needs a fixed width in pixels."""
    return "Mobi" in (st.context.headers.get("User-Agent") or "")


def change_text(change: float, base: str = "", suffix: str = "", digits: int = 1) -> str:
    """A change as coloured text: rust with ▲ when warmer, blue with ▼ when colder (the
    chart's colours), graphite with no arrow when it rounds to zero. Followed by
    "vs <base>", or by `suffix` when given."""
    change = round(change, digits) + 0.0  # + 0.0 turns -0.0 into 0.0
    if change > 0:
        text, colour = f"▲ {signed(change, digits)}", charts.WARMER
    elif change < 0:
        text, colour = f"▼ {signed(change, digits)}", charts.COLDER
    else:
        text, colour = signed(change, digits), charts.NEUTRAL
    after = suffix or f"vs {base}"
    return f"<span style='font-size:0.85rem;font-weight:500;color:{colour}'>{text} {after}</span>"


def metric_html(label: str, value: str, second: str, title: str = "") -> str:
    """A big number with its graphite label above and its change below."""
    return (
        f"<div title='{title}' style='margin-bottom:1.25rem'>"
        f"<div style='font-size:0.85rem;color:{charts.AXIS_COLOUR}'>{label}</div>"
        f"<div style='font-size:2.125rem;font-weight:500;line-height:1.25'>{value}</div>"
        f"<div>{second}</div></div>"
    )


CHART_HEIGHT = 356  # the history chart: its stripes end level with the third number's change line


CELL_HEIGHT_KM = 27.8  # 0.25° of latitude


def cell_width_km(lat: float) -> float:
    """0.25° of longitude: narrower towards the poles."""
    return CELL_HEIGHT_KM * math.cos(math.radians(lat))


def period_label(month: int, year: int) -> str:
    return str(year) if month == 0 else f"{pd.Timestamp(2000, month, 1):%B} {year}"


# --- what is shown: a place or a grid cell -----------------------------------------

# ("place", city_id) or ("square", grid_point_id). Also kept in the address
# (?place=... or ?cell=...), so a link opens the same view again.
SELECTION = "selection"


def map_key() -> str:
    # A new key gives a fresh map without a selected square
    return f"map-{st.session_state.get('map_version', 0)}"


def clear_map_selection() -> None:
    st.session_state["map_version"] = st.session_state.get("map_version", 0) + 1


# A new map also starts from its first view, so the home button uses the same
reset_map_view = clear_map_selection


def on_map_click() -> None:
    objects = st.session_state[map_key()].selection.objects.get("squares", [])
    if objects:
        lat, lon = objects[0]["lat"], objects[0]["lon"]
        # Same id as the grid_point_id macro in dbt
        st.session_state[SELECTION] = ("square", f"{round(lat * 100)}_{round(lon * 100)}")
        st.session_state["typed"] = ""  # a click replaces the search


def on_pick(key: str) -> None:
    st.session_state[SELECTION] = ("place", st.session_state[key])
    clear_map_selection()


def on_type() -> None:
    st.session_state["new_search"] = True


if SELECTION not in st.session_state:
    cell = st.query_params.get("cell") or st.query_params.get("square")  # older links
    if cell:
        st.session_state[SELECTION] = ("square", cell)
    elif st.query_params.get("place", "").isdigit():
        st.session_state[SELECTION] = ("place", int(st.query_params["place"]))
    else:
        st.session_state[SELECTION] = ("place", default_place())


# --- header ---------------------------------------------------------------------------

st.title("Euro Warming Monitor")
st.write(
    "Compare current monthly and annual temperatures with their historical values for any "
    "location in Europe."
)

# Less empty space above the title, so the map fits on a laptop screen, and the map's
# home button placed (Streamlit has no setting for these)
st.html(
    """<style>
    [data-testid="stMainBlockContainer"] { padding-top: 2.5rem; }
    /* The home button level with Streamlit's fullscreen button over the map */
    .st-key-home { margin-bottom: -1rem; }
    /* Figures in columns, so temperatures line up as they change */
    [data-testid="stMain"] { font-variant-numeric: tabular-nums; }
    /* The chosen place's name: the largest type on the page after the title */
    .st-key-place h3 { font-size: 2.25rem; line-height: 1.1; padding-bottom: 0.25rem; }
    </style>"""
)

# --- navigation: month (or year) and base period, for the map and the charts -------------

newest = charts.MONTHS[data_until().month - 1]
period_col, base_col = st.columns([3, 1])
period = (
    period_col.segmented_control("Month or whole year", charts.PERIODS, default=newest) or newest
)
base = base_col.segmented_control("Compared with", list(BASES), default="1991–2020") or (
    "1991–2020"
)
month = 0 if period == charts.YEAR else charts.MONTHS.index(period) + 1
# A thin grey line between the navigation and the content (st.divider has wide margins)
st.html(f"<hr style='margin:0;border:none;border-top:1px solid {charts.RULE_COLOUR}'>")
base_column = "normal_c" if base == "1991–2020" else "early_normal_c"

# The map (left) and the chosen place or grid cell (right). Each is one column, so on
# a phone they stack: the search first, then the map, then everything about the place.
phone = on_phone()
search_part = st.container() if phone else None
map_part, cell_part = st.columns([0.7, 1], gap="medium")
if search_part is None:
    search_part = cell_part.container()  # on a wide screen, at the top of the right side


# --- choose a place (or click the map) ------------------------------------------------

with search_part:
    search_col, pick_col = st.columns([1, 1.4], vertical_alignment="bottom")
    typed = search_col.text_input(
        "Find a place, or click the map",
        placeholder="e.g. Lyon, Kraków",
        key="typed",
        on_change=on_type,
    )
    if typed.strip():
        results = search(typed.strip())
        if results.empty:
            pick_col.caption(f"No place matches “{typed}”.")
        else:
            # A place found by another of its names shows it: "Mons (Bergen), Wallonia, ..."
            labels = {
                int(r.city_id): (
                    r.display_name.replace(r.city_name, f"{r.city_name} ({r.alias})", 1)
                    if isinstance(r.alias, str)
                    else r.display_name
                )
                + f"  ·  {fmt_population(r.population)}"
                for r in results.itertuples()
            }
            key = f"pick:{typed.strip()}"
            pick_col.selectbox(
                "Matching places",
                options=list(labels),
                format_func=labels.get,
                key=key,
                on_change=on_pick,
                args=(key,),
            )
            if st.session_state.pop("new_search", False):  # a new search shows its best match
                st.session_state[SELECTION] = ("place", st.session_state[key])
                clear_map_selection()


# --- the chosen place or grid cell ---------------------------------------------------------

kind, value = st.session_state[SELECTION]
place = None
if kind == "place":
    place_df = query("place", city_id=value)
    if place_df.empty:
        place_df = query("place", city_id=default_place())
    place = place_df.iloc[0].to_dict()
    gp = place["grid_point_id"]
else:
    gp = value
    largest = query("largest_place_in_square", gp=gp)
    if not largest.empty:  # a clicked cell shows its largest town
        place = query("place", city_id=int(largest["city_id"].iloc[0])).iloc[0].to_dict()

square_df = query("square", gp=gp)
if square_df.empty:
    st.warning("That grid cell is not in the data.")
    st.stop()
square = square_df.iloc[0]

st.query_params.clear()
if place:
    st.query_params["place"] = str(place["city_id"])
else:
    st.query_params["cell"] = gp

squares = map_squares(base, month)
view, map_width, map_height = charts.map_frame(
    squares, max_width=charts.MAP_PHONE_WIDTH if phone else charts.MAP_MAX_WIDTH
)
limit = colour_limit(base, annual=month == 0)

latest_all = query("latest", gp=gp).set_index("month")  # every month (1-12) and the year (0)
latest = latest_all.loc[month]
year = int(latest["year"])
label = period_label(month, year)
short_month = f"{pd.Timestamp(2000, month, 1):%b}" if month else ""
full_month = f"{pd.Timestamp(2000, month, 1):%B}" if month else ""
base_value = float(latest[base_column])
history_all = query("history", gp=gp)  # every year of every month (1-12) and the year (0)


# --- left: the map --------------------------------------------------------------------------

with map_part:
    st.markdown(
        # The colour scale sits where the subtitle would
        charts.title_html(f"{label} compared to {full_month + ' ' if month else ''}{base} average")
        + charts.legend_html(limit),
        unsafe_allow_html=True,
    )
    # Between the colour scale and the map, on the left; Streamlit's fullscreen button
    # appears at the right of the same row when the pointer is over the map
    st.button(
        ":material/home:",
        key="home",
        help="Back to the starting view after zooming or panning",
        type="tertiary",
        on_click=reset_map_view,
    )
    marker = place or {"lat": square["lat"], "lon": square["lon"]}
    map_change = float(latest["temp_c"]) - base_value
    st.pydeck_chart(
        charts.change_map(squares, limit, marker, view, signed(map_change), base),
        width=map_width,  # the grid's own shape, so no empty margins
        height=map_height,
        on_select=on_map_click,
        selection_mode="single-object",
        key=map_key(),
    )


# --- right: name, two numbers, and the history behind them ---------------------------------

where = (
    f"{place['distance_to_grid_point_km']:.1f} km from {place['city_name']} to its centre"
    if place
    else "no town of 1,000+ people in it"
)

with cell_part:
    with st.container(key="place"):
        st.subheader(place["display_name"] if place else "A grid cell with no towns")
    st.caption(
        f"Grid cell centred at {coordinates(square['lat'], square['lon'])}, about "
        f"{cell_width_km(square['lat']):.0f} × {CELL_HEIGHT_KM:.0f} km "
        f"({square['area_km2']:.0f} km²), {where}."
        + (
            f" Mostly sea ({square['land_fraction']:.0%} land)."
            if square["land_fraction"] < 0.5
            else ""
        )
    )

    # Three numbers: the latest value, the 10-year mean up to it, the trend since 1940
    if month:
        trend = query("trend", gp=gp).set_index("month").loc[month]
        name = f"{pd.Timestamp(2000, month, 1):%B}"
    else:
        trend = query("annual_trend", gp=gp).iloc[0]
        name = "Year"
    period_history = history_all[history_all["month"] == month]
    # The single years, for the warming stripes
    years = period_history.rename(columns={"temp_c": "value", "is_preliminary": "preliminary"})[
        ["year", "value", "preliminary"]
    ]
    # The 10-year averages, from the first complete window on
    windows = (
        period_history.dropna(subset=["rolling_avg_c"])
        .rename(columns={"year": "window_end_year"})[
            ["rolling_start_year", "window_end_year", "rolling_avg_c", "rolling_is_preliminary"]
        ]
        .rename(
            columns={
                "rolling_start_year": "window_start_year",
                "rolling_avg_c": "avg_temp_c",
                "rolling_is_preliminary": "is_preliminary",
            }
        )
        .astype({"window_start_year": int})
    )
    window = windows.iloc[-1]
    window_years = f"{int(window['window_start_year'])}–{int(window['window_end_year'])}"
    trend_from, trend_to = int(trend["first_year"]), int(trend["last_year"])
    decades = (trend_to - trend_from) / 10
    trend_total = float(trend["warming_c_per_decade"]) * decades

    # Two columns: the three numbers stacked, and the chart beside them
    numbers_col, chart_col = st.columns([1, 2.6], gap="medium")
    numbers_col.markdown(
        metric_html(
            (f"{short_month} {year}" if month else f"{year} (full year)")
            + (" (preliminary)" if latest["is_preliminary"] else ""),
            f"{latest['temp_c']:.1f} °C",
            change_text(float(latest["temp_c"]) - base_value, base),
        )
        + metric_html(
            f"{short_month} {window_years} average".strip(),
            f"{window['avg_temp_c']:.1f} °C",
            change_text(float(window["avg_temp_c"]) - base_value, base),
        )
        + metric_html(
            # the change along the trend line, not one year minus another
            f"{short_month} since {trend_from}" if month else f"Annual, since {trend_from}",
            # The whole change along the trend line, then its rate per decade
            f"{trend_total:+.1f} °C",
            change_text(float(trend["warming_c_per_decade"]), suffix="per decade", digits=2),
            title=f"Straight-line trend of {'every ' + name if month else 'the annual means'} "
            f"from {trend_from} to {trend_to}: its rate per decade × "
            f"{decades:.1f} decades",
        ),
        unsafe_allow_html=True,
    )
    # The same explanations as the hover texts, for phones (which have no hover) and
    # first-time readers
    every = f"every {name}" if month else "every year"
    with numbers_col.popover("How to read this", icon=":material/info:"):
        st.markdown(
            (
                f"**{label}**: the latest {name} compared to the {name} average of {base}."
                if month
                else f"**{year}**: the latest full year compared to the annual average of {base}."
            )
            + (
                " It is preliminary: ERA5's early release, which final values replace about "
                "two to three months later (dotted on the chart)."
                if latest["is_preliminary"]
                else ""
            )
            + "\n\n"
            + "**10-year average**: the "
            + (f"{window_years} {name} mean" if month else f"{window_years} annual mean")
            + ", calculated for the latest finished period. The chart shows the 10-year "
            "rolling average, while the stripes below show each single year's value.\n\n"
            f"**Since {trend_from}**: the warming along a straight line fitted through "
            f"{every} since {trend_from}: {signed(float(trend['warming_c_per_decade']), 2)} "
            f"per decade × {decades:.1f} decades.\n\n"
            "**One value per grid cell**: ERA5 gives one average for each 0.25° cell (about "
            "28 km tall), so mountains, coasts and city heat are smoothed out."
        )

    # The 10-year mean over time, against the base period, with the single years
    # under it as warming stripes
    chart_col.markdown(
        charts.title_html(
            f"{name if month else 'Annual'} temperature, 10-year average",
            "°C, the stripes show each single year",
        ),
        unsafe_allow_html=True,
    )
    history = windows.rename(
        columns={
            "window_end_year": "year",
            "avg_temp_c": "value",
            "is_preliminary": "preliminary",
        }
    )
    history["label"] = (
        (f"{name} " if month else "")
        + history["window_start_year"].astype(str)
        + "–"
        + history["year"].astype(str)
    )
    chart_col.altair_chart(
        charts.history_vs_base(
            history[["year", "value", "label", "preliminary"]],
            base_value,
            base,
            # Shorter by the stripes under it, so the pair stays beside the numbers
            CHART_HEIGHT - (charts.STRIPES_HEIGHT + 30),
            stripes=years,
        ),
        width="stretch",
        key="history",
    )


# --- credits -----------------------------------------------------------------------------

st.divider()
st.caption(
    "Data: ERA5 monthly averaged reanalysis, 2 m temperature (Hersbach et al., 2023, "
    "Copernicus Climate Change Service Climate Data Store, DOI 10.24381/cds.f17050d7). "
    "Contains modified Copernicus Climate Change Service information. "
    "Places: GeoNames (geonames.org, CC BY 4.0). "
    "Built with Python, PostgreSQL/PostGIS and dbt."
)
