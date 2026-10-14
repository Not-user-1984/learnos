"""DTO профиля: машины и предпочтения обучения."""

from pydantic import BaseModel, Field


class Machine(BaseModel):
    """Машина пользователя: где агент предлагает практику."""

    id: str = Field(max_length=40)
    name: str
    kind: str = "other"  # macos | linux | proxmox | windows | other
    specs: str = ""
    tools: list[str] = Field(default_factory=list)
    notes: str = ""


class LearningPrefs(BaseModel):
    """Предпочтения обучения: параметры сессии по умолчанию."""

    session_minutes: int = 30
    theory_concepts: int = 5
    questions_per_concept: int = 1
    practice_default: bool = True
    explain_style: str = "аналогии + пример из DevOps"


class Profile(BaseModel):
    """Профиль пользователя целиком (settings.profile)."""

    name: str = "Дмитрий"
    about: str = "DevOps, люблю объяснения через аналогии"
    machines: list[Machine] = Field(default_factory=list)
    learning: LearningPrefs = Field(default_factory=LearningPrefs)


DEFAULT_PROFILE = Profile(
    machines=[
        Machine(
            id="mac",
            name="MacBook",
            kind="macos",
            specs="M-series, 32 GB",
            tools=["brew", "docker", "uv", "node"],
        ),
        Machine(
            id="homelab",
            name="Хомлаб",
            kind="proxmox",
            specs="Proxmox 192.168.0.105, LXC со статическими IP",
            tools=["pct", "docker"],
            notes="спит 19:00–08:30",
        ),
    ]
)
