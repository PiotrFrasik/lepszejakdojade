"""Decoder for the Google encoded polyline format used by OTP's ``legGeometry.points``."""

from __future__ import annotations


def decode(encoded: str, precision: int = 5) -> list[list[float]]:
    """Decode a polyline into GeoJSON-ordered ``[lon, lat]`` pairs.

    Raises ValueError for a truncated or otherwise malformed string.
    """
    factor = 10**precision
    coordinates: list[list[float]] = []
    index = lat = lon = 0
    length = len(encoded)
    while index < length:
        deltas = []
        for _axis in range(2):
            result = shift = 0
            while True:
                if index >= length:
                    raise ValueError("truncated polyline")
                byte = ord(encoded[index]) - 63
                index += 1
                if not 0 <= byte < 64:
                    raise ValueError("invalid polyline character")
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coordinates.append([round(lon / factor, precision), round(lat / factor, precision)])
    return coordinates
