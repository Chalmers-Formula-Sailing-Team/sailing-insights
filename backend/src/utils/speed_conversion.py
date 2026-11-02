import numpy as np


def mps_to_kn(speed_mps: float | np.ndarray) -> float | np.ndarray:
    return speed_mps * 1.9438444924406046
