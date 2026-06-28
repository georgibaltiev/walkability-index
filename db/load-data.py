import geopandas as gpd
from sqlalchemy import create_engine

# Database connection configuration
DB_USER = "postgres"
DB_PASS = "mysecretpassword"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "gis_db"

engine = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# Target projected CRS for accurate distance in meters (UTM Zone 34N for Sofia)
TARGET_CRS = "EPSG:32634"

print("Loading and projecting datasets...")
buildings = gpd.read_file("./data/geojson/buildings.geojson").to_crs(TARGET_CRS)
supermarkets = gpd.read_file("./data/supermarkets.geojson").to_crs(TARGET_CRS)

# --- THE FIX ---
# Load network, change projection, and explode MultiLineStrings to individual LineStrings
network = gpd.read_file("./data/pedestrian_network.geojson").to_crs(TARGET_CRS)
print("Exploding MultiLineStrings into LineStrings for pgRouting compatibility...")
network = network.explode(index_parts=False).reset_index(drop=True)
# ---------------

# Save to PostgreSQL
print("Writing datasets to PostgreSQL...")
buildings.to_postgis("buildings", engine, if_exists="replace", index=True, index_label="building_id")
supermarkets.to_postgis("supermarkets", engine, if_exists="replace", index=True, index_label="market_id")
network.to_postgis("pedestrian_network", engine, if_exists="replace", index=True, index_label="edge_id")

print("Data ingestion complete. Now run your topology setup and Step 5 routing script!")