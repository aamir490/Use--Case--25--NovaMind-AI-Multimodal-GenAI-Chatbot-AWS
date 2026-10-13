"""Isolate Streamlit modules for offline tests; never import a running app."""
import importlib
import sys
from pathlib import Path
from unittest.mock import patch


def frontend_source():
    root = Path(__file__).resolve().parents[1] / "novamind"
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(root.rglob("*.py")))


class FrontendHarness:
    """Keep existing behavioral tests stable while patching the actual owners.

    UI adapters take priority over explicit-state domain functions. No production
    compatibility facade or module-global synchronization is needed by the app.
    """
    def __init__(self, modules):
        owners = {}
        for module in modules:
            for name in vars(module):
                if not name.startswith("__"):
                    owners.setdefault(name, []).append(module)
        for name, candidates in owners.items():
            ui = [module for module in candidates if module.__name__.startswith("novamind.ui.")]
            owners[name] = ui or candidates
        object.__setattr__(self, "_owners", owners)

    def __getattr__(self, name):
        for module in self._owners.get(name, []):
            if hasattr(module, name):
                return getattr(module, name)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        for module in self._owners[name]:
            setattr(module, name, value)

    def __delattr__(self, name):
        for module in self._owners[name]:
            if hasattr(module, name):
                delattr(module, name)


def load_frontend(streamlit_mock, case):
    """Fresh module imports per test, restoring the prior module cache afterward."""
    from tests.offline_support import demo_state
    streamlit_mock.session_state.update(demo_state())
    # The service fixture and UI must represent the same authenticated session.
    if hasattr(case, "service"):
        case.service._auth_session = streamlit_mock.session_state["auth_session"]
    prior = {name: module for name, module in sys.modules.items()
             if name == "novamind" or name.startswith("novamind.")}
    for name in prior:
        del sys.modules[name]

    def restore():
        for name in list(sys.modules):
            if name == "novamind" or name.startswith("novamind."):
                del sys.modules[name]
        sys.modules.update(prior)
    case.addCleanup(restore)
    sentinel = object()
    previous_streamlit = sys.modules.get("streamlit", sentinel)
    sys.modules["streamlit"] = streamlit_mock
    try:
        importlib.import_module("novamind.ui.app")
        modules = [module for name, module in sys.modules.items() if name.startswith("novamind.")]
    finally:
        if previous_streamlit is sentinel:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = previous_streamlit
    return FrontendHarness(modules)
