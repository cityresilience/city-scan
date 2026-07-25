from __future__ import annotations

import ee


def initialize_earth_engine(
    project: str | None = None,
    auth_mode: str = "notebook",
    force_auth: bool = False,
) -> None:
    """
    Initialize Google Earth Engine in a repo-friendly way.

    Default behavior uses notebook mode so the user can authenticate in a browser
    and paste the authorization code back, which matches the desired Jupyter flow.
    """
    init_kwargs = {}
    if project:
        init_kwargs["project"] = project

    if force_auth:
        ee.Authenticate(auth_mode=auth_mode)
        ee.Initialize(**init_kwargs)
        return

    try:
        ee.Initialize(**init_kwargs)
    except Exception:
        print(
            "Earth Engine credentials not available or invalid.\n"
            f"Starting authentication with auth_mode='{auth_mode}'..."
        )
        ee.Authenticate(auth_mode=auth_mode)
        ee.Initialize(**init_kwargs)