"""Ordered pipeline steps.

Each step exposes a ``run(engine)`` callable. ``STEPS`` lists them in execution
order; ``db/__main__.py`` consumes this list for the ``all`` subcommand.
"""

from db.pipeline import (
    install_extensions,
    introduce_topology,
    load_geojson_data,
    map_step,
    snap_nodes,
    walkability_step,
)


STEPS = [
    ("extensions", install_extensions.run),
    ("load",       load_geojson_data.run),
    ("topology",   introduce_topology.run),
    ("snap",       snap_nodes.run),
    ("walkability", walkability_step.run),
    ("map",        map_step.run),
]

STEP_MAP = dict(STEPS)
