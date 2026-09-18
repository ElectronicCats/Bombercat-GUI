"""Modelo del framework de PoCs: severidad, estado, hallazgos, resultado y el
contexto de ejecución que reciben los PoCs.

Un PoC es una función `run(ctx) -> PocResult`. El `PocContext` le da acceso al
proyecto activo, sus variables (objetivo, credenciales, perfil terminal), una
tarjeta capturada (`EmvCard`), un cliente HTTP con evidencia y helpers para
registrar hallazgos y guardar evidencias. Los PoCs específicos del cliente viven
como plugins del proyecto (`<proyecto>/pocs/*.py`); el core solo aporta el motor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    def __str__(self) -> str:
        return self.value


class Status(str, Enum):
    PASSED = "passed"  # el control resiste (no vulnerable)
    VULNERABLE = "vulnerable"  # PoC confirmó la vulnerabilidad
    NOT_VULNERABLE = "not_vulnerable"
    FAILED = "failed"  # el PoC no pudo completarse por el objetivo
    ERROR = "error"  # error interno del PoC
    SKIPPED = "skipped"
    INFO = "info"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Finding:
    title: str
    severity: Severity = Severity.INFO
    detail: str = ""
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "severity": str(self.severity),
            "detail": self.detail,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class PocMeta:
    id: str
    title: str = ""
    category: str = "general"  # emv | switch | api | nfc | magstripe | ...
    severity: Severity = Severity.INFO
    description: str = ""
    authorization: str = ""  # nota de autorización del engagement
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "severity": str(self.severity),
            "description": self.description,
            "authorization": self.authorization,
            "tags": list(self.tags),
        }


@dataclass
class PocResult:
    poc_id: str
    status: Status = Status.INFO
    summary: str = ""
    findings: list[Finding] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    started: str = ""
    finished: str = ""
    error: str = ""

    @property
    def max_severity(self) -> Severity:
        order = list(Severity)
        sev = [f.severity for f in self.findings]
        return max(sev, key=order.index) if sev else Severity.INFO

    def to_dict(self) -> dict:
        return {
            "poc_id": self.poc_id,
            "status": str(self.status),
            "summary": self.summary,
            "max_severity": str(self.max_severity),
            "findings": [f.to_dict() for f in self.findings],
            "evidence": self.evidence,
            "started": self.started,
            "finished": self.finished,
            "error": self.error,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


@dataclass
class Poc:
    meta: PocMeta
    run: Callable[["PocContext"], PocResult]


@dataclass
class PocContext:
    """Todo lo que un PoC necesita. Los efectos (red, disco) pasan por aquí para
    poder registrarlos como evidencia y respetar dry-run / solo-lectura."""

    project: object | None = None
    variables: Mapping[str, str] = field(default_factory=dict)
    card: object | None = None  # EmvCard | None
    evidence_dir: Path = field(default_factory=lambda: Path("."))
    dry_run: bool = False
    allow_write: bool = False
    http_factory: Callable[["PocContext"], object] | None = None
    logger: Callable[[str], None] | None = None
    evidence: list[str] = field(default_factory=list)

    # -- helpers de PoC -----------------------------------------------------
    def var(self, name: str, default: str | None = None) -> str | None:
        return self.variables.get(name, default)

    def require(self, name: str) -> str:
        val = self.variables.get(name)
        if not val:
            raise PocError(
                f"Falta la variable requerida {name!r} en el proyecto "
                f"(añádela con: cardsec var set {name} <valor>)."
            )
        return val

    def log(self, msg: str) -> None:
        if self.logger:
            self.logger(msg)

    def http(self):
        if self.http_factory is None:
            raise PocError("No hay cliente HTTP configurado en el contexto.")
        return self.http_factory(self)

    def save_evidence(self, name: str, data: bytes | str) -> Path:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        path = self.evidence_dir / name
        mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
        with open(path, mode) as f:
            f.write(data)
        self.evidence.append(str(path))
        return path

    # -- constructores de resultado ----------------------------------------
    def finding(
        self,
        title: str,
        severity: Severity = Severity.INFO,
        detail: str = "",
        evidence=(),
    ) -> Finding:
        return Finding(title, severity, detail, tuple(evidence))

    def result(
        self, status: Status, summary: str = "", findings: list[Finding] | None = None
    ) -> PocResult:
        return PocResult(
            poc_id="",
            status=status,
            summary=summary,
            findings=list(findings or []),
            evidence=list(self.evidence),
        )


class PocError(RuntimeError):
    """Error controlado dentro de un PoC (falta config, precondición, etc.)."""
