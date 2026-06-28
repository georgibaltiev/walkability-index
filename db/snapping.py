import pandas as pd
from sqlalchemy import create_engine, text

DB_USER = "postgres"
DB_PASS = "mysecretpassword"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "gis_db"

engine = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

print("Analyzing network connectivity and performing edge-aligned snapping...")

with engine.begin() as conn:
    # 1. Clear out old metrics
    conn.execute(text("UPDATE buildings SET nearest_node = NULL, distance_to_supermarket_m = NULL;"))
    conn.execute(text("UPDATE supermarkets SET nearest_node = NULL;"))

    # 2. Identify the main connected network component
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS network_components AS
        SELECT * FROM pgr_connectedComponents(
            'SELECT edge_id AS id, source, target, cost FROM pedestrian_network'
        );
    """))
    
    row = conn.execute(text("""
        SELECT component, COUNT(*) as node_count 
        FROM network_components 
        GROUP BY component 
        ORDER BY node_count DESC 
        LIMIT 1;
    """)).fetchone()

    if row is None:
        raise ValueError("The network_components table is empty!")

    main_component_id = row[0]
    print(f"Main network grid identified (Component ID: {main_component_id}).")

    # 3. Smart-snap SUPERMARKETS to the closest vertex of the nearest street edge
    print("Edge-aligning supermarkets to main grid...")
    conn.execute(text(f"""
        UPDATE supermarkets s
        SET nearest_node = (
            SELECT CASE 
                WHEN ST_Distance(s.geometry, v1.the_geom) < ST_Distance(s.geometry, v2.the_geom) THEN n.source
                ELSE n.target
            END
            FROM pedestrian_network n
            JOIN pedestrian_network_vertices_pgr v1 ON n.source = v1.id
            JOIN pedestrian_network_vertices_pgr v2 ON n.target = v2.id
            JOIN network_components c1 ON v1.id = c1.node
            JOIN network_components c2 ON v2.id = c2.node
            WHERE c1.component = {main_component_id} AND c2.component = {main_component_id}
            ORDER BY n.geometry <-> s.geometry
            LIMIT 1
        );
    """))

    # 4. Smart-snap BUILDINGS to the closest vertex of the nearest street edge
    print("Edge-aligning buildings to main grid...")
    conn.execute(text(f"""
        UPDATE buildings b
        SET nearest_node = (
            SELECT CASE 
                WHEN ST_Distance(ST_Centroid(b.geometry), v1.the_geom) < ST_Distance(ST_Centroid(b.geometry), v2.the_geom) THEN n.source
                ELSE n.target
            END
            FROM pedestrian_network n
            JOIN pedestrian_network_vertices_pgr v1 ON n.source = v1.id
            JOIN pedestrian_network_vertices_pgr v2 ON n.target = v2.id
            JOIN network_components c1 ON v1.id = c1.node
            JOIN network_components c2 ON v2.id = c2.node
            WHERE c1.component = {main_component_id} AND c2.component = {main_component_id}
            ORDER BY n.geometry <-> ST_Centroid(b.geometry)
            LIMIT 1
        );
    """))
    
    conn.execute(text("DROP TABLE network_components;"))

print("Advanced snapping complete!")