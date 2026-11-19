"""HydroMet item folders as the Climate DT workflow writes them.

The workflow (lib/common/utils/app_utils.sh, get_stac_structure, together with
HYDROMET.UPLOAD_READY) writes the upload files of one experiment to

    <member>/EO.DWD.STAT.HYDROMET/data/<YYYY>/<item>/

    <item> = EO.DWD.STAT.HYDROMET_EXTREMES_<start>T000000_<end>T230000
             __<model>__<experiment>__<generation>__<realization>__<activity>__<resolution>

EO.DWD.STAT.HYDROMET is the bucket root, not an extra folder level: its
metadata/ and data/ land at the root of the bucket on upload. <YYYY> is the
start year of the experiment, and <start>/<end> are the first and last day of
the experiment, so the period comes from the workflow and is not fixed here.
The suffix values are the workflow's REQUEST values, taken as they are.

The item folder holds a flat set of files:
    <start>_to_<end>_KO_params.nc, <start>_to_<end>_DDF.nc   (Kostradamus)
    <start>_to_<end>_events_<threshold>_<REGION>.csv          (one per region)

Shared by stage.py and move.py, which run from staging/ and so find this
module on sys.path. check_data.sh applies the same rules in plain bash.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Every upload file starts with the period it covers.
FILENAME_RE = re.compile(
    r"^\d{4}_\d{2}_\d{2}_T\d{2}_\d{2}_to_\d{4}_\d{2}_\d{2}_T\d{2}_\d{2}_.+\.(nc|csv)$"
)

_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%S"


@dataclass(frozen=True)
class WorkflowItem:
    """One item folder, parsed from its name."""

    path: Path
    year_folder: str
    start: datetime
    end: datetime
    properties: dict[str, str]

    @property
    def name(self) -> str:
        return self.path.name


def parse_item_name(
    name: str, collection_id: str, property_keys: list[str]
) -> tuple[datetime, datetime, dict[str, str]]:
    """Split an item folder name into start, end and its suffix properties.

    Raises ValueError with a readable reason when the name does not follow
    <collection_id>_<start>_<end>__<v1>__...__<vN>, N = len(property_keys).
    """
    prefix = f"{collection_id}_"
    if not name.startswith(prefix):
        raise ValueError(f"does not start with '{prefix}'")

    head, *values = name[len(prefix):].split("__")
    if len(values) != len(property_keys):
        raise ValueError(
            f"has {len(values)} '__' suffix values, expected {len(property_keys)} "
            f"({', '.join(property_keys)})"
        )
    empty = [k for k, v in zip(property_keys, values) if not v]
    if empty:
        raise ValueError(f"has empty suffix values for {', '.join(empty)}")

    stamps = head.split("_")
    if len(stamps) != 2:
        raise ValueError("expected '<start>_<end>' timestamps after the collection id")
    try:
        start, end = (datetime.strptime(s, _TIMESTAMP_FORMAT) for s in stamps)
    except ValueError as exc:
        raise ValueError(f"has an invalid timestamp ({exc})") from None
    if end < start:
        raise ValueError("ends before it starts")

    return start, end, dict(zip(property_keys, values))


def resolve_data_dir(source: Path, root_dir_name: str) -> Path:
    """Find the data/ folder for a workflow output path.

    Accepts the bucket root folder (holding data/), the member folder the
    workflow writes it into (holding <root_dir_name>/data/), or data/ itself.
    """
    candidates = [source / "data", source / root_dir_name / "data"]
    if source.name == "data":
        candidates.insert(0, source)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        f"No data/ folder in {source} or {source / root_dir_name}. Pass the "
        f"{root_dir_name} folder the workflow wrote, or the member folder holding it."
    )


def find_item_dirs(data_dir: Path) -> list[Path]:
    """All data/<YYYY>/<item>/ folders, sorted."""
    return sorted(
        item
        for year in data_dir.iterdir() if year.is_dir()
        for item in year.iterdir() if item.is_dir()
    )


def load_item(
    item_dir: Path, collection_id: str, property_keys: list[str]
) -> WorkflowItem:
    """Parse and check one item folder. Raises ValueError on any problem."""
    start, end, properties = parse_item_name(item_dir.name, collection_id, property_keys)
    year_folder = item_dir.parent.name
    if year_folder != f"{start:%Y}":
        raise ValueError(
            f"is in year folder {year_folder}, but starts in {start:%Y}"
        )
    return WorkflowItem(item_dir, year_folder, start, end, properties)
