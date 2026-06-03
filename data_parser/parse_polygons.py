#!/usr/bin/env python3
"""
Parser for building polygons (сгради) - converts Shapefile to GeoJSON and generates Leaflet visualization
"""

from collections import defaultdict
from functools import lru_cache
from heapq import heappop, heappush
from itertools import count
from pathlib import Path
from typing import Optional, Tuple

import geopandas as gpd
import json
import argparse
import pandas as pd
from shapely.geometry import LineString, Point


PointLike = Tuple[float, float]
DEFAULT_GREEN_AREAS_PATH = Path("data/green_areas_26_sofp_20200518.geojson")
DEFAULT_SUPERMARKETS_PATH = Path("data/supermarkets.geojson")
DEFAULT_SCHOOLS_PATH = Path("data/schools.json")
DEFAULT_KINDERGARTENS_PATH = Path("data/kindergartens.geojson")


@lru_cache(maxsize=4)
def _load_pedestrian_network(network_geojson_path: str):
    """Load the pedestrian network as projected segments plus an adjacency list."""
    network_gdf = gpd.read_file(network_geojson_path)
    if network_gdf.empty:
        raise ValueError(f"No pedestrian network features found in {network_geojson_path}")

    network_crs = network_gdf.estimate_utm_crs() or "EPSG:3857"
    projected = network_gdf.to_crs(network_crs)

    adjacency = defaultdict(list)
    segments = []

    for geometry in projected.geometry:
        if geometry is None:
            continue

        line_parts = getattr(geometry, "geoms", [geometry])
        for line in line_parts:
            if line is None or line.is_empty:
                continue

            coordinates = list(line.coords)
            for start, end in zip(coordinates, coordinates[1:]):
                start_node = (float(start[0]), float(start[1]))
                end_node = (float(end[0]), float(end[1]))
                weight = LineString([start_node, end_node]).length

                adjacency[start_node].append((end_node, weight))
                adjacency[end_node].append((start_node, weight))
                segments.append((LineString([start_node, end_node]), start_node, end_node))

    return adjacency, segments, network_crs


def _project_point(point: PointLike, source_crs: str, target_crs: str) -> Point:
    """Project a lon/lat point into the network CRS."""
    point_gs = gpd.GeoSeries([Point(point[0], point[1])], crs=source_crs)
    return point_gs.to_crs(target_crs).iloc[0]


def _nearest_segment(point: Point, segments):
    """Find the network segment closest to a projected point."""
    best_segment = None
    best_distance = float("inf")

    for segment, start_node, end_node in segments:
        distance = segment.distance(point)
        if distance < best_distance:
            best_distance = distance
            best_segment = (segment, start_node, end_node)

    if best_segment is None:
        raise ValueError("Unable to locate a pedestrian network segment")

    return best_segment


def _shortest_path_distance(graph, extra_edges, source, target) -> float:
    """Run Dijkstra over the pedestrian graph with temporary endpoint connections."""
    frontier = [(0.0, next(_SHORTEST_PATH_COUNTER), source)]
    best = {source: 0.0}

    while frontier:
        distance, _, node = heappop(frontier)
        if node == target:
            return distance

        if distance > best.get(node, float("inf")):
            continue

        for neighbor, weight in graph.get(node, ()):
            candidate = distance + weight
            if candidate < best.get(neighbor, float("inf")):
                best[neighbor] = candidate
                heappush(frontier, (candidate, next(_SHORTEST_PATH_COUNTER), neighbor))

        for neighbor, weight in extra_edges.get(node, ()):
            candidate = distance + weight
            if candidate < best.get(neighbor, float("inf")):
                best[neighbor] = candidate
                heappush(frontier, (candidate, next(_SHORTEST_PATH_COUNTER), neighbor))

    raise ValueError("No pedestrian route exists between the provided points")


_SHORTEST_PATH_COUNTER = count()


def pedestrian_distance_meters(
    point_a: PointLike,
    point_b: PointLike,
    network_geojson_path: str = "data/pedestrian_network.geojson",
) -> float:
    """
    Compute the shortest walking distance between two lon/lat points using the pedestrian network.

    The points should be provided as (longitude, latitude) pairs in WGS84.
    """
    graph, segments, network_crs = _load_pedestrian_network(network_geojson_path)

    start_point = _project_point(point_a, "EPSG:4326", network_crs)
    end_point = _project_point(point_b, "EPSG:4326", network_crs)

    start_segment, start_a, start_b = _nearest_segment(start_point, segments)
    end_segment, end_a, end_b = _nearest_segment(end_point, segments)

    start_offset = start_segment.project(start_point)
    end_offset = end_segment.project(end_point)

    start_virtual = ("__start__",)
    end_virtual = ("__end__",)

    extra_edges = defaultdict(list)
    for endpoint, distance in (
        (start_a, start_offset),
        (start_b, start_segment.length - start_offset),
    ):
        extra_edges[start_virtual].append((endpoint, distance))
        extra_edges[endpoint].append((start_virtual, distance))
    for endpoint, distance in (
        (end_a, end_offset),
        (end_b, end_segment.length - end_offset),
    ):
        extra_edges[end_virtual].append((endpoint, distance))
        extra_edges[endpoint].append((end_virtual, distance))

    return _shortest_path_distance(graph, extra_edges, start_virtual, end_virtual)


def _residential_mask(gdf) -> gpd.pd.Series:
    """Identify residential buildings using the available attributes."""
    mask = pd.Series([False] * len(gdf), index=gdf.index)

    if "funccode" in gdf.columns:
        mask = mask | gdf["funccode"].astype(str).isin({"100", "110", "180"})

    if "functype" in gdf.columns:
        mask = mask | gdf["functype"].astype(str).str.contains(r"Жилищна|обитаване", case=False, na=False, regex=True)

    return mask


def _metric_crs_for_layers(*layers) -> str:
    """Pick a projected CRS that works for the provided layers."""
    for layer in layers:
        layer_crs = getattr(layer, "crs", None)
        if layer_crs and not getattr(layer_crs, "is_geographic", False):
            return str(layer_crs)

    for layer in layers:
        valid_geometry = layer.geometry.notna() & ~layer.geometry.is_empty
        if not valid_geometry.any():
            continue

        try:
            estimated = layer.loc[valid_geometry].estimate_utm_crs()
            if estimated:
                return str(estimated)
        except (ValueError, TypeError):
            continue

    return "EPSG:3857"


def _sanitize_gdf_for_json(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return a copy of the GeoDataFrame with JSON-unsafe types converted to strings.

    Converts datetime-like columns and other non-primitive objects to strings so
    that `GeoDataFrame.to_json()` doesn't fail on Timestamp objects.
    """
    df = gdf.copy()
    for col in df.columns:
        try:
            if pd.api.types.is_datetime64_any_dtype(df[col].dtype):
                df[col] = df[col].astype(str)
            elif df[col].dtype == object:
                df[col] = df[col].apply(lambda v: v.isoformat() if hasattr(v, 'isoformat') else (v if isinstance(v, (str, int, float, bool)) or v is None else str(v)))
        except Exception:
            # best-effort: stringify problematic column
            df[col] = df[col].apply(lambda v: str(v) if v is not None else None)
    return df


def add_green_area_proximity(
    buildings_gdf,
    green_areas_path: str = str(DEFAULT_GREEN_AREAS_PATH),
    supermarkets_path: str = str(DEFAULT_SUPERMARKETS_PATH),
    schools_path: str = str(DEFAULT_SCHOOLS_PATH),
    kindergartens_path: str = str(DEFAULT_KINDERGARTENS_PATH),
    green_weight: float = 0.5,
    supermarket_weight: float = 0.5,
    school_weight: float = 0.0,
    kindergarten_weight: float = 0.0,
) -> tuple:
    """Add distances to green areas and supermarkets for residential buildings.

    Returns buildings and green areas and supermarkets all in WGS84.
    """
    if not Path(green_areas_path).exists():
        raise FileNotFoundError(f"Green areas file not found: {green_areas_path}")

    green_gdf = gpd.read_file(green_areas_path)
    if green_gdf.empty:
        raise ValueError(f"No green area features found in {green_areas_path}")

    supermarkets_gdf = None
    if Path(supermarkets_path).exists():
        supermarkets_gdf = gpd.read_file(supermarkets_path)

    schools_gdf = None
    if Path(schools_path).exists():
        try:
            schools_gdf = gpd.read_file(schools_path)
        except Exception:
            print(f"Warning: unable to read schools file as a GeoDataFrame: {schools_path}; skipping")
            schools_gdf = None

    kindergartens_gdf = None
    if Path(kindergartens_path).exists():
        try:
            kindergartens_gdf = gpd.read_file(kindergartens_path)
        except Exception:
            print(f"Warning: unable to read kindergartens file as a GeoDataFrame: {kindergartens_path}; skipping")
            kindergartens_gdf = None

    optional_layers = [green_gdf]
    if supermarkets_gdf is not None:
        optional_layers.append(supermarkets_gdf)
    if schools_gdf is not None:
        optional_layers.append(schools_gdf)
    if kindergartens_gdf is not None:
        optional_layers.append(kindergartens_gdf)

    buildings_crs = _metric_crs_for_layers(buildings_gdf, *optional_layers)
    projected_buildings = buildings_gdf.to_crs(buildings_crs)
    projected_green = green_gdf.to_crs(buildings_crs)
    projected_supermarkets = supermarkets_gdf.to_crs(buildings_crs) if supermarkets_gdf is not None else None

    residential_mask = _residential_mask(projected_buildings)
    projected_buildings["is_residential"] = residential_mask
    projected_buildings["green_distance_m"] = None
    projected_buildings["supermarket_distance_m"] = None
    projected_buildings["school_distance_m"] = None
    projected_buildings["kindergarten_distance_m"] = None
    projected_buildings["access_distance_m"] = None

    if residential_mask.any():
        green_union = projected_green.geometry.unary_union
        distances_green = projected_buildings.geometry.distance(green_union)
        projected_buildings.loc[residential_mask, "green_distance_m"] = distances_green.loc[residential_mask].round(2)

        if projected_supermarkets is not None and not projected_supermarkets.empty:
            markets_union = projected_supermarkets.geometry.unary_union
            distances_market = projected_buildings.geometry.distance(markets_union)
            projected_buildings.loc[residential_mask, "supermarket_distance_m"] = distances_market.loc[residential_mask].round(2)

        if schools_gdf is not None and not schools_gdf.empty:
            projected_schools = schools_gdf.to_crs(buildings_crs)
            schools_union = projected_schools.geometry.unary_union
            distances_school = projected_buildings.geometry.distance(schools_union)
            projected_buildings.loc[residential_mask, "school_distance_m"] = distances_school.loc[residential_mask].round(2)

        if kindergartens_gdf is not None and not kindergartens_gdf.empty:
            projected_kindergartens = kindergartens_gdf.to_crs(buildings_crs)
            kindergartens_union = projected_kindergartens.geometry.unary_union
            distances_kind = projected_buildings.geometry.distance(kindergartens_union)
            projected_buildings.loc[residential_mask, "kindergarten_distance_m"] = distances_kind.loc[residential_mask].round(2)

        # combined access distance = weighted combination across available categories.
        # If only one category is present, use that distance. If multiple present
        # and weights sum to zero, fallback to the minimum distance.
        for idx in projected_buildings.index[residential_mask]:
            g = projected_buildings.at[idx, "green_distance_m"]
            s = projected_buildings.at[idx, "supermarket_distance_m"]
            sch = projected_buildings.at[idx, "school_distance_m"]
            kind = projected_buildings.at[idx, "kindergarten_distance_m"]

            available = []
            if g is not None:
                available.append((g, float(green_weight)))
            if s is not None:
                available.append((s, float(supermarket_weight)))
            if sch is not None:
                available.append((sch, float(school_weight)))
            if kind is not None:
                available.append((kind, float(kindergarten_weight)))

            if not available:
                projected_buildings.at[idx, "access_distance_m"] = None
                continue

            if len(available) == 1:
                projected_buildings.at[idx, "access_distance_m"] = round(available[0][0], 2)
                continue

            total_w = sum(w for _, w in available)
            if total_w > 0:
                weighted = sum(d * w for d, w in available) / total_w
                projected_buildings.at[idx, "access_distance_m"] = round(weighted, 2)
            else:
                # No meaningful weights provided: fallback to min distance
                projected_buildings.at[idx, "access_distance_m"] = round(min(d for d, _ in available), 2)

    return (
        projected_buildings.to_crs(epsg=4326),
        green_gdf.to_crs(epsg=4326),
        (projected_supermarkets.to_crs(epsg=4326) if projected_supermarkets is not None else None),
        (schools_gdf.to_crs(epsg=4326) if schools_gdf is not None else None),
        (kindergartens_gdf.to_crs(epsg=4326) if kindergartens_gdf is not None else None),
    )




def parse_polygons(shp_path: str, output_geojson: Optional[str] = None,
                   output_html: Optional[str] = None, max_features: Optional[int] = None,
                   filter_type: Optional[str] = None,
                   green_areas_path: str = str(DEFAULT_GREEN_AREAS_PATH),
                   supermarkets_path: str = str(DEFAULT_SUPERMARKETS_PATH),
                   schools_path: str = str(DEFAULT_SCHOOLS_PATH),
                   kindergartens_path: str = str(DEFAULT_KINDERGARTENS_PATH),
                   green_weight: float = 0.5,
                   supermarket_weight: float = 0.5,
                   school_weight: float = 0.0,
                   kindergarten_weight: float = 0.0) -> dict:
    """
    Parse polygon shapefile and optionally convert to GeoJSON and HTML visualization.

    Args:
        shp_path: Path to the shapefile
        output_geojson: Optional path to save GeoJSON output
        output_html: Optional path to save HTML Leaflet map
        max_features: Optional limit on number of features to process
        filter_type: Optional filter by functype (supports wildcards with *)

    Returns:
        GeoJSON dictionary
    """
    print(f"Reading shapefile: {shp_path}")
    gdf = gpd.read_file(shp_path)

    print(f"Total features: {len(gdf)}")
    print(f"CRS: {gdf.crs}")

    # Filter by type if specified
    if filter_type:
        if '*' in filter_type:
            # Wildcard filtering
            pattern = filter_type.replace('*', '.*')
            gdf = gdf[gdf['functype'].str.contains(pattern, case=False, regex=True, na=False)]
            print(f"Filtered to {len(gdf)} features matching '{filter_type}'")
        else:
            gdf = gdf[gdf['functype'] == filter_type]
            print(f"Filtered to {len(gdf)} features of type '{filter_type}'")

    # Limit features if specified
    if max_features:
        gdf = gdf.head(max_features)
        print(f"Limited to {max_features} features")

    # Convert to WGS84 (EPSG:4326) for Leaflet compatibility
    print("Converting to WGS84...")
    gdf_wgs84, green_areas_wgs84, supermarkets_wgs84, schools_wgs84, kindergartens_wgs84 = add_green_area_proximity(
        gdf,
        green_areas_path,
        supermarkets_path,
        schools_path=schools_path,
        kindergartens_path=kindergartens_path,
        green_weight=green_weight,
        supermarket_weight=supermarket_weight,
        school_weight=school_weight,
        kindergarten_weight=kindergarten_weight,
    )

    # Convert to GeoJSON
    geojson = json.loads(gdf_wgs84.to_json())

    green_areas_geojson = None
    supermarkets_geojson = None
    if output_html:
        green_areas_geojson = json.loads(_sanitize_gdf_for_json(green_areas_wgs84).to_json())
        if supermarkets_wgs84 is not None:
            supermarkets_geojson = json.loads(_sanitize_gdf_for_json(supermarkets_wgs84).to_json())
        else:
            supermarkets_geojson = None

    # Save GeoJSON if requested
    if output_geojson:
        print(f"Saving GeoJSON to: {output_geojson}")
        with open(output_geojson, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)

    # Generate HTML map if requested
    if output_html:
        _generate_leaflet_map(
            geojson, green_areas_geojson, supermarkets_geojson, schools_geojson, kindergartens_geojson, output_html, gdf_wgs84
        )

    return geojson


def _generate_leaflet_map(geojson: dict, green_areas_geojson: dict, supermarkets_geojson: dict, schools_geojson: dict, kindergartens_geojson: dict, output_path: str, gdf) -> None:
    """Generate interactive Leaflet map HTML."""
    print(f"Generating Leaflet map: {output_path}")

    bounds = gdf.total_bounds  # minx, miny, maxx, maxy
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Building Polygons Visualization</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        * {{ margin: 0; padding: 0; }}
        body {{ font: 14px/1.5 "Helvetica Neue", Arial, Helvetica, sans-serif; }}
        #map {{ position: absolute; top: 0; bottom: 0; width: 100%; }}
        .info {{
            padding: 6px 8px;
            font: 14px Arial, Helvetica, sans-serif;
            background: white;
            background: rgba(255,255,255,0.8);
            box-shadow: 0 0 15px rgba(0,0,0,0.2);
            border-radius: 5px;
        }}
        .info h4 {{ margin: 0 0 5px 0; color: #777; }}
        .legend {{
            line-height: 18px;
            color: #555;
        }}
        .legend i {{
            width: 18px;
            height: 18px;
            float: left;
            margin-right: 8px;
            opacity: 0.7;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        var map = L.map('map').setView([{center_lat}, {center_lon}], 12);

        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            maxZoom: 19
        }}).addTo(map);

        var buildingsData = {json.dumps(geojson)};
        var supermarketsData = {json.dumps(supermarkets_geojson) if supermarkets_geojson is not None else 'null'};
        var schoolsData = {json.dumps(schools_geojson) if schools_geojson is not None else 'null'};
        var kindergartensData = {json.dumps(kindergartens_geojson) if kindergartens_geojson is not None else 'null'};

        function getColor(feature) {{
            var funccode = Number(feature.properties.funccode);
            switch(funccode) {{
                case 1101: return '#FF6B6B';  // Residential
                case 1102: return '#4ECDC4';  // Commercial
                case 1103: return '#45B7D1';  // Industrial
                case 1104: return '#96CEB4';  // Agricultural
                default: return '#CCCCCC';
            }}
        }}

        function getResidentialColor(distance) {{
            if (distance === null || distance === undefined || isNaN(distance)) {{
                return '#D8D8D8';
            }}
            if (distance <= 100) return '#1B5E20';
            if (distance <= 250) return '#43A047';
            if (distance <= 500) return '#8BC34A';
            if (distance <= 1000) return '#FDD835';
            return '#EF6C00';
        }}

        function style(feature) {{
            var isResidential = Boolean(feature.properties.is_residential);
            var distance = feature.properties.access_distance_m;
            return {{
                fillColor: isResidential ? getResidentialColor(distance) : getColor(feature),
                weight: 1,
                opacity: 0.5,
                color: '#333',
                dashArray: '0',
                fillOpacity: 0.6
            }};
        }}

        function onEachFeature(feature, layer) {{
            var props = feature.properties;
            var popupContent = '<div style="font-size: 12px; max-width: 250px;">' +
                '<b>Building Info</b><br/>' +
                (props.immaddr ? 'Address: ' + props.immaddr + '<br/>' : '') +
                (props.flrcount ? 'Floors: ' + props.flrcount + '<br/>' : '') +
                (props.AREA ? 'Area: ' + props.AREA.toFixed(2) + ' m²<br/>' : '') +
                (props.functype ? 'Type: ' + props.functype + '<br/>' : '') +
                (props.green_distance_m !== null && props.green_distance_m !== undefined ? 'Distance to green area: ' + Number(props.green_distance_m).toFixed(2) + ' m<br/>' : '') +
                (props.supermarket_distance_m !== null && props.supermarket_distance_m !== undefined ? 'Distance to supermarket: ' + Number(props.supermarket_distance_m).toFixed(2) + ' m<br/>' : '') +
                (props.school_distance_m !== null && props.school_distance_m !== undefined ? 'Distance to school: ' + Number(props.school_distance_m).toFixed(2) + ' m<br/>' : '') +
                (props.kindergarten_distance_m !== null && props.kindergarten_distance_m !== undefined ? 'Distance to kindergarten: ' + Number(props.kindergarten_distance_m).toFixed(2) + ' m<br/>' : '') +
                (props.access_distance_m !== null && props.access_distance_m !== undefined ? 'Access distance: ' + Number(props.access_distance_m).toFixed(2) + ' m<br/>' : '') +
                '</div>';
            layer.bindPopup(popupContent);
        }}

        L.geoJSON(buildingsData, {{
            style: style,
            onEachFeature: onEachFeature
        }}).addTo(map);

        // Info control
        var info = L.control({{position: 'topright'}});
        info.onAdd = function(map) {{
            this._div = L.DomUtil.create('div', 'info');
            this._div.innerHTML = '<h4>Building Polygons</h4>' +
                '<p>Sofia buildings visualization</p>' +
                '<p>Residential buildings are colored by distance to the nearest green area</p>' +
                '<p>Total features: {len(geojson["features"])}</p>';
            return this._div;
        }};
        info.addTo(map);
    </script>
</body>
</html>
"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)


def main():
    parser = argparse.ArgumentParser(description='Parse and visualize building polygons')
    parser.add_argument('--shp', default='data/сгради/Сгради (Polygon).shp',
                       help='Path to shapefile')
    parser.add_argument('--geojson', default='output/buildings.geojson',
                       help='Output GeoJSON file')
    parser.add_argument('--html', default='output/index.html',
                       help='Output HTML Leaflet map')
    parser.add_argument('--limit', type=int, default=None,
                       help='Limit number of features (useful for testing)')
    parser.add_argument('--filter', dest='filter_type', default=None,
                       help='Filter by functype (supports wildcards with *). Examples: "Жилищна*" or "Жилищна сграда - еднофамилна"')
    parser.add_argument('--no-geojson', action='store_true',
                       help='Skip GeoJSON generation')
    parser.add_argument('--no-html', action='store_true',
                       help='Skip HTML map generation')

    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.geojson).parent if args.geojson else Path(args.html).parent
    output_dir.mkdir(exist_ok=True, parents=True)

    # Parse polygons
    geojson_path = None if args.no_geojson else args.geojson
    html_path = None if args.no_html else args.html

    parse_polygons(
        shp_path=args.shp,
        output_geojson=geojson_path,
        output_html=html_path,
        max_features=args.limit,
        filter_type=args.filter_type
    )

    print("\n✓ Done!")
    if geojson_path:
        print(f"  GeoJSON: {geojson_path}")
    if html_path:
        print(f"  Map: {html_path}")


if __name__ == '__main__':
    main()
