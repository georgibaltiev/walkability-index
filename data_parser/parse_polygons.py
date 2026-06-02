#!/usr/bin/env python3
"""
Parser for building polygons (сгради) - converts Shapefile to GeoJSON and generates Leaflet visualization
"""

import geopandas as gpd
import json
import argparse
from pathlib import Path
from typing import Optional

def parse_polygons(shp_path: str, output_geojson: Optional[str] = None,
                   output_html: Optional[str] = None, max_features: Optional[int] = None,
                   filter_type: Optional[str] = None) -> dict:
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
    gdf_wgs84 = gdf.to_crs(epsg=4326)

    # Convert to GeoJSON
    geojson = json.loads(gdf_wgs84.to_json())

    # Save GeoJSON if requested
    if output_geojson:
        print(f"Saving GeoJSON to: {output_geojson}")
        with open(output_geojson, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)

    # Generate HTML map if requested
    if output_html:
        _generate_leaflet_map(geojson, output_html, gdf_wgs84)

    return geojson


def _generate_leaflet_map(geojson: dict, output_path: str, gdf) -> None:
    """Generate interactive Leaflet map HTML."""
    print(f"Generating Leaflet map: {output_path}")

    # Calculate map center
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

        var geojsonData = {json.dumps(geojson)};

        function getColor(feature) {{
            var funccode = feature.properties.funccode;
            switch(funccode) {{
                case 1101: return '#FF6B6B';  // Residential
                case 1102: return '#4ECDC4';  // Commercial
                case 1103: return '#45B7D1';  // Industrial
                case 1104: return '#96CEB4';  // Agricultural
                default: return '#CCCCCC';
            }}
        }}

        function style(feature) {{
            return {{
                fillColor: getColor(feature),
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
                '</div>';
            layer.bindPopup(popupContent);
        }}

        L.geoJSON(geojsonData, {{
            style: style,
            onEachFeature: onEachFeature
        }}).addTo(map);

        // Info control
        var info = L.control({{position: 'topright'}});
        info.onAdd = function(map) {{
            this._div = L.DomUtil.create('div', 'info');
            this._div.innerHTML = '<h4>Building Polygons</h4>' +
                '<p>Sofia buildings visualization</p>' +
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
    parser.add_argument('--html', default='output/buildings_map.html',
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
