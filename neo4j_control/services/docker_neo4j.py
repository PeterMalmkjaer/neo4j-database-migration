"""Docker Compose lifecycle for isolated Neo4j stacks (one stack per DB)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from neo4j_control.audit import audit
from neo4j_control.config import Settings, ensure_runtime_dirs
from neo4j_control.logging_setup import get_logger
from neo4j_control.models import Neo4jInstance
from neo4j_control.services.bolt import bolt_ready, tcp_open
from neo4j_control.services.registry import InstanceRegistry, RegistryError, validate_name

log = get_logger("neo4j_control.docker")

TEMPLATE_NAME = "docker-compose.yml"


class DockerUnavailableError(RuntimeError):
    pass


class LifecycleError(RuntimeError):
    pass


def docker_available() -> tuple[bool, str]:
    """Return (ok, detail) whether docker compose can run."""
    docker = shutil.which("docker")
    if not docker:
        return False, "docker binary not found on PATH"
    try:
        proc = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"docker compose check failed: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "unknown error").strip()
        return False, detail
    return True, (proc.stdout or "").strip() or "docker compose ok"


def _template_path(settings: Settings) -> Path:
    return Path(__file__).resolve().parent.parent / "templates" / TEMPLATE_NAME


def _stack_dir(settings: Settings, name: str) -> Path:
    return settings.stacks_dir / name


def _read_stack_password(stack_dir: Path) -> str | None:
    env_path = stack_dir / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("NEO4J_AUTH="):
            value = line.split("=", 1)[1].strip()
            # format neo4j/password
            if "/" in value:
                return value.split("/", 1)[1]
            return value
    return None


def _run_compose(
    stack_dir: Path,
    *args: str,
    timeout: float = 180.0,
) -> subprocess.CompletedProcess[str]:
    cmd = ["docker", "compose", "-f", str(stack_dir / "docker-compose.yml"), *args]
    log.info("compose %s cwd=%s", " ".join(args), stack_dir)
    try:
        return subprocess.run(
            cmd,
            cwd=str(stack_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ},
        )
    except FileNotFoundError as exc:
        raise DockerUnavailableError("docker not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise LifecycleError(f"docker compose timed out: {' '.join(args)}") from exc


class Neo4jDockerService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = ensure_runtime_dirs(settings)
        self.registry = InstanceRegistry(self.settings)

    def list_instances(self) -> list[Neo4jInstance]:
        instances = self.registry.list()
        # Refresh status when Docker is available
        ok, _ = docker_available()
        if not ok:
            return instances
        refreshed: list[Neo4jInstance] = []
        for inst in instances:
            refreshed.append(self.refresh_status(inst))
        return refreshed

    def refresh_status(self, inst: Neo4jInstance) -> Neo4jInstance:
        stack = Path(inst.compose_dir)
        if not stack.exists():
            inst.status = "error"
            inst.last_error = "compose directory missing"
            self.registry.update(inst)
            return inst
        try:
            proc = _run_compose(stack, "ps", "--status", "running", "--services", timeout=30)
        except (DockerUnavailableError, LifecycleError) as exc:
            inst.status = "unknown"
            inst.last_error = str(exc)
            self.registry.update(inst)
            return inst
        running = "neo4j" in (proc.stdout or "")
        if running:
            if tcp_open("127.0.0.1", inst.bolt_port):
                inst.status = "running"
            else:
                inst.status = "starting"
            inst.last_error = None
        else:
            inst.status = "stopped"
            inst.last_error = None
        self.registry.update(inst)
        return inst

    def create(
        self,
        name: str,
        *,
        password: str | None = None,
        start: bool = False,
    ) -> Neo4jInstance:
        name = validate_name(name)
        password = password or self.settings.default_password
        if len(password) < 8:
            raise LifecycleError("Password must be at least 8 characters (Neo4j requirement).")

        ok, detail = docker_available()
        # Allow create of definitions even without Docker (compose files on disk)
        bolt, http = self.registry.allocate_ports()
        stack = _stack_dir(self.settings, name)
        if stack.exists():
            raise LifecycleError(f"Stack directory already exists: {stack}")

        stack.mkdir(parents=True, exist_ok=False)
        template = _template_path(self.settings).read_text(encoding="utf-8")
        (stack / "docker-compose.yml").write_text(template, encoding="utf-8")
        env_body = (
            f"COMPOSE_PROJECT_NAME=neo4j-{name}\n"
            f"NEO4J_IMAGE={self.settings.neo4j_image}\n"
            f"NEO4J_BOLT_PORT={bolt}\n"
            f"NEO4J_HTTP_PORT={http}\n"
            f"NEO4J_AUTH=neo4j/{password}\n"
        )
        (stack / ".env").write_text(env_body, encoding="utf-8")
        (stack / ".gitignore").write_text(".env\n", encoding="utf-8")

        inst = Neo4jInstance(
            name=name,
            bolt_port=bolt,
            http_port=http,
            compose_dir=str(stack),
            image=self.settings.neo4j_image,
            status="defined",
        )
        self.registry.add(inst)
        audit(
            "instance.create",
            instance=name,
            detail={"bolt_port": bolt, "http_port": http, "image": inst.image, "docker": ok},
        )
        log.info("Created instance %s bolt=%s (docker=%s: %s)", name, bolt, ok, detail)

        if start:
            if not ok:
                inst.last_error = f"Created definition but cannot start: {detail}"
                inst.status = "defined"
                self.registry.update(inst)
                audit("instance.start", instance=name, result="skipped", detail={"reason": detail})
                return inst
            return self.start(name)
        return inst

    def start(self, name: str, *, wait_bolt: bool = True) -> Neo4jInstance:
        inst = self.registry.get(name)
        if not inst:
            raise RegistryError(f"Unknown instance: {name}")
        ok, detail = docker_available()
        if not ok:
            raise DockerUnavailableError(detail)

        stack = Path(inst.compose_dir)
        inst.status = "starting"
        inst.last_error = None
        self.registry.update(inst)

        proc = _run_compose(stack, "up", "-d", timeout=180)
        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout or "compose up failed").strip()
            inst.status = "error"
            inst.last_error = msg
            self.registry.update(inst)
            audit("instance.start", instance=name, result="error", detail={"stderr": msg[:2000]})
            raise LifecycleError(msg)

        if wait_bolt:
            password = _read_stack_password(stack) or self.settings.default_password
            ready, ready_msg = bolt_ready(inst.bolt_uri, password, timeout_s=90)
            if not ready:
                inst.status = "starting"
                inst.last_error = ready_msg
                self.registry.update(inst)
                audit(
                    "instance.start",
                    instance=name,
                    result="partial",
                    detail={"message": ready_msg},
                )
                log.warning("Started containers but Bolt not ready: %s", ready_msg)
                return inst

        inst.status = "running"
        inst.last_error = None
        self.registry.update(inst)
        audit("instance.start", instance=name, result="ok")
        log.info("Started instance %s", name)
        return inst

    def stop(self, name: str) -> Neo4jInstance:
        inst = self.registry.get(name)
        if not inst:
            raise RegistryError(f"Unknown instance: {name}")
        ok, detail = docker_available()
        if not ok:
            raise DockerUnavailableError(detail)

        stack = Path(inst.compose_dir)
        proc = _run_compose(stack, "stop", timeout=120)
        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout or "compose stop failed").strip()
            inst.status = "error"
            inst.last_error = msg
            self.registry.update(inst)
            audit("instance.stop", instance=name, result="error", detail={"stderr": msg[:2000]})
            raise LifecycleError(msg)

        inst.status = "stopped"
        inst.last_error = None
        self.registry.update(inst)
        audit("instance.stop", instance=name, result="ok")
        log.info("Stopped instance %s", name)
        return inst

    def delete(self, name: str, *, confirm_name: str, remove_volumes: bool = True) -> None:
        """Destructive: tear down compose stack and remove registry entry.

        Requires confirm_name to exactly match the instance name.
        """
        if confirm_name.strip() != name:
            raise LifecycleError("Typed confirmation does not match instance name.")

        inst = self.registry.get(name)
        if not inst:
            raise RegistryError(f"Unknown instance: {name}")

        stack = Path(inst.compose_dir)
        ok, detail = docker_available()
        if stack.exists() and ok:
            args = ["down"]
            if remove_volumes:
                args.append("-v")
            proc = _run_compose(stack, *args, timeout=180)
            if proc.returncode != 0:
                msg = (proc.stderr or proc.stdout or "compose down failed").strip()
                audit("instance.delete", instance=name, result="error", detail={"stderr": msg[:2000]})
                raise LifecycleError(msg)
        elif stack.exists() and not ok:
            log.warning("Docker unavailable (%s); removing stack files only for %s", detail, name)

        if stack.exists():
            shutil.rmtree(stack)

        self.registry.remove(name)
        audit(
            "instance.delete",
            instance=name,
            result="ok",
            detail={"remove_volumes": remove_volumes, "docker": ok},
        )
        log.info("Deleted instance %s", name)
