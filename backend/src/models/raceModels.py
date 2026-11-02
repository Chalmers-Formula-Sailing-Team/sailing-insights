from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(slots=True)
class Race:
    id: str
    name: str
    start_at: np.datetime64 | None
    finish_at: np.datetime64 | None

    metadata: dict[str, Any] = field(default_factory=dict)
