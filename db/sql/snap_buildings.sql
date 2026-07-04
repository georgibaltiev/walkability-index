
UPDATE buildings b
SET nearest_node = sub.node_id
FROM (
    SELECT DISTINCT ON (b.building_id)
        b.building_id,
        CASE
            WHEN ST_Distance(ST_ClosestPoint(b.geometry, n.geometry), v1.the_geom)
               < ST_Distance(ST_ClosestPoint(b.geometry, n.geometry), v2.the_geom)
            THEN n.source
            ELSE n.target
        END AS node_id
    FROM buildings b
    JOIN pedestrian_network n
        ON ST_DWithin(b.geometry, n.geometry, 500)
    JOIN pedestrian_network_vertices_pgr v1 ON n.source = v1.id
    JOIN pedestrian_network_vertices_pgr v2 ON n.target = v2.id
    JOIN network_components c1
        ON v1.id = c1.node AND c1.component = :main_component_id
    JOIN network_components c2
        ON v2.id = c2.node AND c2.component = :main_component_id
    ORDER BY b.building_id, n.geometry <-> b.geometry
) AS sub
WHERE b.building_id = sub.building_id;
