"""Missing Holdings Evidence Investigator (additive, read-only).

Explains what the data snapshot does and does not hold about a fund's constituents, and what the
unresolved part could mean for an investor's rules. It never produces a rule verdict (those come from
``backend.engine``), never stores anything, and never fills a gap: a value that is not in the snapshot
is reported as unknown (``None``), not as zero.

* ``scanner``  what is held, what is missing, coverage on a justified basis, source confidence
* ``bounds``   conditional exposure intervals (LEAD_DECISIONS D4), fund level and portfolio level
* ``wording``  the four-part answer written by the server, and the optional, guarded model wording
* ``service``  one investigation: scan -> bounds -> answer
* ``route``    ``POST /evidence/investigate``

Standard library only (the model call uses the ``boto3`` client the Lambda runtime provides).
Percentages are percentage points (10% = 10.0) and are derived from the snapshot's fractions.
"""

from .service import investigate

__all__ = ["investigate"]
