from db.analysis.walkability_step import run as walkability_run
from db.ingestion.install_extensions import run as install_extensions_run
from db.ingestion.load_geojson_data import run as load_geojson_data_run
from db.network.introduce_topology import run as introduce_topology_run
from db.network.snap_nodes import run as snap_nodes_run
from db.visualization.map_step import run as map_run


STEPS = [
    ("extensions", install_extensions_run),
    ("load", load_geojson_data_run),
    ("topology", introduce_topology_run),
    ("snap", snap_nodes_run),
    ("walkability", walkability_run),
    ("map", map_run),
]

STEP_MAP = dict(STEPS)
