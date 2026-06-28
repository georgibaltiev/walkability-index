import folium
from folium import GeoJsonTooltip
import geopandas as gpd
from sqlalchemy import create_engine
import branca.colormap as cm

# 1. Database Connection Setup
DB_USER = "postgres"
DB_PASS = "mysecretpassword"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "gis_db"

engine = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

print("Fetching data from PostgreSQL...")

# 2. Load buildings and supermarkets back from database
# Leaflet/Folium needs standard WGS 84 (EPSG:4326) coordinate projection
buildings = gpd.read_postgis(
    "SELECT building_id, distance_to_supermarket_m, geometry FROM buildings", 
    engine, 
    geom_col="geometry", 
    crs="EPSG:32634"
).to_crs("EPSG:4326")

supermarkets = gpd.read_postgis(
    "SELECT name, geometry FROM supermarkets", 
    engine, 
    geom_col="geometry", 
    crs="EPSG:32634"
).to_crs("EPSG:4326")

print("Generating Leaflet Map configuration...")

# 3. Handle unreachable buildings (None/Null values)
# For calculations, treat missing paths as a very high distance or filter them
max_dist = buildings['distance_to_supermarket_m'].max() or 1500

# 4. Create a Dynamic Color Linear Scale (Green -> Yellow -> Red)
# Green is close (0m), Red is far away (max calculated distance)
colormap = cm.LinearColormap(
    colors=['#2ecc71', '#f1c40f', '#e74c3c'],
    vmin=0,
    vmax=max_dist
).to_step(n=6) # Breaks it into clean step thresholds
colormap.caption = "Distance to Nearest Supermarket (meters)"

# 5. Initialize the Map centered around the buildings data centroid
map_center = [buildings.geometry.centroid.y.mean(), buildings.geometry.centroid.x.mean()]
m = folium.Map(location=map_center, zoom_start=14, tiles="CartoDB positron")

# 6. Function to style individual building polygons based on distance
def style_function(feature):
    dist = feature['properties']['distance_to_supermarket_m']
    
    # If the network couldn't find a path to a supermarket
    if dist is None:
        return {
            'fillColor': '#7f8c8d', # Gray
            'color': '#7f8c8d',
            'weight': 1,
            'fillOpacity': 0.4
        }
    
    return {
        'fillColor': colormap(dist),
        'color': colormap(dist),
        'weight': 1,
        'fillOpacity': 0.7
    }

# 7. Add Buildings layer with automated interactive hover tooltips
folium.GeoJson(
    buildings,
    name="Residential Buildings",
    style_function=style_function,
    tooltip=GeoJsonTooltip(
        fields=['building_id', 'distance_to_supermarket_m'],
        aliases=['Building ID:', 'Distance (meters):'],
        localize=True,
        sticky=True
    )
).add_to(m)

# 8. Add Supermarket Icons to visually trace distances
for _, row in supermarkets.iterrows():
    if row.geometry.geom_type == 'Point':
        folium.Marker(
            location=[row.geometry.y, row.geometry.x],
            popup=row['name'] if row['name'] else "Supermarket",
            icon=folium.Icon(color='blue', icon='shopping-cart', prefix='fa')
        ).add_to(m)

# Add the legend scale to the map view
colormap.add_to(m)

# 9. Output to HTML file
output_html = "walkability_map.html"
m.save(output_html)
print(f"Map successfully generated! Open '{output_html}' in any browser to interact with it.")