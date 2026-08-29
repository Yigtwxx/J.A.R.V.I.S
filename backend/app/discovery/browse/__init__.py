"""The interactive browse tier: a driven browser, as a last resort.

The pipeline's transports answer one question — "what does this URL return?".
This package answers a different one: "what is on this page once a person has
scrolled it, dismissed the banner and expanded the section?".

It is deliberately the *last* resort. A step costs a local vision inference and
a browser page costs 50-150 MB, so the tier runs once per search, on a handful
of targets that something already points at, and only where the cheap tiers were
refused or came back empty.

Two boundaries hold the whole design up:

* ``guard.check`` runs before every action, and the browser never logs in.
* The model never writes evidence. It manoeuvres the page; the terminal harvest
  reads the DOM with the pipeline's existing extractors, and a value the DOM
  never contained is dropped and counted.
"""

from app.discovery.browse.types import (
    CONCLUSIVE_OUTCOMES,
    ActionKind,
    BrowseAction,
    BrowseOutcome,
    BrowseReport,
    BrowseStep,
    BrowseTask,
    Element,
    Observation,
    Refusal,
    RefusalReason,
)

__all__ = [
    "CONCLUSIVE_OUTCOMES",
    "ActionKind",
    "BrowseAction",
    "BrowseOutcome",
    "BrowseReport",
    "BrowseStep",
    "BrowseTask",
    "Element",
    "Observation",
    "Refusal",
    "RefusalReason",
]
