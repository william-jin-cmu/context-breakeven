"""Harbor installed-agent wrapper for dsh (DeepSeek Harness) headless profiles.

Two profiles ship in ``dsh-home``:
  * ``tbmin``   — sdk-minimal tool set driven by the one-shot headless runner
                  (append-only history, no compaction; DeepSeek's "minimal mode").
  * ``tbstate`` — tbmin + the dsh-skill-state plugin (SKILL.state replication).

Usage:
  harbor run -p data/tb21/tasks -i <task> \
    --agent-import-path harness.dsh_agent:DshAgent --ak profile=tbstate \
    -m deepseek/deepseek-v4-flash

Token accounting is read back from the dsh session log (``assistant/message``
events carry provider usage including cache reads).
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path, PurePosixPath
from typing import Any, override

from harbor.agents.installed.base import BaseInstalledAgent
from harbor.agents.model_connection import ModelConnectionSpec
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

ROOT = Path(__file__).resolve().parent.parent
LOCAL_DSH_HOME = ROOT / "dsh-home"
LOCAL_PLUGIN = ROOT / "plugin"
LOCAL_LINK_SCRIPT = ROOT / "scripts" / "link-peers.sh"

REMOTE_ROOT = PurePosixPath("/installed-agent/dsh-skill-state")
REMOTE_DSH_HOME = REMOTE_ROOT / "dsh-home"
REMOTE_PLUGIN = REMOTE_ROOT / "plugin"
REMOTE_LINK_SCRIPT = REMOTE_ROOT / "link-peers.sh"
REMOTE_AGENT_LOGS = PurePosixPath("/logs/agent")
REMOTE_RT = REMOTE_ROOT / "rt"
REMOTE_DSH_NM = REMOTE_RT / "usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai"
BUNDLES = {
    "x86_64": (ROOT / "cache" / "dsh-bundle-linux-amd64.tgz", ROOT / "cache" / "uv-0.9.5-x86_64-unknown-linux-gnu.tar.gz"),
    "aarch64": (ROOT / "cache" / "dsh-bundle-linux-arm64.tgz", ROOT / "cache" / "uv-0.9.5-aarch64-unknown-linux-gnu.tar.gz"),
}

# DeepSeek V4 Flash list prices (USD per 1M tokens) for a cost *estimate*.
PRICE_INPUT_MISS = 0.14
PRICE_INPUT_CACHE_HIT = 0.014
PRICE_OUTPUT = 0.28


class DshAgent(BaseInstalledAgent):
    """Run a dsh headless profile inside the task container."""

    MODEL_CONNECTION = ModelConnectionSpec(
        default_provider="deepseek",
        api_key_envs=("DEEPSEEK_API_KEY",),
        base_url_envs=("DEEPSEEK_BASE_URL",),
    )

    def __init__(
        self,
        *args: Any,
        profile: str = "tbmin",
        dsh_version: str = "0.1.2-alpha.5",
        reasoning_effort: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if not (LOCAL_DSH_HOME / "profiles" / profile / "cordis.patch.yml").exists():
            raise ValueError(f"unknown dsh profile {profile!r}; expected a directory under {LOCAL_DSH_HOME / 'profiles'}")
        self._profile = profile
        self._dsh_version = dsh_version
        self._reasoning_effort = reasoning_effort

    @staticmethod
    @override
    def name() -> str:
        return "dsh"

    @override
    def get_version_command(self) -> str | None:
        return f"{self._path_prefix()} dsh --version"

    @override
    def parse_version(self, stdout: str) -> str:
        return stdout.strip().splitlines()[-1].strip()

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        """Upload a prebuilt linux/amd64 node+dsh bundle (built once on the host via
        docker, see cache/) instead of installing from the network inside every
        task container: faster, and immune to registry/TLS flakiness."""
        arch = (await environment.exec(command="uname -m")).stdout.strip()
        arch = {"amd64": "x86_64", "arm64": "aarch64"}.get(arch, arch)
        if arch not in BUNDLES:
            raise RuntimeError(f"no dsh bundle for container arch {arch}")
        bundle, uv_tarball = BUNDLES[arch]
        self._bundle = bundle
        self._uv_tarball = uv_tarball
        if not bundle.exists():
            raise FileNotFoundError(f"missing {bundle}; build it with scripts/build-bundle.sh")
        try:
            await self.ensure_system_dependencies(environment, ("ca_certificates",))
        except Exception as exc:  # apt mirrors flake (expired Release files etc.); most images already ship certs
            self.logger.warning("ca-certificates install failed, continuing: %s", str(exc)[:200])
        await self.exec_as_root(
            environment,
            command=f"mkdir -p {REMOTE_ROOT} {REMOTE_RT} && chmod -R 777 {REMOTE_ROOT}",
        )
        await environment.upload_file(bundle, (REMOTE_ROOT / "dsh-bundle.tgz").as_posix())
        await self._preinstall_uv(environment)
        await environment.upload_dir(LOCAL_DSH_HOME / "profiles", (REMOTE_DSH_HOME / "profiles").as_posix())
        await environment.upload_file(LOCAL_DSH_HOME / "cordis.patch.yml", (REMOTE_DSH_HOME / "cordis.patch.yml").as_posix())
        await environment.upload_dir(LOCAL_PLUGIN / "lib", (REMOTE_PLUGIN / "lib").as_posix())
        await environment.upload_file(LOCAL_PLUGIN / "package.json", (REMOTE_PLUGIN / "package.json").as_posix())
        await environment.upload_file(LOCAL_LINK_SCRIPT, REMOTE_LINK_SCRIPT.as_posix())
        local_plugin_entry = (LOCAL_PLUGIN / "lib" / "index.js").as_posix()
        remote_plugin_entry = (REMOTE_PLUGIN / "lib" / "index.js").as_posix()
        await self.exec_as_agent(
            environment,
            command=(
                "set -euo pipefail; "
                f"tar xzf {REMOTE_ROOT / 'dsh-bundle.tgz'} -C {REMOTE_RT}; "
                f"{self._path_prefix()} dsh --version; "
                f"rm -rf {REMOTE_DSH_HOME}/sessions; "
                f"sed -i 's#{local_plugin_entry}#{remote_plugin_entry}#' {REMOTE_DSH_HOME}/profiles/*/cordis.patch.yml; "
                f"bash {REMOTE_LINK_SCRIPT} {REMOTE_PLUGIN} {REMOTE_DSH_NM} >/dev/null; "
                f"cd /tmp && {self._path_prefix()} DSH_HOME={REMOTE_DSH_HOME} DSH_TELEMETRY_DISABLED=1 dsh --profile {self._profile} --dump-config >/dev/null"
            ),
            timeout_sec=600,
        )

    async def _preinstall_uv(self, environment: BaseEnvironment) -> None:
        """Terminal-Bench verifiers install uv from GitHub at test time; that download
        is flaky on this network. Pre-install the same uv version for root so the
        verifier's `source $HOME/.local/bin/env` and `uvx` work even when its own
        download fails, and pre-fetch CPython 3.13 (with retries) for the same reason.
        Applied identically to every arm."""
        uv_tarball = self._uv_tarball
        if not uv_tarball.exists():
            self.logger.warning("uv tarball missing at %s; skipping uv pre-install", uv_tarball)
            return
        await environment.upload_file(uv_tarball, (REMOTE_ROOT / "uv.tar.gz").as_posix())
        await self.exec_as_root(
            environment,
            command=(
                "set -e; mkdir -p /root/.local/bin; "
                f"tar xzf {REMOTE_ROOT / 'uv.tar.gz'} -C /root/.local/bin --strip-components=1; "
                "chmod +x /root/.local/bin/uv /root/.local/bin/uvx; "
                "printf '%s\\n' '#!/bin/sh' 'case \":${PATH}:\" in *:\"/root/.local/bin\":*) ;; *) export PATH=\"/root/.local/bin:$PATH\" ;; esac' > /root/.local/bin/env; "
                "/root/.local/bin/uv --version; "
                "if ! command -v python3.13 >/dev/null 2>&1; then "
                "for i in 1 2 3 4 5; do /root/.local/bin/uv python install 3.13 && break; echo \"uv python install retry $i\"; sleep 3; done; fi; true"
            ),
            timeout_sec=900,
        )

    @staticmethod
    def _path_prefix() -> str:
        return f'PATH="{REMOTE_RT}/usr/local/bin:$PATH"'

    @override
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        access = self.model_connection
        env: dict[str, str] = dict(access.env)
        api_key = access.api_key or self._get_env("DEEPSEEK_API_KEY")
        gemini_key = self._get_env("GEMINI_API_KEY")
        if not api_key and not gemini_key:
            raise ValueError("DEEPSEEK_API_KEY or GEMINI_API_KEY is required")
        if api_key:
            env["DEEPSEEK_API_KEY"] = api_key
        if gemini_key:
            env["GEMINI_API_KEY"] = gemini_key
        env["DSH_HOME"] = REMOTE_DSH_HOME.as_posix()
        env["DSH_TELEMETRY_DISABLED"] = "1"
        if self._reasoning_effort:
            env["DSH_REASONING_EFFORT"] = self._reasoning_effort
        quoted = shlex.quote(instruction)
        # Exit 0 regardless of the agent outcome so the verifier still runs; the
        # real exit code is recorded next to the logs.
        command = (
            f"export {self._path_prefix()}; "
            f"mkdir -p {REMOTE_AGENT_LOGS}/sessions; "
            # Persist the session log straight into the harbor logs dir so a
            # partial trajectory survives an agent timeout (the copy below
            # never runs when harbor kills the command).
            f"rm -rf {REMOTE_DSH_HOME}/sessions && ln -s {REMOTE_AGENT_LOGS}/sessions {REMOTE_DSH_HOME}/sessions; "
            f"dsh --profile {self._profile} {quoted} "
            f"> {REMOTE_AGENT_LOGS}/dsh.out 2> {REMOTE_AGENT_LOGS}/dsh.err; rc=$?; "
            f"echo $rc > {REMOTE_AGENT_LOGS}/dsh.rc; "
            "exit 0"
        )
        await self.exec_as_agent(environment, command=command, env=env)

    @override
    def populate_context_post_run(self, context: AgentContext) -> None:
        sessions_dir = self.logs_dir / "sessions"
        logs = sorted(sessions_dir.rglob("session.jsonl")) if sessions_dir.exists() else []
        if not logs:
            context.metadata = {"profile": self._profile, "session_log": None}
            return
        log_path = max(logs, key=lambda p: p.stat().st_size)
        uncached = cache_read = output = reasoning = 0
        steps = 0
        tool_calls: dict[str, int] = {}
        replacements = 0
        max_prompt = 0
        for line in log_path.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = event.get("type")
            data = event.get("data") or {}
            if kind == "assistant/message":
                usage = data.get("usage") or {}
                steps += 1
                cr = int(usage.get("cacheReadTokens") or 0)
                inp = int(usage.get("inputTokens") or 0)
                # dsh's DeepSeek adapter reports inputTokens as the cache-MISS part;
                # the full prompt is inputTokens + cacheReadTokens (verified on
                # session logs: totalTokens == input + output + cacheRead).
                uncached += inp
                cache_read += cr
                output += int(usage.get("outputTokens") or 0)
                reasoning += int(usage.get("reasoningTokens") or 0)
                max_prompt = max(max_prompt, inp + cr)
            elif kind == "tool/call":
                name = str(data.get("name"))
                tool_calls[name] = tool_calls.get(name, 0) + 1
            elif kind == "compaction/prune":
                replacements += 1
        rc_file = self.logs_dir / "dsh.rc"
        rc = rc_file.read_text().strip() if rc_file.exists() else None
        context.n_input_tokens = uncached + cache_read
        context.n_cache_tokens = cache_read
        context.n_output_tokens = output
        context.cost_usd = (
            uncached / 1e6 * PRICE_INPUT_MISS
            + cache_read / 1e6 * PRICE_INPUT_CACHE_HIT
            + output / 1e6 * PRICE_OUTPUT
        )
        context.metadata = {
            "profile": self._profile,
            "session_log": str(log_path.relative_to(self.logs_dir)),
            "dsh_exit_code": rc,
            "steps": steps,
            "uncached_input_tokens": uncached,
            "cache_read_tokens": cache_read,
            "output_tokens": output,
            "reasoning_tokens": reasoning,
            "max_prompt_tokens": max_prompt,
            "cache_hit_ratio": (cache_read / (uncached + cache_read)) if (uncached + cache_read) else None,
            "tool_calls": tool_calls,
            "state_replacements": replacements,
            "cost_is_estimate": True,
        }
