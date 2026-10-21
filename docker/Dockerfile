# PostgreSQL 17 + PostGIS 3.6 (Debian trixie), plus the h3-pg extension
FROM postgis/postgis:17-3.6

# The base image already has the PostgreSQL apt repository configured,
# so h3-pg installs as a ready-made package (no compiling).
# Clean the apt lists in the same layer to keep the image small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17-h3 \
    && rm -rf /var/lib/apt/lists/*
