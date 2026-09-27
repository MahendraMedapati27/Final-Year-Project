"""IMD-style palette with CIEDE2000 / CVD checks (P2.6)."""



from __future__ import annotations



import json

from typing import Any



import numpy as np

from colorspacious import cspace_convert



from rainfall.classes import INTENSITY_BOUNDS, INTENSITY_LABELS

from rainfall.config import resolve_path



# Chosen to satisfy L* steps and delta-E (validated at import / gate)

PALETTE_HEX = [
    "#EFEFEF",  # No Rain
    "#B8D8F0",  # Very Light
    "#68A8D8",  # Light
    "#3878A8",  # Moderate
    "#204870",  # Heavy
    "#102840",  # Very Heavy
    "#081820",  # Extremely Heavy
]

NODATA_FACE = "#989898"
OUTSIDE_FILL = "#D4D0C8"

BG_WHITE = "#FFFFFF"



CLASS_RANGES = [

    "0",

    "0.1–2.4",

    "2.5–15.5",

    "15.6–64.4",

    "64.5–115.5",

    "115.6–204.4",

    "≥204.5",

]





def _hex_to_lab(hexes: list[str]) -> np.ndarray:

    rgb = []

    for h in hexes:

        h = h.lstrip("#")

        rgb.append([int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4)])

    arr = np.array(rgb)

    return cspace_convert(arr, "sRGB1", "CIELab")





def _delta_e(lab1: np.ndarray, lab2: np.ndarray) -> float:

    from colour.difference import delta_E_CIE2000



    return float(delta_E_CIE2000(lab1.reshape(1, 3), lab2.reshape(1, 3))[0])





def _srgb_to_lms(rgb: np.ndarray) -> np.ndarray:
    """rgb: Nx3 linear sRGB."""
    m = np.array(
        [
            [0.386969, 0.627304, -0.014272],
            [0.121521, 0.811988, 0.066491],
            [-0.010528, 0.035508, 0.933020],
        ]
    )
    return rgb @ m.T


def _lms_to_srgb(lms: np.ndarray) -> np.ndarray:
    m = np.array(
        [
            [2.037035, -1.444492, 0.321457],
            [-0.969266, 1.875990, 0.093276],
            [0.013447, -0.118373, 1.104926],
        ]
    )
    lin = lms @ m.T
    lin = np.clip(lin, 0, None)
    return np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.power(lin, 1 / 2.4) - 0.055)


def simulate_cvd(hexes: list[str], kind: str) -> list[str]:
    """kind: protanomaly | deuteranomaly (Machado et al. 2009, severity 100)."""
    from colorspacious.cvd import machado_et_al_2009_matrix

    cvd_type = "protanomaly" if "prot" in kind else "deuteranomaly"
    mat = machado_et_al_2009_matrix(cvd_type, 100)
    out = []
    for h in hexes:
        h = h.lstrip("#")
        srgb = np.array([int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4)])
        lin = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
        lms = _srgb_to_lms(lin.reshape(1, 3))
        sim = (mat @ lms.T).T
        back = _lms_to_srgb(sim)[0]
        out.append(
            "#{:02x}{:02x}{:02x}".format(
                int(np.clip(back[0], 0, 1) * 255),
                int(np.clip(back[1], 0, 1) * 255),
                int(np.clip(back[2], 0, 1) * 255),
            )
        )
    return out





def validate_palette() -> dict[str, Any]:

    labs = _hex_to_lab(PALETTE_HEX)

    l_stars = labs[:, 0].tolist()

    adj_de = [_delta_e(labs[i], labs[i + 1]) for i in range(len(labs) - 1)]

    neutral_labs = _hex_to_lab([NODATA_FACE, OUTSIDE_FILL, BG_WHITE, PALETTE_HEX[0]])

    neutral_de = {

        "no_rain_vs_nodata": _delta_e(neutral_labs[3], neutral_labs[0]),

        "nodata_vs_outside": _delta_e(neutral_labs[0], neutral_labs[1]),

        "outside_vs_white": _delta_e(neutral_labs[1], neutral_labs[2]),

    }

    l_steps = [l_stars[i] - l_stars[i + 1] for i in range(len(l_stars) - 1)]



    def cvd_checks(kind: str) -> dict[str, Any]:

        sim = simulate_cvd(PALETTE_HEX, kind)

        sl = _hex_to_lab(sim)

        return {

            "adjacent_min_delta_e": min(_delta_e(sl[i], sl[i + 1]) for i in range(len(sl) - 1)),

            "l_star": sl[:, 0].tolist(),

        }



    ok_adj = all(d >= 8 for d in adj_de)

    ok_neutral = all(v >= 10 for v in neutral_de.values())

    ok_l = all(s >= 6 for s in l_steps) and l_stars[-1] < l_stars[-2]

    deut = cvd_checks("deuteranomaly")

    prot = cvd_checks("protanomaly")

    ok_cvd = deut["adjacent_min_delta_e"] >= 8 and prot["adjacent_min_delta_e"] >= 8



    payload = {

        "palette_hex": PALETTE_HEX,

        "L_star": l_stars,

        "L_steps": l_steps,

        "adjacent_delta_e": adj_de,

        "neutral_delta_e": neutral_de,

        "deuteranopia": deut,

        "protanopia": prot,

        "pass_adjacent_8": ok_adj,

        "pass_neutral_10": ok_neutral,

        "pass_L_monotone": ok_l,

        "pass_cvd": ok_cvd,

        "pass_all": ok_adj and ok_neutral and ok_l and ok_cvd,

    }

    resolve_path("outputs/checkpoints/p2_palette.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return payload





def intensity_bounds_for_norm() -> list[float]:

    return INTENSITY_BOUNDS

