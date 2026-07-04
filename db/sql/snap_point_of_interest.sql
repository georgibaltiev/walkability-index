UPDATE __TABLE_NAME__ t
SET nearest_node = sub.node_id
FROM (
    SELECT DISTINCT ON (t.__ID_COLUMN__)
        t.__ID_COLUMN__,
        CASE
            WHEN ST_Distance(t.geometry, v1.the_geom) < ST_Distance(t.geometry, v2.the_geom)
            THEN n.source
            ELSE n.target
        END AS node_id
    FROM __TABLE_NAME__ t
    JOIN pedestrian_network n
        ON ST_DWithin(t.geometry, n.geometry, 500)
    JOIN pedestrian_network_vertices_pgr v1 ON n.source = v1.id
    JOIN pedestrian_network_vertices_pgr v2 ON n.target = v2.id
    JOIN network_components c1
        ON v1.id = c1.node AND c1.component = :main_component_id
    JOIN network_components c2
        ON v2.id = c2.node AND c2.component = :main_component_id
    ORDER BY t.__ID_COLUMN__, n.geometry <-> t.geometry
) AS sub
WHERE t.__ID_COLUMN__ = sub.__ID_COLUMN__;