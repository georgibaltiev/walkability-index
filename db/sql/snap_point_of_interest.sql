UPDATE __TABLE_NAME__ t
SET nearest_node = sub.node_id
FROM (
    SELECT DISTINCT ON (t.__ID_COLUMN__)
        t.__ID_COLUMN__,
        v.id AS node_id
    FROM __TABLE_NAME__ t
    JOIN pedestrian_network_vertices_pgr v
        ON ST_DWithin(t.geometry, v.the_geom, 1000)
    JOIN network_components c
        ON v.id = c.node AND c.component = :main_component_id
    ORDER BY t.__ID_COLUMN__, t.geometry <-> v.the_geom
) AS sub
WHERE t.__ID_COLUMN__ = sub.__ID_COLUMN__;