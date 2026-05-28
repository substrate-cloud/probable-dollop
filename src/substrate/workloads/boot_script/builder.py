"""Fluent builder API for boot scripts.

>>> script = (
...     BootScript()
...     .with_base_image_setup()
...     .install_uv()
...     .pip_install(["torch", "transformers"])
...     .pull_hf_model("meta-llama/Llama-3-8B", hf_token=Secret.from_env("HF_TOKEN"))
...     .run_systemd_unit("my-app", exec_start="/opt/app/run.sh")
...     .with_status_beacon("https://my-platform/hooks/boot")
...     .with_idle_shutdown(minutes=30)
... )
>>> rendered = script.render()  # bash string
"""

from __future__ import annotations

from collections.abc import Iterable

from substrate.workloads.boot_script.steps import (
    BaseImageSetup,
    CustomCommand,
    GitClone,
    IdleShutdown,
    InstallCudaDrivers,
    InstallUv,
    PipInstall,
    PullHFModel,
    RunSystemdUnit,
    StatusBeacon,
    Step,
    WriteFile,
    collect_secrets,
    render_steps,
)
from substrate.workloads.secret import Secret


class BootScript:
    """Composable bash boot script. Every method returns `self` for chaining."""

    def __init__(self) -> None:
        self._steps: list[Step] = []

    # -- step builders --------------------------------------------------------

    def with_base_image_setup(self) -> BootScript:
        self._steps.append(BaseImageSetup())
        return self

    def install_uv(self) -> BootScript:
        self._steps.append(InstallUv())
        return self

    def install_cuda_drivers(self) -> BootScript:
        self._steps.append(InstallCudaDrivers())
        return self

    def pip_install(self, packages: Iterable[str], *, use_uv: bool = True) -> BootScript:
        self._steps.append(PipInstall(packages=list(packages), use_uv=use_uv))
        return self

    def pull_hf_model(
        self,
        model_id: str,
        *,
        revision: str | None = None,
        hf_token: Secret | None = None,
        cache_dir: str = "/opt/models",
    ) -> BootScript:
        self._steps.append(
            PullHFModel(
                model_id=model_id,
                revision=revision,
                hf_token=hf_token,
                cache_dir=cache_dir,
            )
        )
        return self

    def write_file(self, path: str, content: str, *, mode: str = "0644") -> BootScript:
        self._steps.append(WriteFile(path=path, content=content, mode=mode))
        return self

    def run_systemd_unit(
        self,
        name: str,
        *,
        exec_start: str,
        description: str = "",
        restart: str = "on-failure",
        environment: dict[str, str | Secret] | None = None,
        after: list[str] | None = None,
        user: str = "root",
    ) -> BootScript:
        self._steps.append(
            RunSystemdUnit(
                name=name,
                exec_start=exec_start,
                description=description,
                restart=restart,
                environment=environment or {},
                after=after or ["network-online.target"],
                user=user,
            )
        )
        return self

    def with_status_beacon(
        self,
        callback_url: str = "",
        *,
        initial_stage: str = "boot_finished",
    ) -> BootScript:
        self._steps.append(
            StatusBeacon(callback_url=callback_url, initial_stage=initial_stage)
        )
        return self

    def with_idle_shutdown(
        self,
        *,
        minutes: int = 30,
        deletion_callback: str | None = None,
    ) -> BootScript:
        self._steps.append(
            IdleShutdown(minutes=minutes, deletion_callback=deletion_callback)
        )
        return self

    def custom(self, command: str, *, step_id: str = "custom") -> BootScript:
        self._steps.append(CustomCommand(command=command, step_id=step_id))
        return self

    def git_clone(
        self,
        repo: str,
        dest: str,
        *,
        branch: str | None = None,
        depth: int | None = 1,
    ) -> BootScript:
        """Clone a public git repo at boot. Shallow by default."""
        self._steps.append(GitClone(repo=repo, dest=dest, branch=branch, depth=depth))
        return self

    def add(self, step: Step) -> BootScript:
        """Escape hatch: append a raw Step subclass."""
        self._steps.append(step)
        return self

    # -- inspection / rendering ----------------------------------------------

    @property
    def steps(self) -> list[Step]:
        return list(self._steps)

    def secrets(self) -> list[Secret]:
        return collect_secrets(self._steps)

    def render(self) -> str:
        """Render the full bash script."""
        return render_steps(self._steps)

    def __str__(self) -> str:
        return self.render()

    def __repr__(self) -> str:
        step_names = [s.step_id for s in self._steps]
        return f"BootScript(steps={step_names})"
