"""Utilities for generating crystal structure scenes."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

from fastapi import HTTPException, status

log = logging.getLogger(__name__)


def _ensure_crystal_dependencies():
    """Import heavy crystal tooling lazily and raise HTTP-friendly errors."""

    try:  # pragma: no cover - optional heavyweight deps
        from pymatgen.analysis.graphs import StructureGraph  # type: ignore
        from pymatgen.analysis.local_env import MinimumDistanceNN  # type: ignore
        from crystal_toolkit.core.legend import Legend  # type: ignore

        # Ensure CTK monkey patches StructureGraph.get_scene
        from crystal_toolkit.renderables import (  # type: ignore  # noqa: F401
            structuregraph as _ct_structuregraph,
        )
    except Exception as exc:  # pragma: no cover - env specific
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Crystal structure dependencies are unavailable. "
                "Install 'pymatgen' and 'crystal-toolkit'."
            ),
        ) from exc

    return StructureGraph, MinimumDistanceNN, Legend


def structure_to_scene_dict(structure, *, radius_strategy: str = "uniform") -> Dict[str, Any]:
    """Convert a pymatgen Structure to CrystalToolkitScene JSON including bonds."""

    StructureGraph, MinimumDistanceNN, Legend = _ensure_crystal_dependencies()

    try:  # pragma: no cover - heavy math branches
        graph = StructureGraph.from_local_env_strategy(structure, MinimumDistanceNN())
        legend = Legend(structure, radius_scheme=radius_strategy)
        scene_obj = graph.get_scene(
            draw_image_atoms=True,
            bonded_sites_outside_unit_cell=True,
            hide_incomplete_edges=True,
            legend=legend,
        )
        scene_json = scene_obj.to_json()

        _append_axes(scene_json, getattr(structure, "lattice", None))
        return scene_json
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - env dependent
        log.exception("Failed to build CrystalToolkit scene", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate crystal scene from structure.",
        ) from exc


def _append_axes(scene_json: Dict[str, Any], lattice) -> None:
    """Append lattice or cartesian axes to the scene JSON in-place."""

    if lattice is None:
        return

    try:  # pragma: no cover - arithmetic heavy
        mode = os.getenv("CT_AXES_MODE", "lattice").lower()
        scale = float(os.getenv("CT_AXES_SCALE", "1.6"))
        head_len = float(os.getenv("CT_AXES_HEAD_LENGTH", "0.32"))
        head_wid = float(os.getenv("CT_AXES_HEAD_WIDTH", "0.18"))
        radius = float(os.getenv("CT_AXES_RADIUS", "0.07"))

        if mode == "cartesian":
            axes_vectors = [
                [scale, 0.0, 0.0],
                [0.0, scale, 0.0],
                [0.0, 0.0, scale],
            ]
        else:
            matrix = lattice.matrix

            def _normalized(vec):
                norm = (vec[0] ** 2 + vec[1] ** 2 + vec[2] ** 2) ** 0.5 or 1.0
                return [float(v) / norm * scale for v in vec]

            axes_vectors = [_normalized(row) for row in matrix]

        colors = ["red", "green", "blue"]
        contents = []
        for vec, color in zip(axes_vectors, colors):
            contents.append(
                {
                    "type": "arrows",
                    "positionPairs": [[[0.0, 0.0, 0.0], vec]],
                    "color": color,
                    "radius": radius,
                    "headLength": head_len,
                    "headWidth": head_wid,
                    "clickable": False,
                }
            )

        scene_json.setdefault("contents", []).append(
            {
                "name": "axes",
                "contents": contents,
                "origin": scene_json.get("origin", [0.0, 0.0, 0.0]),
                "visible": True,
            }
        )
    except Exception as exc:  # pragma: no cover - optional feature
        log.debug("Skipping axes augmentation due to error: %s", exc)


def cif_file_to_scene(file_path: str, *, radius_strategy: str = "uniform") -> Dict[str, Any]:
    """Load a CIF file into a CrystalToolkitScene JSON representation."""

    try:  # pragma: no cover - heavy dependency
        from pymatgen.core.structure import Structure  # type: ignore
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Crystal structure dependencies are unavailable. "
                "Install 'pymatgen' and 'crystal-toolkit'."
            ),
        ) from exc

    try:
        structure = Structure.from_file(file_path)
    except Exception as exc:
        log.exception("Failed to parse CIF file", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to parse CIF file.",
        ) from exc

    return structure_to_scene_dict(structure, radius_strategy=radius_strategy)


def vasp_poscar_file_to_scene(
    file_path: str, *, radius_strategy: str = "uniform"
) -> Dict[str, Any]:
    """Load a VASP POSCAR/CONTCAR file into a CrystalToolkitScene representation."""

    try:  # pragma: no cover - heavy dependency
        from pymatgen.core.structure import Structure  # type: ignore
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Crystal structure dependencies are unavailable. "
                "Install 'pymatgen' and 'crystal-toolkit'."
            ),
        ) from exc

    try:
        structure = Structure.from_file(file_path)
    except Exception as exc:
        log.exception("Failed to parse VASP POSCAR/CONTCAR file", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to parse VASP POSCAR/CONTCAR file.",
        ) from exc

    return structure_to_scene_dict(structure, radius_strategy=radius_strategy)


def cif_string_to_scene(content: str, *, radius_strategy: str = "uniform") -> Dict[str, Any]:
    """Convert CIF content provided as a string to a scene JSON representation."""

    try:  # pragma: no cover - heavy dependency
        from pymatgen.core.structure import Structure  # type: ignore
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Crystal structure dependencies are unavailable. "
                "Install 'pymatgen' and 'crystal-toolkit'."
            ),
        ) from exc

    try:
        structure = Structure.from_str(content, fmt="cif")
    except Exception as exc:
        log.exception("Failed to parse CIF content", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to parse CIF content.",
        ) from exc

    return structure_to_scene_dict(structure, radius_strategy=radius_strategy)
