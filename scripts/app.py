#!/usr/bin/env python3
"""Shared cross-platform local lifecycle; application dependencies run in Docker."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "app-workflow.json").read_text(encoding="utf-8"))
STATE = ROOT / ".runtime"


def run(*args, env=None, capture=False, check=True):
    result = subprocess.run([str(a) for a in args], cwd=ROOT, env=env,
                            text=True, stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None)
    if check and result.returncode:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(map(str, args[:4]))}\n{detail}")
    return result.stdout.strip() if capture else result.returncode


def revision():
    return run("git", "rev-parse", "HEAD", capture=True)


def environment(args, image=None, project=None, revision_value=None):
    env = os.environ.copy()
    env.update(APP_PORT=str(args.port or CONFIG["local_port"]),
               PUBLIC_ORIGIN="http://127.0.0.1:" + str(args.port or CONFIG["local_port"]),
               APP_REVISION=revision_value or revision(),
               APP_SOURCE_URL="https://github.com/" + CONFIG["repository"])
    if image:
        env["APP_IMAGE"] = image
    return env


def installation_id():
    STATE.mkdir(exist_ok=True)
    path = STATE / "installation-id"
    if not path.exists():
        try:
            with path.open("x", encoding="utf-8") as stream:
                stream.write(uuid.uuid4().hex[:8] + "\n")
        except FileExistsError:
            pass
    value = path.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9a-f]{8}", value):
        raise RuntimeError("Invalid .runtime/installation-id; preserve this identifier with the installation's data.")
    return value


def compose(mode, *args, env=None, project=None, capture=False, check=True):
    return run("docker", "compose", "--project-name", project or CONFIG["name"] + "-" + installation_id() + "-" + mode,
               "--file", "compose." + mode + ".yaml", *args, env=env,
               capture=capture, check=check)


@contextlib.contextmanager
def lock():
    STATE.mkdir(exist_ok=True)
    folder = STATE / "launcher.lock"
    try:
        folder.mkdir()
    except FileExistsError:
        raise RuntimeError("Another launcher owns .runtime/launcher.lock. If it crashed, verify no launcher is running before removing that empty lock directory.")
    try:
        yield
    finally:
        folder.rmdir()


def doctor():
    if sys.version_info < (3, 10):
        raise RuntimeError("Python 3.10 or newer is required.")
    for tool in ("git", "docker"):
        if not shutil.which(tool):
            raise RuntimeError(tool + " is required on this machine.")
    run("docker", "compose", "version")
    kind = run("docker", "info", "--format", "{{.OSType}}", capture=True)
    if kind != "linux":
        raise RuntimeError("Docker must be running Linux containers.")
    print("Python, Git, Docker daemon and Compose are available. Application credentials and resource requirements are app-specific.")


def verify_http(mode, env, expected, project=None):
    address = compose(mode, "port", CONFIG["service"], str(CONFIG["container_port"]),
                      env=env, project=project, capture=True)
    base = "http://" + address.splitlines()[0]
    with urllib.request.urlopen(base + CONFIG["health_path"], timeout=10) as response:
        if response.status != 200:
            raise RuntimeError("Health endpoint did not return 200.")
    with urllib.request.urlopen(base + CONFIG["version_path"], timeout=10) as response:
        receipt = json.load(response)
    if receipt.get("revision") != expected:
        raise RuntimeError("Served revision does not match expected image/source revision.")
    return base


def image_revision(image):
    info = json.loads(run("docker", "image", "inspect", image, capture=True))[0]
    labels = info.get("Config", {}).get("Labels") or {}
    result = labels.get("org.opencontainers.image.revision", "")
    if not re.fullmatch(r"[0-9a-f]{40}", result):
        raise RuntimeError("Image must carry its full Git revision label.")
    if labels.get("org.opencontainers.image.source") != "https://github.com/" + CONFIG["repository"]:
        raise RuntimeError("Image source label does not match this configured repository.")
    if not info.get("Config", {}).get("Healthcheck", {}).get("Test"):
        raise RuntimeError("Runtime image needs a Docker health check.")
    return result


class E2EFailure(RuntimeError):
    def __init__(self, returncode):
        self.returncode = returncode
        super().__init__(f"E2E target failed with exit code {returncode}.")


def has_e2e_stage():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    # Join Dockerfile continuation lines, including files using the Windows escape directive.
    escape = re.search(r"^\s*#\s*escape\s*=\s*([`\\])\s*$", dockerfile, re.M | re.I)
    continuation = escape.group(1) if escape else "\\"
    dockerfile = re.sub(r"^[ \t]*#.*$", "", dockerfile, flags=re.M)
    dockerfile = re.sub(re.escape(continuation) + r"\r?\n\s*", " ", dockerfile)
    return bool(re.search(r"^\s*FROM\s+(?:--\S+\s+)*\S+\s+AS\s+e2e\s*$", dockerfile, re.M | re.I))


def run_e2e(env, project, expected):
    """Run an opt-in e2e image against this check's healthy synthetic candidate."""
    unique = CONFIG["name"] + "-e2e-" + uuid.uuid4().hex[:10]
    image, network, container = unique + ":test", unique + "-net", unique + "-run"
    connected, created = False, False
    candidate_id = None
    try:
        run("docker", "build", "--target", "e2e", "--build-arg", "APP_REVISION=" + expected,
            "--build-arg", "APP_SOURCE_URL=https://github.com/" + CONFIG["repository"], "--tag", image, ".")
        candidate_id = compose("installed", "ps", "--quiet", CONFIG["service"], env=env, project=project, capture=True)
        if not candidate_id or len(candidate_id.splitlines()) != 1:
            raise RuntimeError("E2E needs exactly one candidate service container.")
        inspected = json.loads(run("docker", "inspect", candidate_id, capture=True))[0]
        if inspected["Config"]["Labels"].get("com.docker.compose.project") != project or "-check-" not in project:
            raise RuntimeError("Refusing a volume that does not belong to this isolated check.")
        mounts = [m for m in inspected["Mounts"] if m["Destination"] == "/data"]
        if len(mounts) != 1 or mounts[0]["Type"] != "volume":
            raise RuntimeError("The check fixture requires its exact synthetic named data volume.")
        volume = mounts[0]["Name"]
        info = json.loads(run("docker", "volume", "inspect", volume, capture=True))[0]
        if (info.get("Labels") or {}).get("com.docker.compose.project") != project:
            raise RuntimeError("Synthetic volume ownership could not be verified.")
        host = inspected["HostConfig"]
        if inspected["Config"]["User"] != "10001:10001" or host["Memory"] != 268435456 or host["PidsLimit"] != 100 or not host["ReadonlyRootfs"]:
            raise RuntimeError("Candidate runtime limits or non-root identity changed.")
        run("docker", "network", "create", "--internal", network)
        created = True
        run("docker", "network", "connect", "--alias", "candidate", network, candidate_id)
        connected = True
        base = "http://candidate:" + str(CONFIG["container_port"])
        result = run("docker", "run", "--rm", "--name", container, "--network", network,
                     "--mount", "type=volume,source=" + volume + ",target=/data",
                     "--env", "XS_E2E_ISOLATED=" + project,
                     "--env", "BASE_URL=" + base, "--env", "APP_REVISION=" + expected, image, check=False)
        if result:
            raise E2EFailure(result)
    finally:
        # Unique names are created only here. Never prune or touch installed app resources.
        if run("docker", "container", "inspect", container, capture=True, check=False):
            run("docker", "rm", "--force", "--volumes", container, check=False)
        if connected:
            run("docker", "network", "disconnect", network, candidate_id, check=False)
        if created:
            run("docker", "network", "rm", network, check=False)
        if image_cached(image):
            run("docker", "image", "rm", image, check=False)


def candidate(args, image, expected, e2e=False):
    project = CONFIG["name"] + "-check-" + uuid.uuid4().hex[:10]
    env = environment(args, image=image, revision_value=expected)
    env["APP_PORT"] = "0"
    env["PUBLIC_ORIGIN"] = "http://candidate:" + str(CONFIG["container_port"])
    if e2e:
        # Reserved fictional phone; only generate a manual sms: link for the isolated fixture.
        env["DEMO_ALLOWED_PHONES"] = "+12025550123"
    keep = False
    try:
        compose("installed", "up", "--detach", "--no-build", "--wait", "--wait-timeout", "90", env=env, project=project)
        verify_http("installed", env, expected, project)
        if e2e:
            run_e2e(env, project, expected)
        if getattr(args, "keep_candidate", False):
            address = compose("installed", "port", CONFIG["service"], str(CONFIG["container_port"]), env=env, project=project, capture=True).splitlines()[0]
            env["APP_PORT"] = address.rsplit(":", 1)[1]
            env["PUBLIC_ORIGIN"] = "http://127.0.0.1:" + env["APP_PORT"]
            compose("installed", "up", "--detach", "--no-build", "--wait", env=env, project=project)
            ident = compose("installed", "ps", "--quiet", CONFIG["service"], env=env, project=project, capture=True)
            export = STATE / (project + "-sessions.json")
            run("docker", "cp", ident + ":/data/e2e-sessions.json", export)
            sessions = json.loads(export.read_text(encoding="utf-8"))
            for value in sessions.values():
                value["cookie"]["url"] = env["PUBLIC_ORIGIN"]
            export.write_text(json.dumps(sessions), encoding="utf-8")
            receipt = dict(project=project, image=image, origin=env["PUBLIC_ORIGIN"], port=env["APP_PORT"], revision=expected, sessions=str(export))
            (STATE / "candidate.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            keep = True
            print("Isolated synthetic browser candidate: " + env["PUBLIC_ORIGIN"] + "; private session export: " + str(export))
            print("Retained for the requested integration walkthrough; recheck and remove after it with: python scripts/app.py clean-candidate")
    finally:
        # The project was generated here, never an existing installation. Only its synthetic volume is removed.
        if not keep:
            compose("installed", "down", "--volumes", env=env, project=project)


def backup(mode, env):
    running = compose(mode, "ps", "--status", "running", "--quiet", CONFIG["service"], env=env, capture=True)
    if not running or not CONFIG.get("stateful"):
        return
    if CONFIG.get("backup_mode") == "quiesced-data":
        # A stopped service has no SQLite/upload writers. Keep a complete recovery
        # copy outside the Docker volume, including keys and encrypted tokens.
        destination = ROOT / ".runtime" / "backups" / (mode + "-" + uuid.uuid4().hex)
        destination.mkdir(parents=True, exist_ok=False)
        compose(mode, "stop", CONFIG["service"], env=env)
        try:
            run("docker", "cp", running.strip() + ":/data", str(destination))
        finally:
            compose(mode, "start", CONFIG["service"], env=env)
        print("Complete quiesced data snapshot: " + str(destination))
        return
    command = CONFIG.get("backup_command")
    if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
        raise RuntimeError("This stateful app needs a verified backup_command argument list before replacing its running container.")
    compose(mode, "exec", "--no-TTY", CONFIG["service"], *command, env=env)


def source_update(args):
    branch = run("git", "branch", "--show-current", capture=True)
    branches = CONFIG.get("branches", ["dev", "main"])
    if branch not in branches:
        raise RuntimeError("Update requires one of the long-lived branches (" + ", ".join(branches) + "); detached and feature checkouts are left untouched.")
    if run("git", "status", "--porcelain", "--untracked-files=all", capture=True):
        raise RuntimeError("Commit or stash source changes, including untracked files, before updating.")
    run("git", "fetch", "origin", f"refs/heads/{branch}:refs/remotes/origin/{branch}")
    counts = run("git", "rev-list", "--left-right", "--count", f"HEAD...refs/remotes/origin/{branch}", capture=True).split()
    if int(counts[0]):
        raise RuntimeError("Local history is ahead or divergent; integrate/push it deliberately before updating.")
    if run("git", "status", "--porcelain", "--untracked-files=all", capture=True):
        raise RuntimeError("Source changed during fetch; no update was applied.")
    run("git", "merge", "--ff-only", "--no-edit", f"refs/remotes/origin/{branch}")
    # Re-enter updated code after the lock is released, so controller updates take effect too.
    return [sys.executable, str(Path(__file__)), "start", "--mode", "dev", "--port", str(args.port or CONFIG["local_port"])]


def start_dev(args):
    env = environment(args)
    compose("dev", "build", env=env)
    backup("dev", env)
    compose("dev", "up", "--detach", "--no-build", "--wait", "--wait-timeout", "90", env=env)
    print("Development app: " + verify_http("dev", env, env["APP_REVISION"]))


def saved_image():
    path = STATE / "installed.json"
    return json.loads(path.read_text(encoding="utf-8")).get("image") if path.exists() else None


def public_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "App-Launchpad", "Accept": "application/json", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = response.read(1024 * 1024 + 1)
    if len(payload) > 1024 * 1024:
        raise RuntimeError("GitHub response exceeded the release discovery size limit.")
    return json.loads(payload)


def gh_json(path, asset=False):
    if not shutil.which("gh"):
        raise RuntimeError("Release discovery could not read GitHub. For a private repository, install/authenticate GitHub CLI and sign Docker into GHCR; or provide an accessible exact --image digest.")
    command = ["gh", "api", path]
    if asset:
        command += ["--header", "Accept: application/octet-stream"]
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise RuntimeError("GitHub discovery timed out; the running installation is unchanged.") from None
    if result.returncode:
        raise RuntimeError("GitHub CLI could not read the exact main release. Check repository access/authentication and wait for main publication to finish. The running installation is unchanged.")
    if len(result.stdout) > 1024 * 1024:
        raise RuntimeError("GitHub response exceeded the release discovery size limit.")
    return json.loads(result.stdout)


def current_main():
    path = "repos/" + CONFIG["repository"] + "/git/ref/heads/main"
    try:
        ref = public_json("https://api.github.com/" + path + "?launchpad=" + uuid.uuid4().hex)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        ref = gh_json(path)
    if not isinstance(ref, dict) or not isinstance(ref.get("object"), dict):
        raise RuntimeError("GitHub main returned an invalid revision response.")
    commit = ref.get("object", {}).get("sha", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("GitHub main did not identify a valid full source revision.")
    return commit


def discover_image():
    commit = current_main()
    repo = CONFIG["repository"]
    release_path = "repos/" + repo + "/releases/tags/release-" + commit
    try:
        release = public_json("https://api.github.com/" + release_path + "?launchpad=" + uuid.uuid4().hex)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        release = gh_json(release_path)
    if (not isinstance(release, dict) or release.get("tag_name") != "release-" + commit
            or release.get("draft") is not False or release.get("prerelease") is not False
            or not release.get("published_at")):
        raise RuntimeError("Current main's exact release is a draft, prerelease or incomplete publication. Resolve its publication state before retrying; the running installation is unchanged.")
    assets = [item for item in release.get("assets", []) if isinstance(item, dict) and item.get("name") == "deployment.json"]
    if (len(assets) != 1 or type(assets[0].get("id")) is not int
            or assets[0].get("state") != "uploaded"):
        raise RuntimeError("Current main has no unique fully uploaded deployment.json. Wait for publication or inspect the interrupted release; the running installation is unchanged.")
    try:
        manifest = public_json("https://github.com/" + repo + "/releases/download/release-" + commit + "/deployment.json")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        manifest = gh_json("repos/" + repo + "/releases/assets/" + str(assets[0]["id"]), asset=True)
    if not isinstance(manifest, dict):
        raise RuntimeError("Release manifest must be a JSON object.")
    prefix = "ghcr.io/" + repo.lower() + "@sha256:"
    image = manifest.get("image", "")
    if (manifest.get("revision") != commit or manifest.get("repository", repo) != repo
            or not isinstance(image, str) or not image.startswith(prefix)
            or not re.fullmatch(r"[0-9a-f]{64}", image[len(prefix):])):
        raise RuntimeError("Release manifest repository, exact main revision or immutable image digest is invalid.")
    if "schema" in manifest and (type(manifest["schema"]) is not int or manifest["schema"] != 1):
        raise RuntimeError("Unsupported release manifest schema.")
    if "digest" in manifest and manifest["digest"] != image.split("@", 1)[1]:
        raise RuntimeError("Release digest fields disagree.")
    return image, commit


def image_cached(image):
    probe = subprocess.run(["docker", "image", "inspect", image], cwd=ROOT,
                           capture_output=True, text=True)
    return probe.returncode == 0


def start_installed(args):
    previous = saved_image()
    discovered = None
    image = args.image or previous
    if not args.image and (args.action == "update" or not previous):
        image, discovered = discover_image()
    expected_prefix = "ghcr.io/" + CONFIG["repository"].lower() + "@sha256:"
    pinned = image.startswith(expected_prefix) and re.fullmatch(r"[0-9a-f]{64}", image[len(expected_prefix):])
    if not pinned and not args.allow_local_image:
        raise RuntimeError("Installed images must use this repository's immutable GHCR digest. --allow-local-image is for isolated local rehearsals only.")
    if pinned and not image_cached(image):
        run("docker", "pull", image)
    expected = image_revision(image)
    if discovered and expected != discovered:
        raise RuntimeError("Published image label disagrees with the discovered exact main revision.")
    candidate(args, image, expected)
    env = environment(args, image=image, revision_value=expected)
    old_env = environment(args, image=previous or image, revision_value=expected)
    backup("installed", old_env)
    if discovered and current_main() != discovered:
        raise RuntimeError("Main advanced during preflight; retry update for the newer release. The running installation is unchanged.")
    try:
        compose("installed", "up", "--detach", "--no-build", "--wait", "--wait-timeout", "90", env=env)
        url = verify_http("installed", env, expected)
        staged = STATE / "installed.json.tmp"
        staged.write_text(json.dumps({"image": image, "revision": expected}) + "\n", encoding="utf-8")
        staged.replace(STATE / "installed.json")
    except Exception:
        if previous:
            print("Activation failed; attempting the previous image. Durable data is not rolled back.", file=sys.stderr)
            compose("installed", "up", "--detach", "--no-build", "--wait", "--wait-timeout", "90", env=old_env)
            verify_http("installed", old_env, image_revision(previous))
        raise
    print("Installed app: " + url + " (" + expected + ")")


def check_app(args):
    expected = revision()
    image = CONFIG["name"] + "-check:" + expected
    source = "https://github.com/" + CONFIG["repository"]
    for target in ("test", "runtime"):
        command = ["docker", "build", "--target", target, "--build-arg", "APP_REVISION=" + expected,
                   "--build-arg", "APP_SOURCE_URL=" + source]
        if target == "runtime":
            command += ["--tag", image]
        run(*command, ".")
    image_revision(image)
    run("docker", "run", "--rm", "--network", "none", "--read-only", "--entrypoint", "python", image,
        "-c", "import importlib.util,pathlib; assert not any(pathlib.Path(p).exists() for p in ['/workspace/tests','/e2e','/opt/test-fixtures']); assert importlib.util.find_spec('pytest') is None; from server import create_app; print('Runtime excludes test fixtures and test packages.')")
    e2e = has_e2e_stage()
    candidate(args, image, expected, e2e=e2e)
    print("Container tests, runtime health, source label and exact revision" +
          (", and E2E" if e2e else "") + " passed: " + expected)
    if not getattr(args, "keep_candidate", False):
        run("docker", "image", "rm", image, check=False)


def clean_candidate(args):
    path = STATE / "candidate.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    project = receipt["project"]
    if not re.fullmatch(re.escape(CONFIG["name"]) + r"-check-[0-9a-f]{10}", project):
        raise RuntimeError("Unrecognized candidate identity; no resource removed.")
    env = environment(args, image=receipt["image"], revision_value=receipt["revision"])
    env.update(APP_PORT=receipt["port"], PUBLIC_ORIGIN=receipt["origin"])
    compose("installed", "down", "--volumes", env=env, project=project)
    run("docker", "image", "rm", receipt["image"], check=False)
    print("Removed only the recorded candidate containers/network/synthetic volume/image. Recycle the private .runtime candidate/session receipts after review.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "update", "doctor", "check", "clean-candidate", "stop", "status", "logs"))
    parser.add_argument("--mode", choices=("dev", "installed"), default="dev")
    parser.add_argument("--image")
    parser.add_argument("--allow-local-image", action="store_true")
    parser.add_argument("--port", type=int)
    parser.add_argument("--keep-candidate", action="store_true", help="After a passing check, retain only its isolated synthetic candidate for a local walkthrough.")
    args = parser.parse_args()
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    followup = None
    with lock():
        if args.action == "doctor":
            doctor()
        elif args.action == "check":
            check_app(args)
        elif args.action == "clean-candidate":
            clean_candidate(args)
        elif args.action == "update" and args.mode == "dev":
            followup = source_update(args)
        elif args.action in ("start", "update"):
            if args.mode == "dev":
                start_dev(args)
            else:
                start_installed(args)
        else:
            env = environment(args, image=args.image or saved_image() or "unused-local-state")
            command = {"stop": ["down"], "status": ["ps"], "logs": ["logs", "--tail", "80"]}[args.action]
            compose(args.mode, *command, env=env)
    if followup:
        return subprocess.call(followup, cwd=ROOT)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError) as error:
        print("Error: " + str(error), file=sys.stderr)
        sys.exit(getattr(error, "returncode", 1))
