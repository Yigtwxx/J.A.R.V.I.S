"""Which browser we claim to be.

One identity, used everywhere. That is a decision, not an oversight.

The tempting design is to vary the impersonation profile per host so that no
single fingerprint is reused. It is wrong here. We have one residential IP, and a
large share of the web sits behind a handful of CDNs, so an observer with a
cross-site view sees *one address* presenting several different TLS stacks. A
consistent client is ordinary; an address whose browser identity changes between
sites is not. Rotating identities is also what the old
``services/scraper_service.py`` did — its docstring records the resulting data
race as one of the reasons it was gutted.

So what this module actually contributes is the two places consistency is *not*
free:

* **Locale.** Instagram and friends localise ``og:description`` and the
  extractors parse those strings positionally, so the reply must not depend on
  where the exit IP geolocates to.
* **User-Agent matching.** A clearance cookie presented under a different
  User-Agent than the one it was issued to is worse than sending no cookie at
  all. When the browser tier earns a cookie, the HTTP tier has to borrow its UA.

Scrapling already defaults to ``impersonate="chrome"``
(``scrapling/engines/static.py:73``), so pinning it here is about making the
choice explicit and stable rather than about changing it.
"""

from __future__ import annotations

from dataclasses import dataclass

# curl_cffi impersonation target, verified against the installed
# ``curl_cffi.requests.impersonate.BrowserTypeLiteral``. The bare name tracks the
# newest profile curl ships, which is what a real Chrome does when it updates.
DEFAULT_IMPERSONATE = "chrome"

# Pinned so localised markup is deterministic for the extractors.
DEFAULT_ACCEPT_LANGUAGE = "en-US,en;q=0.9"


@dataclass(frozen=True, slots=True)
class BrowserIdentity:
    """A self-consistent client identity."""

    impersonate: str = DEFAULT_IMPERSONATE
    accept_language: str = DEFAULT_ACCEPT_LANGUAGE
    useragent: str | None = None
    """Set only when a stored cookie was earned under a specific UA we must match."""

    def headers(self) -> dict[str, str]:
        """Headers merged on top of the ones curl generates for ``impersonate``.

        Scrapling merges caller headers over its generated ones
        (``engines/static.py:170``), so these win where they overlap.
        """
        out = {"Accept-Language": self.accept_language}
        if self.useragent:
            out["User-Agent"] = self.useragent
        return out


class IdentityPicker:
    """Resolves the identity to present to a host.

    Stateless and deterministic. The only thing that varies the result is whether
    we hold a cookie for that host that was earned under a known User-Agent.
    """

    def __init__(
        self,
        *,
        impersonate: str = DEFAULT_IMPERSONATE,
        accept_language: str = DEFAULT_ACCEPT_LANGUAGE,
    ) -> None:
        self._impersonate = impersonate or DEFAULT_IMPERSONATE
        self._accept_language = accept_language or DEFAULT_ACCEPT_LANGUAGE

    def for_url(self, url: str, *, useragent: str | None = None) -> BrowserIdentity:
        """Identity for a request to ``url``.

        ``useragent`` is the UA that earned a stored cookie for this host, if any.
        When given it is adopted, and the TLS profile stays in the same browser
        family so the two halves of the identity still agree.
        """
        del url  # one identity for every host — see the module docstring
        return BrowserIdentity(
            impersonate=self._impersonate,
            accept_language=self._accept_language,
            useragent=useragent or None,
        )
