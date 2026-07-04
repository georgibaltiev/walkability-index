"""Ordered pipeline steps.

Each step exposes a ``run(engine)`` callable. ``STEPS`` lists them in execution
order; ``db/__main__.py`` consumes this list for the ``all`` subcommand.
"""

from db.pipeline import (
    calculate_walkability_features,
    generate_map,
    install_extensions,
    introduce_topology,
    load_geojson_data,
    snap_nodes,
)


STEPS = [
    ("extensions", install_extensions.run),
    ("load",       load_geojson_data.run),
    ("topology",   introduce_topology.run),
    ("snap",       snap_nodes.run),
    ("walkability", calculate_walkability_features.run),
    ("map",        generate_map.run),
]

STEP_MAP = dict(STEPS)
