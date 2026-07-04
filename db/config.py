
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
import os


REPO_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(REPO_ROOT / ".env")


# UTM Zone 34N — projected CRS used for all metric calculations in Sofia.
TARGET_CRS = "EPSG:32634"


@dataclass(frozen=True)
class DBSettings:
    user: str
    password: str
    host: str
    port: str
    name: str

    @property
    def sqlalchemy_url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass(frozen=True)
class GeoJSONDataset:
    table_name: str
    path: Path
    index_label: str = "poi_id"


settings = DBSettings(
    user=os.environ.get("DB_USER", "postgres"),
    password=os.environ.get("DB_PASS", "mysecretpassword"),
    host=os.environ.get("DB_HOST", "localhost"),
    port=os.environ.get("DB_PORT", "5432"),
    name=os.environ.get("DB_NAME", "gis_db"),
)


# Default input data paths used by the load step.
DATA_DIR = REPO_ROOT / "data"
GEOJSON_DIR = DATA_DIR / "geojson"
BUILDINGS_GEOJSON = DATA_DIR / "geojson" / "buildings" / "buildings.geojson"
PEDESTRIAN_NETWORK_GEOJSON = DATA_DIR / "geojson" / "pedestrian_network.geojson"


POINT_OF_INTEREST_GEOJSONS = (
    GeoJSONDataset(
        table_name="schools_points",
        path=GEOJSON_DIR / "education" / "schools_points.geojson",
    ),
    GeoJSONDataset(
        table_name="parks_and_gardens",
        path=GEOJSON_DIR / "green_areas" / "parks_and_gardens.geojson",
    ),
    GeoJSONDataset(
        table_name="hospitals",
        path=GEOJSON_DIR / "health" / "hospitals.geojson",
    ),
    GeoJSONDataset(
        table_name="supermarkets",
        path=GEOJSON_DIR / "services" / "supermarkets.geojson",
    ),
    GeoJSONDataset(
        table_name="overground_stops",
        path=GEOJSON_DIR / "transit" / "overground_stops.geojson",
    ),
)

# Output paths.
OUTPUT_DIR = REPO_ROOT / "output"
WALKABILITY_MAP_HTML = OUTPUT_DIR / "walkability_map.html"
