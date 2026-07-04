from __future__ import annotations

import branca.colormap as cm
import folium
import geopandas as gpd
import pandas as pd
from folium import GeoJsonTooltip
from shapely.geometry import Point
from sqlalchemy.engine import Engine

from db.config import OUTPUT_DIR, TARGET_CRS, WALKABILITY_MAP_HTML
from db.analysis.data_access import load_feature_frame, load_poi_layer


def render_map(engine: Engine) -> None:
    print("Fetching data from PostgreSQL...")
    distance_frame = load_feature_frame(engine)
    buildings_projected = gpd.read_postgis(
        "SELECT building_id, geometry FROM buildings",
        engine, geom_col="geometry", crs=TARGET_CRS,
    )
    buildings_projected = buildings_projected.merge(distance_frame, on="building_id", how="left")
    buildings = buildings_projected.to_crs("EPSG:4326")

    poi_frames = []
    for column_name in distance_frame.columns:
        if column_name == "building_id" or not column_name.startswith("distance_to_"):
            continue
        table_name = column_name.removeprefix("distance_to_").removesuffix("_m")
        poi_frames.append(load_poi_layer(engine, table_name))

    points_of_interest = pd.concat(poi_frames, ignore_index=True) if poi_frames else pd.DataFrame()

    print("Generating Leaflet map...")
    distance_columns = [col for col in buildings.columns if col.startswith("distance_to_")]
    if not distance_columns:
        raise RuntimeError("No POI distance columns found — run the walkability step first.")

    buildings["min_distance_m"] = buildings[distance_columns].min(axis=1, skipna=True)
    max_dist = buildings["min_distance_m"].max() or 1500
    colormap = cm.LinearColormap(
        colors=["#2ecc71", "#f1c40f", "#e74c3c"], vmin=0, vmax=max_dist,
    ).to_step(n=6)
    colormap.caption = "Distance to Nearest POI (meters)"

    projected_centroids = buildings_projected.geometry.centroid
    center_projected = gpd.GeoSeries(
        [Point(projected_centroids.x.mean(), projected_centroids.y.mean())],
        crs=TARGET_CRS,
    ).to_crs("EPSG:4326").iloc[0]
    map_center = [center_projected.y, center_projected.x]
    m = folium.Map(location=map_center, zoom_start=14, tiles="CartoDB positron")

    def style(feature):
        dist = feature["properties"]["min_distance_m"]
        if dist is None:
            return {"fillColor": "#7f8c8d", "color": "#7f8c8d", "weight": 1, "fillOpacity": 0.4}
        return {"fillColor": colormap(dist), "color": colormap(dist), "weight": 1, "fillOpacity": 0.7}

    folium.GeoJson(
        buildings,
        name="Residential Buildings",
        style_function=style,
        tooltip=GeoJsonTooltip(
            fields=["building_id", "min_distance_m", *distance_columns],
            aliases=["Building ID:", "Nearest POI distance (meters):", *[f"{col}:" for col in distance_columns]],
            localize=True, sticky=True,
        ),
    ).add_to(m)

    for _, row in points_of_interest.iterrows():
        if row.geometry.geom_type == "Point":
            folium.Marker(
                location=[row.geometry.y, row.geometry.x],
                popup=row["display_name"],
                icon=folium.Icon(color="blue", icon="map-marker", prefix="fa"),
            ).add_to(m)

    colormap.add_to(m)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    m.save(str(WALKABILITY_MAP_HTML))
    print(f"Map written to {WALKABILITY_MAP_HTML}.")
