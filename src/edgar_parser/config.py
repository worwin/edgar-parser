from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


CONFIG_FILENAME = "edgar-parser.toml"


def _require_non_empty(name: str, value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{name} must not be empty")
    return stripped


def _require_email(name: str, value: str) -> str:
    stripped = _require_non_empty(name, value)
    if "@" not in stripped or stripped.startswith("@") or stripped.endswith("@"):
        raise ValueError(f"{name} must look like an email address")
    return stripped


@dataclass(frozen=True, slots=True)
class IdentityConfig:
    company_name: str
    email: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_name", _require_non_empty("company_name", self.company_name))
        object.__setattr__(self, "email", _require_email("email", self.email))

    @property
    def user_agent(self) -> str:
        return f"{self.company_name} {self.email}"


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    workspace_root: Path
    identity: IdentityConfig | None = None
    request_rate_limit_per_second: float = 5.0

    @classmethod
    def load(cls, workspace_root: Path) -> "ProjectConfig":
        config_path = workspace_root / CONFIG_FILENAME
        if not config_path.exists():
            return cls(workspace_root=workspace_root.resolve())

        with config_path.open("rb") as handle:
            raw = tomllib.load(handle)

        identity_block = raw.get("identity")
        identity = None
        if isinstance(identity_block, dict):
            company_name = identity_block.get("company_name")
            email = identity_block.get("email")
            if company_name and email:
                identity = IdentityConfig(company_name=company_name, email=email)

        request_rate = raw.get("sec", {}).get("request_rate_limit_per_second", 5.0)
        return cls(
            workspace_root=workspace_root.resolve(),
            identity=identity,
            request_rate_limit_per_second=float(request_rate),
        )

    def to_toml(self) -> str:
        lines = [
            "[project]",
            f'workspace_root = "{self.workspace_root.as_posix()}"',
            "",
        ]

        if self.identity is not None:
            lines.extend(
                [
                    "[identity]",
                    f'company_name = "{self.identity.company_name}"',
                    f'email = "{self.identity.email}"',
                    "",
                ]
            )

        lines.extend(
            [
                "[sec]",
                f"request_rate_limit_per_second = {self.request_rate_limit_per_second}",
                "",
            ]
        )
        return "\n".join(lines)
