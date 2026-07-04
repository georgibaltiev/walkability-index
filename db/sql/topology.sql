
ALTER TABLE pedestrian_network ADD COLUMN IF NOT EXISTS source INTEGER;
ALTER TABLE pedestrian_network ADD COLUMN IF NOT EXISTS target INTEGER;
ALTER TABLE pedestrian_network ADD COLUMN IF NOT EXISTS cost DOUBLE PRECISION;
UPDATE pedestrian_network SET cost = ST_Length(geometry);

-- 2.0 m snapping tolerance for nearby endpoint segments.
SELECT pgr_createTopology('pedestrian_network', 2.0, 'geometry', 'edge_id', 'source', 'target');

CREATE INDEX IF NOT EXISTS buildings_geom_idx
    ON buildings USING GIST (geometry);
CREATE INDEX IF NOT EXISTS pedestrian_network_geom_idx
    ON pedestrian_network USING GIST (geometry);
CREATE INDEX IF NOT EXISTS pedestrian_network_vertices_idx
    ON pedestrian_network_vertices_pgr USING GIST (the_geom);
