from __future__ import annotations

import branca.colormap as cm
import folium
import geopandas as gpd
import pandas as pd
from folium import GeoJsonTooltip
from sqlalchemy.engine import Engine

from db.config import OUTPUT_DIR, TARGET_CRS, WALKABILITY_MAP_HTML
from db.analysis.data_access import load_feature_frame


def render_map(engine: Engine) -> None:
    print("Fetching data from PostgreSQL...")
    distance_frame = load_feature_frame(engine)
    buildings_projected = gpd.read_postgis(
        "SELECT building_id, geometry FROM buildings",
        engine, geom_col="geometry", crs=TARGET_CRS,
    )
    buildings_projected = buildings_projected.merge(distance_frame, on="building_id", how="left")
    buildings = buildings_projected.to_crs("EPSG:4326")

    min_x, min_y, max_x, max_y = buildings.total_bounds
    map_center = [
        (min_y + max_y) / 2.0,
        (min_x + max_x) / 2.0,
    ]

    print("Generating Leaflet map...")
    if "walkability_index" not in buildings.columns:
        raise RuntimeError("No walkability_index column found — run the walkability step first.")

    buildings["walkability_index"] = pd.to_numeric(
        buildings["walkability_index"], errors="coerce"
    ).clip(lower=0.0, upper=100.0)

    colormap = cm.LinearColormap(
        colors=["#e74c3c", "#f1c40f", "#2ecc71", "#3498db"], vmin=0, vmax=100,
    ).to_step(n=8)
    colormap.caption = "Walkability Index (0-100)"

    m = folium.Map(location=map_center, zoom_start=14, tiles="CartoDB positron")

    def style(feature):
        score = feature["properties"].get("walkability_index")
        if score is None:
            return {"fillColor": "#7f8c8d", "color": "#7f8c8d", "weight": 1, "fillOpacity": 0.4}
        return {"fillColor": colormap(score), "color": colormap(score), "weight": 1, "fillOpacity": 0.7}

    folium.GeoJson(
        buildings,
        name="Residential Buildings",
        style_function=style,
        tooltip=GeoJsonTooltip(
            fields=["walkability_index"],
            aliases=["Walkability Index:"],
            localize=True, sticky=True,
        ),
    ).add_to(m)

    colormap.add_to(m)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    m.save(str(WALKABILITY_MAP_HTML))
    print(f"Map written to {WALKABILITY_MAP_HTML}.")
