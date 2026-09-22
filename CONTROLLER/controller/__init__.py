"""A minimal LLM controller for the SWIM exemplar.

Five pieces, each usable on its own:

``swim``        line-oriented TCP client and the derived metrics
``actions``     the action space, its legality rules and the safety gate
``trajectory``  rolling history of observations and their outcomes
``context``     the segmented decision prompt and its probe positions
``backends``    generate/score against a served model, or a model-free stub
``policies``    SWIM's reactive rule (the oracle) and the LLM
``loop``        sense-decide-act, once per evaluation period
"""

from .actions import Action, DimmerMode, Kind
from .backends import Backend, OpenAICompatBackend, StubBackend, build_backend
from .context import DEFAULT_EXEMPLARS, ContextBuilder, ReasoningStyle
from .loop import ControlLoop
from .policies import LLMPolicy, NullPolicy, PolicyResult, ReactivePolicy
from .swim import Observation, SwimClient, SwimError, synthetic_observation
from .trajectory import Trajectory

__all__ = [
    "Action", "DimmerMode", "Kind",
    "Backend", "OpenAICompatBackend", "StubBackend", "build_backend",
    "ContextBuilder", "ReasoningStyle", "DEFAULT_EXEMPLARS",
    "ControlLoop",
    "LLMPolicy", "NullPolicy", "PolicyResult", "ReactivePolicy",
    "Observation", "SwimClient", "SwimError", "synthetic_observation",
    "Trajectory",
]
