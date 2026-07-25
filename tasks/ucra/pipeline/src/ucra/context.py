from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pandas as pd


@dataclass
class PipelineContext:
    project_dir: Path
    country: str
    crp_dir: Path
    aoi_folder: Path
    output_folder: Path
    cities: list[str]
    centroids: pd.DataFrame
    epsg_dict: dict
