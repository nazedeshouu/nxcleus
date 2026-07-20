"""Configuration — pydantic-settings over the exact env surface of spec 01 §6.

Every variable has a default so the control plane boots with zero config: SQLite in ./data/,
model backends in `mock` mode, no keys required. The production `.env` on the VM overrides.
Secrets are read but never logged or serialized (see .safe_summary()).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# app/config.py -> app -> backend -> repo root (local). The container flattens backend/ into /app,
# so parents[2] overshoots to '/'; anchor on the nearest ancestor that actually holds infra/ so
# infra-relative paths (seeds corpora, seats/models yaml) resolve in BOTH layouts. (ponytail)
_here = Path(__file__).resolve()
REPO_ROOT = next((p for p in _here.parents if (p / "infra").is_dir()), _here.parents[2])
BACKEND_ROOT = _here.parents[1]


def _resolve(path_str: str) -> Path:
    """Resolve a configured path: absolute as-is; relative tried against cwd then repo root."""
    p = Path(path_str)
    if p.is_absolute():
        return p
    if p.exists():
        return p.resolve()
    return (REPO_ROOT / p).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- public / deploy
    app_base_url: str = ""
    app_name: str = "Nxcleus"

    # --- provider keys / endpoints (secrets — never logged)
    anthropic_api_key: str = ""
    fireworks_api_key: str = ""
    fireworks_base_url: str = "https://api.fireworks.ai/inference"
    openai_api_key: str = ""                     # OpenAI-direct planner fallback (gpt-5.5); absent => degrades on
    openai_base_url: str = "https://api.openai.com"  # client appends /v1/chat/completions
    openrouter_api_key: str = ""                 # flagship planner (openai/gpt-5.6-sol via OpenRouter); absent => degrades
    openrouter_base_url: str = "https://openrouter.ai/api"  # client appends /v1/chat/completions (NOT /api/v1)
    hf_token: str = ""
    hf_token_file: str = ""                     # .env variant; resolved into hf_token at load
    digitalocean_access_token: str = ""

    # --- persistence
    sqlite_path: str = "./data/platform.db"
    data_dir: str = "./data"                    # packages, workspaces, backups (config addition)

    # --- model routing config files
    seats_config: str = "infra/seats.yaml"
    models_config: str = "infra/models.yaml"    # config addition (02 §7.1); router reads if present
    fleet_config: str = "infra/fleet.yaml"
    rates_config: str = "infra/rates.yaml"      # config addition (10 §3)

    # --- model mode: how backends dispatch
    #   mock -> always MockClient (deterministic, zero-config, dev + CI + tests)
    #   auto -> real client when its key/endpoint present and backend healthy, else mock (badged)
    #   live -> real clients only; missing backend raises
    model_mode: str = "mock"                    # config addition; dev/CI default is mock
    # Explicitly unsafe demo-only generated-code executor. A subprocess separates generated imports
    # from the control-plane interpreter but is NOT a filesystem/network security boundary.
    unsafe_demo_runtime: bool = False
    # Delivery may proceed without Docker execution only for an explicitly opted-in mock demo.
    # This is independent from unsafe_demo_runtime and has no effect in auto/live model modes.
    allow_unverified_demo_delivery: bool = False
    codeexec_image: str = "nxcleus/codeexec:py312"

    # --- boundary / sovereign
    sovereign_default: bool = False
    # fail closed by default (I1); the demo env opts in explicitly (ALLOW_RAW_ON_AMD_HOSTED=1 or
    # the NXCLEUS_-prefixed spelling), which badges every such dispatch in the UI
    allow_raw_on_amd_hosted: bool = Field(
        default=False, validation_alias=AliasChoices(
            "allow_raw_on_amd_hosted", "nxcleus_allow_raw_on_amd_hosted"))

    # --- whisper (policy dictation, O9)
    whisper_model_path: str = ""                # empty => voice input disabled
    whisper_cli: str = "whisper-cli"

    # --- budgets / guards
    fireworks_daily_budget_usd: float = 15.0
    sandbox_run_budget_usd: float = 0.50
    sandbox_max_concurrent: int = 1
    sandbox_max_units: int = 250                # per-run scope guard (09 §4) — LLM-judged units only
    sql_step_row_cap: int = 5000                # sql topology steps: max candidate rows returned
    sql_step_timeout_s: float = 60.0           # cross-row self-joins over 100k+ row corpora (insurer

    # --- prompt trace layer (LOCAL-only debugging; rows never leave the box)
    trace_prompts: bool = True

    # --- auth / ops
    admin_token: str = ""                       # empty => demo/admin writes are open in dev
    # real login (cookie session). Set either password => auth ENABLED (login wall in UI, writes
    # require a session or the legacy X-Demo-Token). Both empty => dev mode, behaves as today.
    auth_admin_password: str = ""               # user 'admin'  (role admin) — full access
    auth_judge_password: str = ""               # user 'judge'  (role judge) — demo writes, no admin ops
    auth_secret: str = ""                        # session cookie signing key; empty => admin_token, else random-at-boot
    auth_signup_code: str = ""                  # invite code for /auth/signup; set => required, empty => open signup
    fernet_key: str = ""                        # BYOK secret encryption; empty => ephemeral dev key
    discord_webhook_url: str = ""

    # --- engine tuning (config additions with spec-backed defaults)
    pool_slots_per_backend: int = 4             # 07 §5.3 default concurrency per vLLM instance
    node_poll_interval_s: float = 2.0           # 07 §5.1 heartbeat cadence
    sse_heartbeat_s: float = 10.0               # 06 §3 rule
    sse_throttle_per_s: int = 10                # 06 §3 delta throttle

    def model_post_init(self, __ctx) -> None:
        if not self.hf_token and self.hf_token_file:
            fp = _resolve(self.hf_token_file)
            if fp.exists():
                object.__setattr__(self, "hf_token", fp.read_text().strip())

    # --- resolved paths
    @property
    def sqlite_file(self) -> Path:
        p = Path(self.sqlite_path)
        if not p.is_absolute():
            p = (REPO_ROOT / p).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        if not p.is_absolute():
            p = (REPO_ROOT / p).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def packages_dir(self) -> Path:
        d = self.data_path / "packages"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def workspaces_dir(self) -> Path:
        d = self.data_path / "workspaces"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def auth_enabled(self) -> bool:
        """True once any login password is configured — flips writes from token-gated to session-gated."""
        return bool(self.auth_admin_password or self.auth_judge_password)

    def config_path(self, which: str) -> Path | None:
        mapping = {
            "seats": self.seats_config,
            "models": self.models_config,
            "fleet": self.fleet_config,
            "rates": self.rates_config,
        }
        p = _resolve(mapping[which])
        return p if p.exists() else None

    def safe_summary(self) -> dict:
        """Feature flags + non-secret state for GET /config/public — never includes key material."""
        return {
            "app_name": self.app_name,
            "model_mode": self.model_mode,
            "unsafe_demo_runtime": self.unsafe_demo_runtime,
            "allow_unverified_demo_delivery": (
                self.allow_unverified_demo_delivery and self.model_mode == "mock"
            ),
            "sovereign_default": self.sovereign_default,
            "allow_raw_on_amd_hosted": self.allow_raw_on_amd_hosted,
            "trace_prompts": self.trace_prompts,
            "voice_input_enabled": bool(self.whisper_model_path),
            "budgets": {
                "fireworks_daily_usd": self.fireworks_daily_budget_usd,
                "sandbox_run_usd": self.sandbox_run_budget_usd,
                "sandbox_max_concurrent": self.sandbox_max_concurrent,
            },
            "keys_present": {
                "anthropic": bool(self.anthropic_api_key),
                "fireworks": bool(self.fireworks_api_key),
                "openai": bool(self.openai_api_key),
                "openrouter": bool(self.openrouter_api_key),
            },
            "admin_required": bool(self.admin_token),
            "auth_enabled": self.auth_enabled,
            "signup_code_required": bool(self.auth_signup_code),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
