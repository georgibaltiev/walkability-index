from sqlalchemy import create_engine, text

# 1. Configuration matching your database container setup
DB_USER = "postgres"
DB_PASS = "mysecretpassword"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "gis_db"

engine = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

def setup_network_topology():
    
    # We group all operations into separate logical tasks executed sequentially
    steps = [
        {
            "desc": "Adding network routing columns and calculating line length costs",
            "sql": """
                ALTER TABLE pedestrian_network ADD COLUMN IF NOT EXISTS source INTEGER;
                ALTER TABLE pedestrian_network ADD COLUMN IF NOT EXISTS target INTEGER;
                ALTER TABLE pedestrian_network ADD COLUMN IF NOT EXISTS cost DOUBLE PRECISION;
                UPDATE pedestrian_network SET cost = ST_Length(geometry);
            """
        },
        {
            "desc": "Generating network topology vertices (pgr_createTopology)",
            "sql": """
                -- 1.0 meters is the snapping tolerance for nearby endpoint segments
                SELECT pgr_createTopology('pedestrian_network', 1.0, 'geometry', 'edge_id', 'source', 'target');
            """
        },
        {
            "desc": "Creating Spatial Indexes to drastically speed up distance computations",
            "sql": """
                CREATE INDEX IF NOT EXISTS buildings_geom_idx ON buildings USING GIST (geometry);
                CREATE INDEX IF NOT EXISTS supermarkets_geom_idx ON supermarkets USING GIST (geometry);
                CREATE INDEX IF NOT EXISTS pedestrian_network_vertices_idx ON pedestrian_network_vertices_pgr USING GIST (the_geom);
            """
        },
        {
            "desc": "Mapping buildings and supermarkets to their nearest network nodes",
            "sql": """
                -- Add node tracking tracking columns if missing
                ALTER TABLE buildings ADD COLUMN IF NOT EXISTS nearest_node INTEGER;
                ALTER TABLE supermarkets ADD COLUMN IF NOT EXISTS nearest_node INTEGER;

                -- Find nearest network vertex for each building centroid using spatial index (<-> operator)
                UPDATE buildings b
                SET nearest_node = (
                    SELECT v.id 
                    FROM pedestrian_network_vertices_pgr v 
                    ORDER BY v.the_geom <-> ST_Centroid(b.geometry) 
                    LIMIT 1
                );

                -- Find nearest network vertex for each supermarket location
                UPDATE supermarkets s
                SET nearest_node = (
                    SELECT v.id 
                    FROM pedestrian_network_vertices_pgr v 
                    ORDER BY v.the_geom <-> s.geometry 
                    LIMIT 1
                );
            """
        }
    ]

    # Execute steps inside a controlled transaction context
    with engine.begin() as conn:
        for step in steps:
            print(f"[Running]: {step['desc']}...")
            conn.execute(text(step['sql']))
            
    print("--- Database Topology and Spatial Indexes Ready! ---")

if __name__ == "__main__":
    setup_network_topology()