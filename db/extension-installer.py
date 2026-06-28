import psycopg2

# Connection settings matching the Docker container parameters
conn = psycopg2.connect(
    dbname="gis_db",
    user="postgres",
    password="mysecretpassword",
    host="localhost",
    port="5432"
)
cursor = conn.cursor()

# Enable PostGIS and pgRouting extensions
cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
cursor.execute("CREATE EXTENSION IF NOT EXISTS pgrouting;")
conn.commit()

cursor.close()
conn.close()
print("Database extensions successfully initialized! Ready for pipeline.")