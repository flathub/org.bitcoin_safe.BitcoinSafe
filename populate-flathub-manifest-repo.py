#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
import textwrap
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib
import yaml
from packaging.markers import Marker
from packaging.specifiers import SpecifierSet
from packaging.version import Version


DEFAULT_SOURCE_REPO_URL = "https://github.com/andreasgriffin/bitcoin-safe/"
APP_ID = "org.bitcoin_safe.BitcoinSafe"
APP_NAME = "Bitcoin Safe"
REPO_SCREENSHOT_BASE = (
    "https://raw.githubusercontent.com/flathub/org.bitcoin_safe.BitcoinSafe/master/screenshots"
)
SCREENSHOT_SOURCES = [
    ("docs/tx-linux.png", "tx-linux.png"),
]
ICON_SOURCES = [
    ("tools/resources/icon.svg", f"{APP_ID}.svg"),
    ("tools/resources/icon-128.png", f"{APP_ID}.png"),
]
RUNTIME_ENV = {
    "implementation_name": "cpython",
    "os_name": "posix",
    "platform_machine": "x86_64",
    "platform_python_implementation": "CPython",
    "platform_release": "",
    "platform_system": "Linux",
    "platform_version": "",
    "python_full_version": "3.12.0",
    "python_version": "3.12",
    "sys_platform": "linux",
    "extra": "",
}
NAMESPACE = {"": "http://www.freedesktop.org/standards/appstream/1.0"}


@dataclass
class ReleaseInfo:
    source_repo_url: str
    tag_name: str
    published_at: str
    prerelease: bool
    tarball_url: str
    html_url: str
    body: str

    @property
    def date(self) -> str:
        return self.published_at[:10]

    @property
    def branch(self) -> str:
        return "beta" if self.prerelease or "rc" in self.tag_name.lower() else "stable"


@dataclass
class SourceContext:
    repo_url: str
    release: ReleaseInfo
    tree_root: Path


def github_repo_slug(repo_url: str) -> str:
    parsed = urllib.parse.urlparse(repo_url)
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    slug = path.strip("/")
    if slug.count("/") != 1:
        raise ValueError(f"Unsupported repository URL: {repo_url}")
    return slug


def json_request(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "bitcoin-safe-flathub-generator",
        },
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def text_request(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "bitcoin-safe-flathub-generator"})
    with urllib.request.urlopen(request) as response:
        return response.read().decode("utf-8")


def binary_request(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "bitcoin-safe-flathub-generator"})
    with urllib.request.urlopen(request) as response:
        return response.read()


def fetch_release(repo_url: str, tag_name: str | None) -> ReleaseInfo:
    slug = github_repo_slug(repo_url)
    if tag_name:
        payload = json_request(f"https://api.github.com/repos/{slug}/releases/tags/{tag_name}")
    else:
        releases = json_request(f"https://api.github.com/repos/{slug}/releases?per_page=1")
        if not releases:
            raise RuntimeError(f"No releases found for {repo_url}")
        payload = releases[0]
    return ReleaseInfo(
        source_repo_url=repo_url,
        tag_name=payload["tag_name"],
        published_at=payload["published_at"],
        prerelease=bool(payload["prerelease"]),
        tarball_url=payload["tarball_url"],
        html_url=payload["html_url"],
        body=payload.get("body", ""),
    )


def extract_release_tree(release: ReleaseInfo, workdir: Path) -> Path:
    archive_path = workdir / f"{release.tag_name}.tar.gz"
    archive_path.write_bytes(binary_request(release.tarball_url))
    with tarfile.open(archive_path) as tar:
        tar.extractall(workdir, filter="data")
    roots = [path for path in workdir.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise RuntimeError(f"Expected exactly one extracted root in {workdir}, found {len(roots)}")
    return roots[0]


def build_source_context(
    repo_url: str,
    local_source_checkout: str | None,
    release_tag: str | None,
) -> SourceContext:
    release = fetch_release(repo_url, release_tag)
    if local_source_checkout:
        tree_root = Path(local_source_checkout).resolve()
    else:
        tempdir = Path(tempfile.mkdtemp(prefix="bitcoin-safe-flathub-"))
        tree_root = extract_release_tree(release, tempdir)
    return SourceContext(repo_url=repo_url, release=release, tree_root=tree_root)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(read_text(path))


def load_toml(path: Path) -> Any:
    return tomllib.loads(read_text(path))


def marker_matches(marker_text: str | dict[str, str] | None) -> bool:
    if isinstance(marker_text, dict):
        marker_text = marker_text.get("main")
    if not marker_text:
        return True
    return Marker(marker_text).evaluate(RUNTIME_ENV)


def normalize_project_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def safe_module_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def choose_artifact(file_entries: list[dict[str, str]]) -> dict[str, str]:
    def score(filename: str) -> tuple[int, str]:
        lower = filename.lower()
        if lower.endswith(".whl"):
            if "py3-none-any" in lower or "py2.py3-none-any" in lower:
                return (0, lower)
            if "abi3" in lower and "x86_64" in lower and "manylinux" in lower:
                return (1, lower)
            if "cp312" in lower and "x86_64" in lower and "manylinux" in lower:
                return (2, lower)
            if "cp312" in lower and "x86_64" in lower and "linux" in lower:
                return (3, lower)
            return (50, lower)
        if lower.endswith(".tar.gz") or lower.endswith(".zip") or lower.endswith(".tar.bz2"):
            return (100, lower)
        return (200, lower)

    compatible = sorted(file_entries, key=lambda entry: score(entry["file"]))
    if not compatible:
        raise RuntimeError("No files available to choose from")
    return compatible[0]


class PypiIndex:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], dict[str, Any]] = {}

    def release_json(self, name: str, version: str) -> dict[str, Any]:
        key = (normalize_project_name(name), version)
        if key not in self._cache:
            url = f"https://pypi.org/pypi/{urllib.parse.quote(name)}/{urllib.parse.quote(version)}/json"
            self._cache[key] = json.loads(text_request(url))
        return self._cache[key]

    def file_url(self, name: str, version: str, filename: str) -> str:
        payload = self.release_json(name, version)
        for entry in payload["urls"]:
            if entry["filename"] == filename:
                return entry["url"]
        raise RuntimeError(f"Unable to find {filename} in PyPI release {name}=={version}")

    def resolve_version(self, name: str, specifier: str) -> str:
        payload = json.loads(text_request(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json"))
        spec = SpecifierSet(specifier)
        candidates = sorted((Version(item) for item in payload["releases"].keys()), reverse=True)
        for candidate in candidates:
            if spec.contains(candidate, prereleases=True):
                return str(candidate)
        raise RuntimeError(f"No PyPI release of {name} satisfies {specifier}")


def artifact_source_entry(name: str, version: str, file_entry: dict[str, str], pypi: PypiIndex) -> dict[str, str]:
    return {
        "type": "file",
        "url": pypi.file_url(name, version, file_entry["file"]),
        "sha256": file_entry["hash"].split(":", 1)[1],
    }


def dependency_names(package: dict[str, Any]) -> list[str]:
    deps = package.get("dependencies", {})
    if isinstance(deps, dict):
        return list(deps.keys())
    return []


def closure_from_lock(
    lock_packages: dict[str, dict[str, Any]],
    seed_names: set[str],
) -> list[dict[str, Any]]:
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(name: str) -> None:
        normalized = normalize_project_name(name)
        if normalized in seen or normalized not in lock_packages:
            return
        seen.add(normalized)
        package = lock_packages[normalized]
        if not marker_matches(package.get("markers")):
            return
        for dependency in dependency_names(package):
            visit(dependency)
        ordered.append(package)

    for name in sorted(seed_names):
        visit(name)
    return ordered


def download_sha256(url: str) -> str:
    digest = hashlib.sha256()
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "bitcoin-safe-flathub-generator"})) as response:
        for chunk in iter(lambda: response.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def github_archive_url(git_url: str, resolved_reference: str) -> str:
    if git_url.endswith(".git"):
        git_url = git_url[:-4]
    parsed = urllib.parse.urlparse(git_url)
    path = parsed.path.rstrip("/")
    if parsed.netloc != "github.com":
        raise RuntimeError(f"Only GitHub git sources are currently supported, got {git_url}")
    return f"https://github.com{path}/archive/{resolved_reference}.tar.gz"


def extract_archive_to_temp(url: str) -> Path:
    data = binary_request(url)
    tempdir = Path(tempfile.mkdtemp(prefix="bitcoin-safe-src-"))
    archive_path = tempdir / "archive.tar.gz"
    archive_path.write_bytes(data)
    with tarfile.open(archive_path) as tar:
        tar.extractall(tempdir, filter="data")
    roots = [path for path in tempdir.iterdir() if path.is_dir()]
    for root in roots:
        if root.name != archive_path.stem:
            return root
    if roots:
        return roots[0]
    raise RuntimeError(f"Unable to extract archive from {url}")


def build_requirements_for_tree(tree_root: Path) -> list[str]:
    pyproject_path = tree_root / "pyproject.toml"
    if pyproject_path.exists():
        payload = load_toml(pyproject_path)
        build_system = payload.get("build-system", {})
        if build_system:
            return list(build_system.get("requires", []))
    if (tree_root / "setup.py").exists():
        return ["setuptools", "wheel"]
    return []


def backend_name(spec: str) -> str:
    match = re.match(r"([A-Za-z0-9_.-]+)", spec)
    if not match:
        raise RuntimeError(f"Unable to parse backend requirement {spec}")
    return match.group(1)


def resolve_backend_packages(
    lock_packages: dict[str, dict[str, Any]],
    requirement_specs: set[str],
    pypi: PypiIndex,
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    seed_names = {backend_name(spec) for spec in requirement_specs}
    for package in closure_from_lock(lock_packages, seed_names):
        file_entry = choose_artifact(package["files"])
        resolved.append(
            {
                "name": package["name"],
                "version": package["version"],
                "file_entry": file_entry,
                "source": artifact_source_entry(package["name"], package["version"], file_entry, pypi),
            }
        )

    seen: set[str] = {normalize_project_name(item["name"]) for item in resolved}
    for spec in sorted(requirement_specs):
        name = backend_name(spec)
        normalized = normalize_project_name(name)
        if normalized in seen:
            continue
        seen.add(normalized)
        if normalized in lock_packages:
            package = lock_packages[normalized]
            version = package["version"]
            file_entry = choose_artifact(package["files"])
            resolved.append(
                {
                    "name": package["name"],
                    "version": version,
                    "file_entry": file_entry,
                    "source": artifact_source_entry(package["name"], version, file_entry, pypi),
                }
            )
            continue

        specifier = spec[len(name) :]
        version = pypi.resolve_version(name, specifier or "")
        payload = pypi.release_json(name, version)
        files = [
            {"file": entry["filename"], "hash": f"sha256:{entry['digests']['sha256']}"}
            for entry in payload["urls"]
        ]
        file_entry = choose_artifact(files)
        resolved.append(
            {
                "name": name,
                "version": version,
                "file_entry": file_entry,
                "source": {
                    "type": "file",
                    "url": pypi.file_url(name, version, file_entry["file"]),
                    "sha256": file_entry["hash"].split(":", 1)[1],
                },
            }
        )
    return resolved


def evaluate_packages(lock_payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    main_packages: list[dict[str, Any]] = []
    all_packages: dict[str, dict[str, Any]] = {}
    for package in lock_payload["package"]:
        normalized = normalize_project_name(package["name"])
        all_packages[normalized] = package
        if "main" not in package.get("groups", []):
            continue
        if not marker_matches(package.get("markers")):
            continue
        if normalized == normalize_project_name("bitcoin-safe"):
            continue
        main_packages.append(package)
    return main_packages, all_packages


def topological_git_packages(git_packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {normalize_project_name(pkg["name"]): pkg for pkg in git_packages}
    indegree = {name: 0 for name in by_name}
    graph = {name: set() for name in by_name}
    for name, package in by_name.items():
        for dependency in dependency_names(package):
            dep_name = normalize_project_name(dependency)
            if dep_name in by_name and dep_name not in graph[name]:
                graph[dep_name].add(name)
                indegree[name] += 1
    ordered: list[dict[str, Any]] = []
    ready = sorted([name for name, degree in indegree.items() if degree == 0])
    while ready:
        current = ready.pop(0)
        ordered.append(by_name[current])
        for child in sorted(graph[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        ready.sort()
    if len(ordered) != len(git_packages):
        raise RuntimeError("Git package dependency cycle detected")
    return ordered


def render_requirements(path: Path, packages: list[dict[str, Any]]) -> None:
    lines = [f"{package['name']}=={package['version']}" for package in packages]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def serialize_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=4) + "\n", encoding="utf-8")


def write_flathub_json(path: Path) -> None:
    serialize_json(
        path,
        {
            "only-arches": ["x86_64"],
            "disable-external-data-checker": True,
        },
    )


def update_metainfo(upstream_metainfo_path: Path, output_path: Path, release: ReleaseInfo) -> None:
    tree = ET.parse(upstream_metainfo_path)
    root = tree.getroot()
    releases = root.find("releases")
    if releases is None:
        releases = ET.SubElement(root, "releases")
    releases.clear()
    ET.SubElement(releases, "release", {"version": release.tag_name, "date": release.date})

    screenshots = root.find("screenshots")
    if screenshots is None:
        screenshots = ET.SubElement(root, "screenshots")
    screenshots.clear()
    screenshot = ET.SubElement(screenshots, "screenshot", {"type": "default"})
    image = ET.SubElement(screenshot, "image", {"type": "source"})
    image.text = f"{REPO_SCREENSHOT_BASE}/tx-linux.png"

    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def write_readme(path: Path, release: ReleaseInfo) -> None:
    text = f"""# {APP_ID}

Flathub-style Flatpak packaging for [Bitcoin Safe]({release.html_url}).

## Maintainer Workflow

Run:

```sh
./populate-flathub-manifest-repo.py
```

By default the generator reads from `{DEFAULT_SOURCE_REPO_URL}` and uses the most recently published GitHub release, including prereleases. You can override that with:

- `--release-tag <tag>`
- `--source-repo-url <url>`
- `--local-source-checkout <path>`

The generator treats the upstream Flatpak manifest as the baseline and rewrites only the Flathub-incompatible parts:

- replaces local staged sources with pinned release archives
- replaces build-time dependency resolution with generated, pinned dependency manifests
- removes build-time network assumptions

Flathub builds from the checked-in files in this repo, not from Docker.

## Current Release

- Source repo: `{release.source_repo_url}`
- Selected tag: `{release.tag_name}`
- Channel: `{release.branch}`
- Published: `{release.date}`
"""
    path.write_text(text, encoding="utf-8")


def write_desktop_file(upstream_desktop_path: Path, output_path: Path) -> None:
    text = read_text(upstream_desktop_path)
    text = re.sub(r"^Exec=.*$", "Exec=run-bitcoin-safe.sh %F", text, flags=re.MULTILINE)
    text = re.sub(r"^Icon=.*$", f"Icon={APP_ID}", text, flags=re.MULTILINE)
    output_path.write_text(text, encoding="utf-8")


def build_manifest(
    upstream_manifest: dict[str, Any],
    release: ReleaseInfo,
    app_source_sha256: str,
) -> dict[str, Any]:
    manifest = {
        "app-id": upstream_manifest["app-id"],
        "branch": release.branch,
        "runtime": upstream_manifest["runtime"],
        "runtime-version": upstream_manifest["runtime-version"],
        "sdk": upstream_manifest["sdk"],
        "command": upstream_manifest["command"],
        "separate-locales": upstream_manifest.get("separate-locales", False),
        "finish-args": copy.deepcopy(upstream_manifest.get("finish-args", [])),
        "modules": [],
    }

    for module in upstream_manifest["modules"][:-1]:
        manifest["modules"].append(copy.deepcopy(module))

    manifest["modules"].extend(
        [
            "python3-build-backends.json",
            "python3-runtime.json",
            "python3-git-packages.json",
            {
                "name": "bitcoin-safe",
                "buildsystem": "simple",
                "build-commands": [
                    "pip3 install --no-build-isolation --no-deps --prefix=${FLATPAK_DEST} .",
                    f"install -Dm755 run-bitcoin-safe.sh /app/bin/run-bitcoin-safe.sh",
                    f"install -Dm644 {APP_ID}.svg /app/share/icons/hicolor/scalable/apps/{APP_ID}.svg",
                    f"install -Dm644 {APP_ID}.png /app/share/icons/hicolor/128x128/apps/{APP_ID}.png",
                    f"install -Dm644 {APP_ID}.metainfo.xml /app/share/metainfo/{APP_ID}.metainfo.xml",
                    f"install -Dm644 {APP_ID}.desktop /app/share/applications/{APP_ID}.desktop",
                ],
                "sources": [
                    {
                        "type": "archive",
                        "url": release.tarball_url,
                        "sha256": app_source_sha256,
                    },
                    {"type": "file", "path": "run-bitcoin-safe.sh"},
                    {"type": "file", "path": f"{APP_ID}.svg"},
                    {"type": "file", "path": f"{APP_ID}.png"},
                    {"type": "file", "path": f"{APP_ID}.desktop"},
                    {"type": "file", "path": f"{APP_ID}.metainfo.xml"},
                ],
            },
        ]
    )
    return manifest


def collect_backend_specs(
    context: SourceContext,
    runtime_packages: list[dict[str, Any]],
    git_packages: list[dict[str, Any]],
    pypi: PypiIndex,
) -> set[str]:
    specs: set[str] = set()
    specs.update(["poetry-core", "setuptools", "wheel"])

    chosen_runtime_sdists: list[tuple[str, str, str]] = []
    for package in runtime_packages:
        chosen = package["chosen_artifact"]
        if chosen["file"].lower().endswith(".whl"):
            continue
        chosen_runtime_sdists.append((package["name"], package["version"], package["artifact_url"]))

    for _, _, url in chosen_runtime_sdists:
        tree_root = extract_archive_to_temp(url)
        specs.update(build_requirements_for_tree(tree_root))

    for package in git_packages:
        source = package["source"]
        archive_url = github_archive_url(source["url"], source["resolved_reference"])
        tree_root = extract_archive_to_temp(archive_url)
        specs.update(build_requirements_for_tree(tree_root))

    specs.update(build_requirements_for_tree(context.tree_root))
    return {spec for spec in specs if spec}


def prepare_runtime_packages(main_packages: list[dict[str, Any]], pypi: PypiIndex) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    runtime_packages: list[dict[str, Any]] = []
    git_packages: list[dict[str, Any]] = []
    for package in main_packages:
        package = copy.deepcopy(package)
        if package.get("source", {}).get("type") == "git":
            git_packages.append(package)
            continue
        chosen_artifact = choose_artifact(package["files"])
        package["chosen_artifact"] = chosen_artifact
        package["artifact_url"] = pypi.file_url(package["name"], package["version"], chosen_artifact["file"])
        runtime_packages.append(package)
    return runtime_packages, git_packages


def write_dependency_modules(
    output_dir: Path,
    release: ReleaseInfo,
    context: SourceContext,
    main_packages: list[dict[str, Any]],
    all_packages: dict[str, dict[str, Any]],
) -> None:
    pypi = PypiIndex()
    runtime_packages, git_packages = prepare_runtime_packages(main_packages, pypi)
    git_packages = topological_git_packages(git_packages)

    backend_specs = collect_backend_specs(context, runtime_packages, git_packages, pypi)
    backend_packages = resolve_backend_packages(all_packages, backend_specs, pypi)
    render_requirements(output_dir / "requirements-build-backends.txt", backend_packages)
    render_requirements(output_dir / "requirements-runtime.txt", runtime_packages)

    serialize_json(
        output_dir / "python3-build-backends.json",
        {
            "name": "python3-build-backends",
            "buildsystem": "simple",
            "build-commands": [
                "pip3 install --no-build-isolation --no-index --find-links=\"file://${PWD}\" --prefix=${FLATPAK_DEST} -r requirements-build-backends.txt"
            ],
            "sources": [{"type": "file", "path": "requirements-build-backends.txt"}]
            + [package["source"] for package in backend_packages],
        },
    )

    serialize_json(
        output_dir / "python3-runtime.json",
        {
            "name": "python3-runtime",
            "buildsystem": "simple",
            "build-commands": [
                "pip3 install --no-build-isolation --no-index --find-links=\"file://${PWD}\" --prefix=${FLATPAK_DEST} -r requirements-runtime.txt"
            ],
            "sources": [{"type": "file", "path": "requirements-runtime.txt"}]
            + [
                artifact_source_entry(package["name"], package["version"], package["chosen_artifact"], pypi)
                for package in runtime_packages
            ],
        },
    )

    git_modules = []
    for package in git_packages:
        archive_url = github_archive_url(package["source"]["url"], package["source"]["resolved_reference"])
        git_modules.append(
            {
                "name": f"python3-{safe_module_name(package['name'])}",
                "buildsystem": "simple",
                "build-commands": [
                    "pip3 install --no-build-isolation --no-deps --prefix=${FLATPAK_DEST} ."
                ],
                "sources": [
                    {
                        "type": "archive",
                        "url": archive_url,
                        "sha256": download_sha256(archive_url),
                    }
                ],
            }
        )

    serialize_json(
        output_dir / "python3-git-packages.json",
        {
            "name": "python3-git-packages",
            "buildsystem": "simple",
            "build-commands": [],
            "modules": git_modules,
        },
    )


def copy_assets(context: SourceContext, output_dir: Path) -> None:
    screenshots_dir = output_dir / "screenshots"
    if screenshots_dir.exists():
        shutil.rmtree(screenshots_dir)
    screenshots_dir.mkdir(exist_ok=True)

    for source_path, output_name in SCREENSHOT_SOURCES:
        shutil.copyfile(context.tree_root / source_path, screenshots_dir / output_name)

    for source_path, output_name in ICON_SOURCES:
        shutil.copyfile(context.tree_root / source_path, output_dir / output_name)

    shutil.copyfile(
        context.tree_root / "tools/build-linux/flatpak/run-bitcoin-safe.sh",
        output_dir / "run-bitcoin-safe.sh",
    )

    write_desktop_file(
        context.tree_root / "tools/resources/linux-bitcoin-safe.desktop",
        output_dir / f"{APP_ID}.desktop",
    )
    update_metainfo(
        context.tree_root / "tools/build-linux/flatpak/org.bitcoin_safe.BitcoinSafe.metainfo.xml",
        output_dir / f"{APP_ID}.metainfo.xml",
        context.release,
    )


def generate_repo(output_dir: Path, context: SourceContext) -> None:
    upstream_manifest = load_yaml(
        context.tree_root / "tools/build-linux/flatpak/org.bitcoin_safe.BitcoinSafe.yml"
    )
    lock_payload = load_toml(context.tree_root / "poetry.lock")
    main_packages, all_packages = evaluate_packages(lock_payload)
    app_source_sha256 = download_sha256(context.release.tarball_url)

    write_flathub_json(output_dir / "flathub.json")
    write_readme(output_dir / "README.md", context.release)
    copy_assets(context, output_dir)
    write_dependency_modules(output_dir, context.release, context, main_packages, all_packages)

    manifest = build_manifest(upstream_manifest, context.release, app_source_sha256)
    (output_dir / "org.bitcoin_safe.BitcoinSafe.yml").write_text(
        yaml.safe_dump(manifest, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Populate the Bitcoin Safe Flathub manifest repo.")
    parser.add_argument("--source-repo-url", default=DEFAULT_SOURCE_REPO_URL)
    parser.add_argument("--local-source-checkout")
    parser.add_argument("--release-tag")
    parser.add_argument("--use-latest-release", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-dir", default=".")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tag_name = args.release_tag
    context = build_source_context(
        repo_url=args.source_repo_url,
        local_source_checkout=args.local_source_checkout,
        release_tag=tag_name,
    )
    generate_repo(Path(args.output_dir).resolve(), context)


if __name__ == "__main__":
    main()
