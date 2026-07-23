"""
The single gateway to Goong's routing APIs.

Everything that needs real road distance or travel time goes through here
rather than calling httpx directly, because this layer owns four concerns
that must not be scattered across the matching code:

  1. CACHING — a fixed corridor with repeat addresses (hospitals,
     universities, the Vingroup areas in the company's own marketing)
     means the same coordinate pairs recur constantly. Cache hits are the
     difference between an affordable API bill and an unaffordable one.

  2. BATCHING — one Distance Matrix call for a whole pool evaluation
     instead of one call per pair.

  3. CIRCUIT BREAKING — when Goong is down or rate-limiting, dispatch
     must degrade, not stop. After repeated failures this stops calling
     out and serves haversine-based estimates, clearly flagged as
     degraded, until the circuit resets.

  4. HONEST FALLBACK — every result carries `is_estimate`, so callers can
     tell a real road measurement from a straight-line guess. Matching
     tightens its thresholds when running on estimates rather than
     silently pretending the numbers are as good.
"""

import hashlib
import logging
import time
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.dispatch_config import (
    CIRCUIT_FAILURE_THRESHOLD,
    CIRCUIT_RESET_SECONDS,
    FALLBACK_SPEED_KMH,
    ROUTE_CACHE_TTL_SECONDS,
    ROUTING_MAX_RETRIES,
    ROUTING_TIMEOUT_SECONDS,
)
from app.services.geo import haversine_m

logger = logging.getLogger(__name__)

GOONG_MATRIX_URL = "https://rsapi.goong.io/DistanceMatrix"
GOONG_DIRECTIONS_URL = "https://rsapi.goong.io/Direction"


@dataclass(frozen=True)
class Leg:
    """One point-to-point measurement."""

    distance_meters: float
    duration_seconds: float
    is_estimate: bool = False


@dataclass(frozen=True)
class RouteResult:
    """A full ordered route through several stops."""

    total_distance_meters: float
    total_duration_seconds: float
    geometry: str | None
    is_estimate: bool = False


Coord = tuple[float, float]  # (lat, lng)


def _fallback_leg(a: Coord, b: Coord) -> Leg:
    """
    Straight-line distance inflated by a road-winding factor, converted to
    time at a conservative average speed. Deliberately pessimistic: it is
    better to under-fill a car than to promise a customer a pickup time
    the driver cannot make.
    """
    straight = haversine_m(a[0], a[1], b[0], b[1])
    road_estimate = straight * 1.35
    seconds = (road_estimate / 1000.0) / FALLBACK_SPEED_KMH * 3600.0
    return Leg(road_estimate, seconds, is_estimate=True)


class _TTLCache:
    """
    Small in-process TTL cache. Deliberately not Redis yet — with a single
    backend container this is sufficient and has zero operational cost.
    The interface is narrow enough to swap for Redis when the app is
    scaled to multiple workers, which is the point at which a shared
    cache actually starts to matter.
    """

    def __init__(self, ttl_seconds: int, max_entries: int = 20_000):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._data: dict[str, tuple[float, object]] = {}

    def get(self, key: str):
        hit = self._data.get(key)
        if hit is None:
            return None
        expires_at, value = hit
        if time.time() > expires_at:
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: str, value: object) -> None:
        if len(self._data) >= self._max:
            # Cheap eviction: drop the oldest ~10% by expiry time.
            for k in sorted(self._data, key=lambda k: self._data[k][0])[: self._max // 10]:
                self._data.pop(k, None)
        self._data[key] = (time.time() + self._ttl, value)

    def stats(self) -> dict:
        return {"entries": len(self._data)}


class RoutingService:
    def __init__(self) -> None:
        self._cache = _TTLCache(ROUTE_CACHE_TTL_SECONDS)
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._hits = 0
        self._misses = 0
        self._degraded_calls = 0

    # ---------- circuit breaker ----------

    @property
    def _circuit_open(self) -> bool:
        return time.time() < self._circuit_open_until

    def _record_success(self) -> None:
        self._consecutive_failures = 0

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= CIRCUIT_FAILURE_THRESHOLD:
            self._circuit_open_until = time.time() + CIRCUIT_RESET_SECONDS
            logger.warning(
                "Routing circuit OPEN for %ss after %s consecutive failures; "
                "serving degraded straight-line estimates",
                CIRCUIT_RESET_SECONDS,
                self._consecutive_failures,
            )

    def _usable(self) -> bool:
        configured = bool(settings.goong_api_key) and (
            settings.goong_api_key != "your_goong_api_key"
        )
        return configured and not self._circuit_open

    # ---------- cache keys ----------

    @staticmethod
    def _key(prefix: str, coords: list[Coord]) -> str:
        # Round to ~11m. Sub-11m precision produces cache misses for what
        # is operationally the same doorstep.
        flat = ";".join(f"{lat:.4f},{lng:.4f}" for lat, lng in coords)
        return f"{prefix}:{hashlib.sha256(flat.encode()).hexdigest()[:32]}"

    # ---------- public API ----------

    def leg(self, origin: Coord, destination: Coord) -> Leg:
        """Road distance + duration for a single origin/destination pair."""
        return self.matrix([origin], [destination])[0][0]

    def matrix(
        self, origins: list[Coord], destinations: list[Coord]
    ) -> list[list[Leg]]:
        """
        Full origin x destination matrix in ONE upstream call.

        This is the primary cost lever: evaluating whether a booking fits
        a pool needs every stop-to-stop time, and fetching those
        individually would multiply the API bill by an order of
        magnitude.
        """
        cache_key = self._key("mx", origins + destinations)
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._hits += 1
            return cached  # type: ignore[return-value]
        self._misses += 1

        if not self._usable():
            self._degraded_calls += 1
            return [[_fallback_leg(o, d) for d in destinations] for o in origins]

        try:
            result = self._fetch_matrix(origins, destinations)
            self._record_success()
            self._cache.set(cache_key, result)
            return result
        except Exception as exc:
            self._record_failure()
            logger.warning("Distance matrix failed (%s); using estimates", exc)
            self._degraded_calls += 1
            return [[_fallback_leg(o, d) for d in destinations] for o in origins]

    def route(self, stops: list[Coord]) -> RouteResult:
        """
        Total distance/duration for an ordered sequence of stops, plus
        encoded geometry for driver navigation and live customer tracking.
        """
        if len(stops) < 2:
            return RouteResult(0.0, 0.0, None)

        cache_key = self._key("rt", stops)
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._hits += 1
            return cached  # type: ignore[return-value]
        self._misses += 1

        if not self._usable():
            self._degraded_calls += 1
            return self._fallback_route(stops)

        try:
            result = self._fetch_route(stops)
            self._record_success()
            self._cache.set(cache_key, result)
            return result
        except Exception as exc:
            self._record_failure()
            logger.warning("Directions failed (%s); using estimates", exc)
            self._degraded_calls += 1
            return self._fallback_route(stops)

    def health(self) -> dict:
        total = self._hits + self._misses
        return {
            "circuit_open": self._circuit_open,
            "consecutive_failures": self._consecutive_failures,
            "cache_hit_rate": round(self._hits / total, 3) if total else None,
            "degraded_calls": self._degraded_calls,
            **self._cache.stats(),
        }

    # ---------- upstream calls ----------

    def _fetch_matrix(
        self, origins: list[Coord], destinations: list[Coord]
    ) -> list[list[Leg]]:
        params = {
            "origins": "|".join(f"{lat},{lng}" for lat, lng in origins),
            "destinations": "|".join(f"{lat},{lng}" for lat, lng in destinations),
            "vehicle": "car",
            "api_key": settings.goong_api_key,
        }
        data = self._request(GOONG_MATRIX_URL, params)

        rows = data.get("rows", [])
        if len(rows) != len(origins):
            raise ValueError(
                f"matrix shape mismatch: {len(rows)} rows for {len(origins)} origins"
            )

        out: list[list[Leg]] = []
        for i, row in enumerate(rows):
            elements = row.get("elements", [])
            if len(elements) != len(destinations):
                raise ValueError("matrix row width mismatch")
            legs = []
            for j, el in enumerate(elements):
                # Goong marks unreachable pairs per-element; fall back for
                # just that pair rather than discarding the whole matrix.
                if el.get("status") not in (None, "OK"):
                    legs.append(_fallback_leg(origins[i], destinations[j]))
                    continue
                legs.append(
                    Leg(
                        float(el["distance"]["value"]),
                        float(el["duration"]["value"]),
                    )
                )
            out.append(legs)
        return out

    def _fetch_route(self, stops: list[Coord]) -> RouteResult:
        origin = stops[0]
        destination = stops[-1]
        waypoints = stops[1:-1]

        params = {
            "origin": f"{origin[0]},{origin[1]}",
            "destination": f"{destination[0]},{destination[1]}",
            "vehicle": "car",
            "api_key": settings.goong_api_key,
        }
        if waypoints:
            params["waypoints"] = "|".join(f"{lat},{lng}" for lat, lng in waypoints)

        data = self._request(GOONG_DIRECTIONS_URL, params)
        routes = data.get("routes") or []
        if not routes:
            raise ValueError("no route returned")

        legs = routes[0].get("legs", [])
        total_m = sum(float(l["distance"]["value"]) for l in legs)
        total_s = sum(float(l["duration"]["value"]) for l in legs)
        geometry = (routes[0].get("overview_polyline") or {}).get("points")
        return RouteResult(total_m, total_s, geometry)

    def _request(self, url: str, params: dict) -> dict:
        last_exc: Exception | None = None
        for attempt in range(ROUTING_MAX_RETRIES + 1):
            try:
                resp = httpx.get(url, params=params, timeout=ROUTING_TIMEOUT_SECONDS)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:  # noqa: BLE001 - retried then surfaced
                last_exc = exc
                if attempt < ROUTING_MAX_RETRIES:
                    time.sleep(0.25 * (2**attempt))  # backoff
        raise last_exc  # type: ignore[misc]

    def _fallback_route(self, stops: list[Coord]) -> RouteResult:
        total_m = 0.0
        total_s = 0.0
        for a, b in zip(stops, stops[1:]):
            leg = _fallback_leg(a, b)
            total_m += leg.distance_meters
            total_s += leg.duration_seconds
        return RouteResult(total_m, total_s, None, is_estimate=True)


# Module-level singleton so the cache and circuit state are shared across
# requests within a worker.
routing_service = RoutingService()
