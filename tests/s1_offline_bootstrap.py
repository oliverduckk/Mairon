"""Test-only absent SDK stand-ins. No real provider, OAuth or network access."""
import sys
import types


def _stub(full_name, **attributes):
    module = types.ModuleType(full_name)
    module.__dict__.update(attributes)
    module.__path__ = []  # support parent package imports
    sys.modules[full_name] = module
    if '.' in full_name:
        parent, child = full_name.rsplit('.', 1)
        if parent in sys.modules:
            setattr(sys.modules[parent], child, module)
    return module


if "openai" not in sys.modules:
    _stub("openai", OpenAI=type("OfflineOpenAI", (), {}))
if "ollama" not in sys.modules:
    _stub("ollama", Client=type("OfflineOllama", (), {}))
if "tavily" not in sys.modules:
    _stub("tavily", TavilyClient=type("OfflineTavily", (), {}))
for package in (
    "google", "google.auth", "google.auth.transport", "google.oauth2",
    "google_auth_oauthlib", "googleapiclient",
):
    _stub(package)
_stub("google.auth.transport.requests", Request=type("OfflineRequest", (), {}))
_stub("google.auth.exceptions", RefreshError=type("RefreshError", (Exception,), {}))
_stub("google.oauth2.credentials", Credentials=type("OfflineCredentials", (), {}))
_stub("google_auth_oauthlib.flow", InstalledAppFlow=type("OfflineFlow", (), {}))
_stub("googleapiclient.discovery", build=lambda *a, **k: None)
_stub("googleapiclient.errors", HttpError=type("HttpError", (Exception,), {}))
