"""Mock Record-Replay Engine.

Entry point: MockEngine ties recorder, matcher, and replayer together.
Use ``registry`` to obtain project-scoped singletons.
"""

from .engine import MockEngine, MockEngineRegistry, registry
from .recorder import shutdown_all

__all__ = ["MockEngine", "MockEngineRegistry", "registry", "shutdown_all"]
