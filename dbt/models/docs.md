{% docs grid_squares %}
ERA5 values come on a regular 0.25° grid. Each grid point is the centre of a
square that reaches 0.125° in every direction, and its value describes that
whole square. Squares get smaller towards the poles: in the Caucasus box they
range from about 625 km² at 36°N to 519 km² at 48°N, so averages over several
squares should be weighted by `area_km2`.

ERA5 values are interpolated from the model's native grid (about 31 km), so
the effective resolution is a little coarser than the grid spacing.
{% enddocs %}

{% docs city_to_square %}
Each GeoNames place (cities1000: places with at least 1,000 inhabitants)
belongs to the square it lies in, which is the square of its nearest grid
point. A square's temperature describes the whole square and its average
height, not the town itself: coastal and mountain towns can differ by several
degrees. Changes over time (anomalies, trends) are much less affected than
absolute temperatures.
{% enddocs %}

{% docs climate_normals %}
A climate normal is the mean temperature over a 30-year reference period, here
per grid square and calendar month. The current WMO normal is 1991–2020; the
earlier 1961–1990 normal shows long-term change. Both periods are set by
`vars` in `dbt_project.yml`.
{% enddocs %}

{% docs rolling_window %}
For each grid square and calendar month, the mean over the last
`window_years` years (default 10), labelled by the window's end year: the
January 1949 value is the mean of the Januaries 1940–1949. Only complete
windows are kept. The window counts rows, so the tests check that no year is
missing.
{% enddocs %}

{% docs preliminary %}
The most recent months of ERA5 are published first as preliminary data
(ERA5T, `expver` other than `0001`) and may be revised. They are flagged with
`is_preliminary`, which carries through to every mart.
{% enddocs %}
