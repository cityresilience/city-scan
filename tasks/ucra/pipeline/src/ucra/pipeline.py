# from __future__ import annotations

# from pathlib import Path

# from ucra.modules import bootstrap, cckp, environment, lst_and_stats, urban_coastal, wsf_drought


# def run_pipeline(project_dir: str | Path, country: str) -> None:
#     ctx = bootstrap.run(project_dir=project_dir, country=country)
#     urban_coastal.run(ctx)
#     cckp.run(ctx)
#     environment.run(ctx)
#     wsf_drought.run(ctx)
#     lst_and_stats.run(ctx)
    
from __future__ import annotations

from pathlib import Path

from ucra.config import load_config
from ucra.modules import bootstrap, cckp, environment, lst_and_stats, urban_coastal, wsf_drought


def run_pipeline(project_dir: str | Path, country: str, config_path: str | Path | None = None) -> None:
    cfg = load_config(config_path) if config_path else {}

    run_urban_coastal = cfg.get("run_urban_coastal", True)
    run_cckp = cfg.get("run_cckp", True)
    run_environment = cfg.get("run_environment", True)
    run_wsf_drought = cfg.get("run_wsf_drought", True)
    run_lst_and_stats = cfg.get("run_lst_and_stats", True)

    # bootstrap must still run because it builds the PipelineContext
    ctx = bootstrap.run(project_dir=project_dir, country=country)

    if run_urban_coastal:
        urban_coastal.run(ctx)

    if run_cckp:
        cckp.run(ctx)

    if run_environment:
        environment.run(ctx)

    if run_wsf_drought:
        wsf_drought.run(ctx)

    if run_lst_and_stats:
        lst_and_stats.run(ctx)
