import pandas as pd
from sqlalchemy import create_engine, text

# Database connection configuration
DB_USER = "postgres"
DB_PASS = "mysecretpassword"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "gis_db"

engine = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# 1. Fetch all supermarket network nodes safely using text()
with engine.connect() as conn:
    markets_df = pd.read_sql(
        text("SELECT DISTINCT nearest_node FROM supermarkets WHERE nearest_node IS NOT NULL"), 
        conn
    )
market_nodes = markets_df['nearest_node'].tolist()

if not market_nodes:
    raise ValueError("No supermarket network nodes found. Make sure Step 3 & 4 ran completely.")

market_nodes_str = ",".join(map(str, market_nodes))

# 2. Fetch all building targets
with engine.connect() as conn:
    buildings_df = pd.read_sql(
        text("SELECT building_id, nearest_node FROM buildings WHERE nearest_node IS NOT NULL"), 
        conn
    )

print(f"Calculating network distances for {len(buildings_df)} buildings...")

building_distances = {}
chunk_size = 50

# 3. Iterate through buildings in chunks to optimize memory
for i in range(0, len(buildings_df), chunk_size):
    chunk = buildings_df.iloc[i:i+chunk_size]
    source_nodes = chunk['nearest_node'].tolist()
    source_nodes_str = ",".join(map(str, source_nodes))
    
    # Construct the pgRouting query
    query = f"""
    SELECT 
        start_vid AS building_node,
        MIN(agg_cost) AS min_distance
    FROM pgr_dijkstra(
        'SELECT edge_id AS id, source, target, cost FROM pedestrian_network',
        ARRAY[{source_nodes_str}],
        ARRAY[{market_nodes_str}],
        directed := false
    )
    WHERE agg_cost > 0  -- Forces pgRouting to find an actual walking route edge if it loops
    GROUP BY start_vid;
    """
    
    with engine.connect() as conn:
        routes_df = pd.read_sql(text(query), conn)
    
    # Map the resulting node distances back to the dataframe chunk elements
    for _, row in chunk.iterrows():
        b_id = row['building_id']
        b_node = row['nearest_node']
        
        match = routes_df[routes_df['building_node'] == b_node]
        if not match.empty:
            building_distances[b_id] = float(match['min_distance'].values[0])
        else:
            building_distances[b_id] = None

print("Calculations complete. Writing back to database...")

# 4. Save results to a temporary table
results_df = pd.DataFrame(list(building_distances.items()), columns=['building_id', 'distance_to_supermarket_m'])
results_df.to_sql("temp_distances", engine, if_exists="replace", index=False)

# 5. Perform the final update join using the correct syntax
# 5. Perform the final update join inside a managed transaction block
with engine.begin() as conn:
    # Safely create column if missing
    conn.execute(text("ALTER TABLE buildings ADD COLUMN IF NOT EXISTS distance_to_supermarket_m DOUBLE PRECISION;"))
    
    # Update main table mapping from temp table
    conn.execute(text("""
        UPDATE buildings b
        SET distance_to_supermarket_m = t.distance_to_supermarket_m
        FROM temp_distances t
        WHERE b.building_id = t.building_id;
    """))
    
    # Clean up the staging table immediately
    conn.execute(text("DROP TABLE temp_distances;"))

print("Successfully updated buildings table with walking distances!")