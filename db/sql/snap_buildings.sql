
UPDATE buildings b
SET nearest_node = sub.node_id
FROM (
    SELECT DISTINCT ON (b.building_id)
        b.building_id,
        v.id AS node_id
    FROM buildings b
    JOIN pedestrian_network_vertices_pgr v
        ON ST_DWithin(b.geometry, v.the_geom, 1000)
    JOIN network_components c
        ON v.id = c.node AND c.component = :main_component_id
    ORDER BY b.building_id, b.geometry <-> v.the_geom
) AS sub
WHERE b.building_id = sub.building_id;
