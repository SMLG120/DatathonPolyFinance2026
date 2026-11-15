"""Before You Buy calculation engine.

Pure and deterministic: standard library plus the shared ``byb_contracts``
package (``contracts/python`` must be importable). No AWS, no model, no clock;
all data is passed in as plain dicts in the contract shapes.
"""

from .boundary import max_compliant_amount
from .check import check_rules
from .core import compute_exposure, replay_period, simulate_change
from .version import CALCULATION_VERSION

__all__ = [
    "CALCULATION_VERSION",
    "check_rules",
    "compute_exposure",
    "max_compliant_amount",
    "replay_period",
    "simulate_change",
]
