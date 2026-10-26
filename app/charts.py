"""The line chart (Altair) and the map (pydeck)."""

from __future__ import annotations

import json
import math
from functools import cache
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
YEAR = "Year"
PERIODS = [*MONTHS, YEAR]

HIGHLIGHT = "#A94A1A"  # rust, from the warm end of the map's scale
ANNUAL = "#5B6B73"  # graphite, for the base-period line on chart paper

# Diverging scale for change, colder to warmer: blue - pale - orange-brown.
# 20 steps; zero falls between the two palest
DIVERGING = [
    "#1a3399", "#2547a1", "#2f5cab", "#3770b4", "#4087bd",
    "#4a9dc7", "#5bb6d0", "#75ccd6", "#98dfd7", "#bde9cf",
    "#d6ecc0", "#e2e8a6", "#e0dd86", "#d5c861", "#c4a841",
    "#b68c2f", "#a97122", "#9c5717", "#8d3a0b", "#7f1900",
]  # fmt: skip

SEA = [203, 214, 219]  # pale chart blue for the sea

# The sea and large lakes over the study area (made by extract/make_sea_mask.py)
SEA_MASK = Path(__file__).with_name("sea.geojson")

HALF = 0.125  # half the width of a 0.25° square
# The largest map, in pixels: small enough to see whole on a laptop screen
MAP_MAX_WIDTH = 620
MAP_MAX_HEIGHT = 460
MAP_PHONE_WIDTH = 340  # on a phone: its screen less the page margins


WARMER = HIGHLIGHT  # rust
COLDER = "#2F5CAB"  # blue, from the map's palette
NEUTRAL = "#5B6B73"  # graphite, for changes that round to zero


FONT = "'IBM Plex Sans', sans-serif"  # the page's font (loaded by the theme), so charts match it
AXIS_COLOUR = "#5B6B73"  # tick labels and the x-axis line: graphite
GRID_COLOUR = "#D3DBDF"  # a shade darker than the paper
RULE_COLOUR = "#C3CDD2"  # the line under the navigation


def history_vs_base(
    points: pd.DataFrame,
    base_value: float,
    base_label: str,
    height: int,
    stripes: pd.DataFrame | None = None,
):
    """A line over the years, rust where it is above the base-period average and
    blue where below, with the average as a dashed line across the whole chart.

    `points` has columns year, value, label (shown on hover) and preliminary. Where the
    line crosses the average, a point is added exactly on it, so the colour changes
    there. The line is dotted from the last final point on, where it uses
    preliminary data. The unit is in the chart's subtitle, so the axes carry none.

    `stripes` (optional; columns year, value, preliminary) are the single years behind
    the averages. They are drawn as a band of warming stripes under the line, on the
    same time axis, coloured by their difference from the base-period average."""
    pts = points.sort_values("year").reset_index(drop=True)
    xs, ys = pts["year"].tolist(), pts["value"].tolist()
    prelim = pts["preliminary"].astype(bool).tolist()

    # Split the line into segments that lie wholly above or below the average
    rows = []
    for i in range(len(xs) - 1):
        x0, y0, x1, y1 = xs[i], ys[i], xs[i + 1], ys[i + 1]
        if (y0 - base_value) * (y1 - base_value) < 0:  # crosses the average
            xc = x0 + (base_value - y0) / (y1 - y0) * (x1 - x0)
            pieces = [((x0, y0), (xc, base_value)), ((xc, base_value), (x1, y1))]
        else:
            pieces = [((x0, y0), (x1, y1))]
        for (xa, ya), (xb, yb) in pieces:
            colour = WARMER if (ya + yb) / 2 > base_value else COLDER
            segment = len(rows)
            # dotted when it leads to a preliminary point
            style = "preliminary" if prelim[i + 1] else "final"
            rows += [
                {"segment": segment, "year": xa, "value": ya, "colour": colour, "style": style},
                {"segment": segment, "year": xb, "value": yb, "colour": colour, "style": style},
            ]
    segments = pd.DataFrame(rows)

    has_stripes = stripes is not None and not stripes.empty
    if has_stripes:
        # Each stripe spans its year, so the axis runs from the first stripe's left edge
        domain = [int(stripes["year"].min()) - 0.5, int(stripes["year"].max()) + 0.5]
        domain = [min(domain[0], min(xs)), max(domain[1], max(xs))]
    else:
        domain = [min(xs), max(xs)]
    x_scale = alt.Scale(domain=domain, nice=False)
    # With stripes, the year labels move down below them
    x = alt.X(
        "year:Q",
        title=None,
        scale=x_scale,
        axis=alt.Axis(
            format="d",
            tickCount=8,
            grid=False,
            domain=not has_stripes,
            offset=STRIPES_GAP + STRIPES_HEIGHT + 2 if has_stripes else 0,
        ),
    )
    y = alt.Y("value:Q", title=None, scale=alt.Scale(zero=False))
    line = (
        alt.Chart(segments)
        .mark_line(strokeWidth=2.5)
        .encode(
            x=x,
            y=y,
            detail="segment:N",
            color=alt.Color("colour:N", scale=None),
            strokeDash=alt.StrokeDash(
                "style:N",
                scale=alt.Scale(domain=["final", "preliminary"], range=[[1, 0], [2, 3]]),
                legend=None,
            ),
        )
    )
    hover_points = pts.assign(
        change=pts["value"] - base_value,
        label=pts["label"] + np.where(pts["preliminary"], " (preliminary)", ""),
    )
    hover = (
        alt.Chart(hover_points)
        .mark_circle(size=60, opacity=0)
        .encode(
            x=x,
            y=y,
            tooltip=[
                alt.Tooltip("label:N", title="Period"),
                alt.Tooltip("value:Q", title="°C", format=".1f"),
                alt.Tooltip("change:Q", title=f"vs {base_label}", format="+.1f"),
            ],
        )
    )
    base = (
        alt.Chart(pd.DataFrame({"value": [base_value]}))
        .mark_rule(color=ANNUAL, strokeWidth=1.5, strokeDash=[5, 4])
        .encode(y="value:Q", tooltip=[alt.Tooltip("value:Q", title=base_label, format=".1f")])
    )
    layers = [base, line, hover]
    if has_stripes:
        # Drawn under the plot as part of the same chart (a separate chart below would
        # not stretch to the column's width in Streamlit)
        layers.append(stripes_band(stripes, base_value, base_label))
    chart = alt.layer(*layers).properties(height=height)
    return (
        chart.configure(font=FONT)
        .configure_view(stroke=None)
        # Horizontal gridlines only; an x-axis line, no y-axis line or ticks
        .configure_axis(labelColor=AXIS_COLOUR, labelFontSize=12, gridColor=GRID_COLOUR)
        .configure_axisY(domain=False, ticks=False)
        .configure_axisX(domain=True, domainColor=AXIS_COLOUR, ticks=False)
    )


STRIPES_HEIGHT = 18
STRIPES_GAP = 8  # between the plot and the stripes, in pixels


def stripes_band(years: pd.DataFrame, base_value: float, base_label: str) -> alt.Chart:
    """One stripe per year, coloured on the map's blue-pale-rust scale by its difference
    from the base-period average. The scale is set by this place's own years (all but
    the most extreme 2%), so every place shows its full range, as warming stripes do.
    Placed in pixels just below the plot, on the plot's year axis."""
    years = years.sort_values("year").copy()
    change = years["value"].to_numpy(float) - base_value
    limit = max(0.5, float(np.nanpercentile(np.abs(change), 98)))
    rgb = diverging_colour(change, limit)
    years["colour"] = [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in rgb]
    years["change"] = change
    years["start"], years["end"] = years["year"] - 0.5, years["year"] + 0.5
    years["label"] = years["year"].astype(int).astype(str) + np.where(
        years["preliminary"].astype(bool), " (preliminary)", ""
    )
    return (
        alt.Chart(years)
        .mark_rect()
        .encode(
            # No axis of its own: it shares the line's (axis=None here would hide that too)
            x=alt.X("start:Q", title=None),
            x2="end:Q",
            # From the plot's bottom edge as drawn ("height"), not a fixed number of
            # pixels: Streamlit fits the chart to its box, so the plot comes out shorter
            # than the height asked for, and stripes placed below that are cut off
            y=alt.value({"expr": f"height + {STRIPES_GAP}"}),
            y2=alt.value({"expr": f"height + {STRIPES_GAP + STRIPES_HEIGHT}"}),
            color=alt.Color("colour:N", scale=None),
            tooltip=[
                alt.Tooltip("label:N", title="Year"),
                alt.Tooltip("value:Q", title="°C", format=".1f"),
                alt.Tooltip("change:Q", title=f"vs {base_label}", format="+.1f"),
            ],
        )
    )


def title_html(title: str, subtitle: str = "") -> str:
    """A chart's title and its graphite subtitle (which holds the unit)."""
    html = f"<div style='font-weight:600;font-size:1rem'>{title}</div>"
    if subtitle:
        html += f"<div style='color:{AXIS_COLOUR};font-size:0.85rem'>{subtitle}</div>"
    return html


def diverging_colour(values: np.ndarray, limit: float) -> np.ndarray:
    """RGB (0-255) for each value on the blue-pale-orange scale, ±limit at the ends."""
    stops = np.array([[int(h[i : i + 2], 16) for i in (1, 3, 5)] for h in DIVERGING], float)
    position = np.clip((np.asarray(values, float) / limit + 1) / 2, 0, 1) * (len(stops) - 1)
    lower = np.floor(position).astype(int).clip(0, len(stops) - 2)
    frac = (position - lower)[:, None]
    return (stops[lower] * (1 - frac) + stops[lower + 1] * frac).round().astype(int)


def _mercator(lat: float) -> float:
    """Height of a latitude on the (Web Mercator) map, in degrees."""
    return math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def _inverse_mercator(y: float) -> float:
    return math.degrees(2 * math.atan(math.exp(math.radians(y))) - math.pi / 2)


def map_frame(
    squares: pd.DataFrame, max_width: int = MAP_MAX_WIDTH
) -> tuple[pdk.ViewState, int, int]:
    """A view, width and height that fit the study area exactly: the map has the
    area's shape as drawn (Web Mercator), as large as fits max_width x MAP_MAX_HEIGHT."""
    south, north = squares["lat"].min() - HALF, squares["lat"].max() + HALF
    west, east = squares["lon"].min() - HALF, squares["lon"].max() + HALF
    y_south, y_north = _mercator(south), _mercator(north)

    # Pixels per degree (of longitude, and of Mercator height): the tighter limit wins
    scale = min(max_width / (east - west), MAP_MAX_HEIGHT / (y_north - y_south))
    width = round(scale * (east - west))
    height = round(scale * (y_north - y_south))
    # deck.gl maps draw the whole world 512 pixels wide at zoom 0
    zoom = math.log2(scale * 360 / 512)
    view = pdk.ViewState(
        latitude=_inverse_mercator((y_south + y_north) / 2),  # centre as drawn on the map
        longitude=(east + west) / 2,
        zoom=zoom,
        min_zoom=zoom,  # no zooming out past the whole area; zooming in is free
    )
    return view, width, height


@cache
def sea_mask() -> dict | None:
    """The sea outline, read once; None when the file is missing (the map then has none)."""
    return json.loads(SEA_MASK.read_text(encoding="utf-8")) if SEA_MASK.exists() else None


def change_map(
    squares: pd.DataFrame,
    limit: float,
    place: dict,
    view: pdk.ViewState,
    place_label: str,
    base_label: str,
) -> pdk.Deck:
    """Every square coloured by its change, with the chosen place marked and labelled.
    Hovering a cell shows its change against the base period and where it is."""
    squares = squares.copy()
    squares[["r", "g", "b"]] = diverging_colour(squares["value"].to_numpy(), limit)
    squares["a"] = 204  # 20% transparent: the base map shows through a little
    # The hover text's number, like the rest of the page: one decimal, ±0.0 at zero
    rounded = squares["value"].round(1) + 0.0
    squares["label"] = ["±0.0 °C" if v == 0 else f"{v:+.1f} °C" for v in rounded]

    # The square's corners are computed in the browser from its centre, which
    # keeps the data sent to it small
    corners = (
        f"[[lon - {HALF}, lat - {HALF}], [lon + {HALF}, lat - {HALF}], "
        f"[lon + {HALF}, lat + {HALF}], [lon - {HALF}, lat + {HALF}]]"
    )
    squares_layer = pdk.Layer(
        "PolygonLayer",
        id="squares",  # clicks report the square under this name
        data=squares[["lat", "lon", "r", "g", "b", "a", "label"]],
        get_polygon=corners,
        get_fill_color="[r, g, b, a]",
        stroked=False,
        pickable=True,
        auto_highlight=True,
        highlight_color=[0, 0, 0, 70],  # darken the square under the pointer
    )
    place_layer = pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame([{"lat": place["lat"], "lon": place["lon"]}]),
        get_position="[lon, lat]",
        get_radius=12000,
        radius_min_pixels=5,
        radius_max_pixels=8,
        get_fill_color=[247, 249, 249],  # a paper-white dot with an ink ring
        get_line_color=[24, 38, 46],
        line_width_min_pixels=2,
        stroked=True,
    )

    # The chosen square's value, written next to its dot
    label_layer = pdk.Layer(
        "TextLayer",
        data=pd.DataFrame([{"lat": place["lat"], "lon": place["lon"], "text": place_label}]),
        get_position="[lon, lat]",
        get_text="text",
        get_size=13,
        get_color=[24, 38, 46],  # ink
        get_pixel_offset=[0, -18],
        # In quotes: pydeck reads any other text as an expression, and without them the
        # label isn't drawn
        font_family="'IBM Plex Sans, sans-serif'",
        # deck.gl draws only ASCII unless told otherwise, and the label has ° and ±:
        # "auto" takes the characters from the text. In quotes, like font_family
        character_set="'auto'",
        font_weight=600,  # a number: pydeck would read the text "bold" as a column name
        background=True,
        get_background_color=[247, 249, 249, 235],
        background_padding=[4, 2],
    )
    layers = [squares_layer, place_layer, label_layer]
    if sea_mask():
        # The sea over the cells, so their colours stop at the coast. Not pickable:
        # a click on the sea still reaches the cell under it
        sea_layer = pdk.Layer(
            "GeoJsonLayer",
            data=sea_mask(),
            filled=True,
            stroked=False,
            get_fill_color=SEA,
            pickable=False,
        )
        layers.insert(1, sea_layer)
    return pdk.Deck(
        layers=layers,
        initial_view_state=view,
        # The base period and the layout are the same for every cell, so they sit in the
        # template rather than in the data sent for each cell
        tooltip={
            "html": f"<b>{{label}}</b> vs {base_label}<br/>cell at {{lat}}, {{lon}}",
            "style": {
                "backgroundColor": "#18262E",  # ink
                "color": "#F7F9F9",
                "fontFamily": "'IBM Plex Sans', sans-serif",
                "fontSize": "0.8rem",
                "padding": "4px 8px",
            },
        },
        map_style="light",
    )


def legend_html(limit: float) -> str:
    """The colour key as 20 separate steps, like the key printed on a weather chart."""
    steps = "".join(f'<div style="flex:1;background:{c}"></div>' for c in DIVERGING)
    return (
        '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px 8px;'
        f'font-size:0.8rem;color:{AXIS_COLOUR};white-space:nowrap;font-variant-numeric:tabular-nums">'
        f"<span>−{limit:.1f} °C</span>"
        f'<div style="flex:1 1 120px;max-width:260px;height:8px;display:flex">{steps}</div>'
        f"<span>+{limit:.1f} °C</span>"
        "<span style='white-space:normal'>● the chosen place</span></div>"
    )
