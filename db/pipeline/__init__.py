"""Ordered pipeline steps.

Each step exposes a ``run(engine)`` callable. ``STEPS`` lists them in execution
order; ``db/__main__.py`` consumes this list for the ``all`` subcommand.
"""

from db.pipeline import (
    
)

from db.analysis import walkability_step
from db.ingestion import install_extensions, load_geojson_data
from db.network import introduce_topology, snap_nodes
from db.visualization import map_step


STEPS = [
    ("extensions", install_extensions.run),
    ("load",       load_geojson_data.run),
    ("topology",   introduce_topology.run),
    ("snap",       snap_nodes.run),
    ("walkability", walkability_step.run),
    ("map",        map_step.run),
]

STEP_MAP = dict(STEPS)
