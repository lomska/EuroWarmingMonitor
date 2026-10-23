-- One row per ERA5 grid point and the square it represents (the point is its centre).

select * from {{ ref('int_grid_squares') }}
