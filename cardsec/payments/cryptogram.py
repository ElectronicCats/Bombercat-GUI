"""Análisis puro de criptogramas EMV sobre un conjunto de capturas (`EmvCard`).

Detecta indicios de riesgo de **replay** y de generación débil, comparando el
Application Transaction Counter (ATC), el criptograma (ARQC) y el Unpredictable
Number (UN) entre capturas de la misma tarjeta:

  * ATC duplicado           -> misma cuenta reutilizada (captura/replay).
  * ATC no creciente         -> orden anómalo.
  * ARQC repetido            -> criptograma reutilizado (grave).
  * UN reutilizado           -> RNG de terminal débil o replay.
  * huecos de ATC            -> transacciones intermedias no capturadas (informativo).

Todo es puro y testeable con los `mock_card_ATC*.json` reales.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .emvcard import EmvCard

SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3}


@dataclass(frozen=True)
class Observation:
    kind: str
    severity: str  # info | low | medium | high
    message: str
    detail: str = ""


@dataclass
class CryptogramReport:
    pan: str = ""
    count: int = 0
    atc_values: list[int] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)

    @property
    def max_severity(self) -> str:
        if not self.observations:
            return "info"
        return max(
            (o.severity for o in self.observations), key=lambda s: SEVERITY_ORDER[s]
        )

    @property
    def replay_risk(self) -> bool:
        return any(o.severity in ("medium", "high") for o in self.observations)

    def summary(self) -> str:
        lines = [
            f"PAN {self.pan or '?'} — {self.count} captura(s), "
            f"ATC {self._atc_range()}"
        ]
        for o in self.observations:
            lines.append(
                f"  [{o.severity.upper()}] {o.message}"
                + (f" — {o.detail}" if o.detail else "")
            )
        if not self.observations:
            lines.append("  (sin anomalías: ATC creciente, ARQC y UN únicos)")
        return "\n".join(lines)

    def _atc_range(self) -> str:
        if not self.atc_values:
            return "?"
        lo, hi = min(self.atc_values), max(self.atc_values)
        return f"{lo:04X}..{hi:04X}"

    def to_dict(self) -> dict:
        return {
            "pan": self.pan,
            "count": self.count,
            "atc_values": [f"{v:04X}" for v in self.atc_values],
            "max_severity": self.max_severity,
            "replay_risk": self.replay_risk,
            "observations": [vars(o) for o in self.observations],
        }


def _atc_int(card: EmvCard) -> int | None:
    if not card.atc:
        return None
    try:
        return int(card.atc, 16)
    except ValueError:
        return None


def analyze(cards: list[EmvCard]) -> CryptogramReport:
    """Analiza un conjunto de capturas de (idealmente) la misma tarjeta."""
    pans = {c.pan_digits for c in cards if c.pan_digits}
    pan = (
        next(iter(pans)) if len(pans) == 1 else (",".join(sorted(pans)) if pans else "")
    )
    rep = CryptogramReport(pan=pan, count=len(cards))
    obs = rep.observations

    if len(pans) > 1:
        obs.append(
            Observation(
                "mixed_pan",
                "info",
                "El conjunto mezcla varias tarjetas",
                f"PANs: {', '.join(sorted(pans))}",
            )
        )

    atcs = [a for a in (_atc_int(c) for c in cards) if a is not None]
    rep.atc_values = sorted(atcs)

    # ATC duplicado
    for atc, n in Counter(atcs).items():
        if n > 1:
            obs.append(
                Observation(
                    "atc_dup",
                    "high",
                    f"ATC {atc:04X} aparece {n} veces",
                    "misma cuenta reutilizada — riesgo de replay/captura repetida",
                )
            )

    # ARQC repetido (entre ATC distintos)
    arqc_to_atc = defaultdict(set)
    for c in cards:
        if c.arqc and _atc_int(c) is not None:
            arqc_to_atc[c.arqc].add(_atc_int(c))
    for arqc, atc_set in arqc_to_atc.items():
        if len(atc_set) > 1:
            obs.append(
                Observation(
                    "arqc_reuse",
                    "high",
                    f"ARQC {arqc} compartido por varios ATC",
                    f"ATC: {', '.join(f'{a:04X}' for a in sorted(atc_set))}",
                )
            )
    dup_arqc = [a for a, n in Counter(c.arqc for c in cards if c.arqc).items() if n > 1]
    for a in dup_arqc:
        if a not in arqc_to_atc or len(arqc_to_atc[a]) == 1:
            obs.append(
                Observation(
                    "arqc_dup",
                    "high",
                    f"ARQC {a} idéntico en múltiples capturas",
                    "criptograma reutilizado — replay directo",
                )
            )

    # UN reutilizado
    for un, n in Counter(c.un for c in cards if c.un).items():
        if n > 1:
            obs.append(
                Observation(
                    "un_reuse",
                    "medium",
                    f"UN {un} reutilizado en {n} capturas",
                    "RNG de terminal débil o replay del mismo desafío",
                )
            )

    # secuencia de ATC: huecos
    uniq = sorted(set(atcs))
    for prev, nxt in zip(uniq, uniq[1:]):
        gap = nxt - prev
        if gap > 1:
            obs.append(
                Observation(
                    "atc_gap",
                    "info",
                    f"Hueco de ATC {prev:04X}→{nxt:04X} (+{gap})",
                    "transacciones intermedias no capturadas",
                )
            )

    return rep


def analyze_by_pan(cards: list[EmvCard]) -> dict[str, CryptogramReport]:
    """Agrupa por PAN y analiza cada grupo por separado."""
    groups: dict[str, list[EmvCard]] = defaultdict(list)
    for c in cards:
        groups[c.pan_digits or "?"].append(c)
    return {pan: analyze(group) for pan, group in groups.items()}
