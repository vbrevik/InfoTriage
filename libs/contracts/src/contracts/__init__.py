"""contracts — InfoTriage shared schemas, codec, and bus interface.

Single source of truth for all InfoTriage apps:

    from contracts import Item
    from contracts import ItemIngested, VerdictReady, SabPublished, FeedUnhealthy
    from contracts import to_frontmatter, from_frontmatter
    from contracts import BusClient, InMemoryBus
    from contracts import setup_logging
    from contracts import LOGGING_CONFIG  # Phase 7 07-02: uvicorn JSON access logs
"""

from ._item import Item
from ._events import ItemIngested, VerdictReady, SabPublished, FeedUnhealthy
from ._codec import to_frontmatter, from_frontmatter
from ._bus import BusClient, InMemoryBus
from ._bus_rabbitmq import RabbitMQBus
from ._logging import setup_logging
from .uvicorn_log_config import LOGGING_CONFIG
from ._verify import (
    CITATION_INSTRUCTION,
    CONTRADICTION_INSTRUCTION,
    CROSS_LANGUAGE_INSTRUCTION,
    verify_language_coverage,
)
from ._translation import translate_to, TranslationCache
from ._phase11_gates import (
    require_discipline,
    require_acled_license,
    DisciplineRequired,
    AcledLicenseMissing,
)

__all__ = [
    "Item",
    "ItemIngested",
    "VerdictReady",
    "SabPublished",
    "FeedUnhealthy",
    "to_frontmatter",
    "from_frontmatter",
    "BusClient",
    "InMemoryBus",
    "RabbitMQBus",
    "setup_logging",
    "LOGGING_CONFIG",
    "verify_language_coverage",
    "CITATION_INSTRUCTION",
    "CROSS_LANGUAGE_INSTRUCTION",
    "CONTRADICTION_INSTRUCTION",
    "translate_to",
    "TranslationCache",
    "require_discipline",
    "require_acled_license",
    "DisciplineRequired",
    "AcledLicenseMissing",
    "CCIR",
    "CCIRSpec",
    "active_specs",
    "CCIR_ORDER",
    "COP_CCIR",
    "build_scorer_block",
    "build_quickref",
    "build_examples_and_guide",
    "active_ccir_enum",
    "render_feeds_opml_groups",
]

from .ccir import (  # noqa: E402
    CCIR,
    CCIRSpec,
    active_specs,
    CCIR_ORDER,
    COP_CCIR,
    build_scorer_block,
    build_quickref,
    build_examples_and_guide,
    active_ccir_enum,
    render_feeds_opml_groups,
)
