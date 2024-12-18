from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime

from pathlib import Path

@dataclass
class XBRLFile:
    path: Path
    file_type: str
    namespaces: Dict[str, str]
    root_element: str
    role_refs: Dict[str, str] = field(default_factory=dict)


@dataclass
class XBRLContext:
    id: str
    entity: str
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    instant: Optional[datetime] = None
    scenario: Optional[Dict[str, Any]] = None

    @property
    def is_duration(self) -> bool:
        return self.period_start is not None and self.period_end is not None

    @property
    def is_instant(self) -> bool:
        return self.instant is not None


@dataclass
class XBRLUnit:
    id: str
    measures: List[str]  # e.g., ['iso4217:USD'] or ['xbrli:pure']
    divide: bool = False  # True if it's a divide relationship (e.g., shares/shares)
    numerator: List[str] = field(default_factory=list)
    denominator: List[str] = field(default_factory=list)


@dataclass
class XBRLFact:
    concept: str
    value: Any
    context_ref: str
    unit_ref: Optional[str] = None
    decimals: Optional[int] = None
    precision: Optional[int] = None