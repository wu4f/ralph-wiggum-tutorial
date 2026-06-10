"""Repository ingestion, execution-flow detection, and flow-quiz scoring."""
from __future__ import annotations

from dataclasses import dataclass
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from flask import current_app, has_app_context

from .code_map import build_execution_graph


JSONDict = dict[str, Any]


_GITHUB_ROOT = 'github.com'
_FIXTURE_OWNER = 'copilot-fixtures'
_MAX_FLOWS = 4
_MAX_CHAIN_DEPTH = 4
_EXCLUDED_ENTRY_DIRS = {
    'tests', 'test', 'docs', 'docs_src', 'examples', 'example', 'tutorial',
    'tutorials', 'benchmarks', 'scripts', 'fixtures', '__tests__',
}
_TEXT_SUFFIXES = {
    '.css', '.html', '.js', '.json', '.jsx', '.md', '.py', '.toml', '.ts',
    '.tsx', '.txt', '.yaml', '.yml',
}
_CODE_SUFFIXES = {'.py', '.js', '.jsx', '.ts', '.tsx'}
_IMPORT_FILE_SUFFIXES = ('.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs')
_SKIP_DIRECTORIES = {
    '.git', '.next', '.venv', '__pycache__', 'build', 'coverage', 'dist',
    'node_modules', 'vendor', 'site-packages', 'examples', 'docs',
}
_LANGUAGE_MAP = {
    '.css': 'CSS',
    '.html': 'HTML',
    '.js': 'JavaScript',
    '.jsx': 'React JSX',
    '.json': 'JSON',
    '.md': 'Markdown',
    '.py': 'Python',
    '.ts': 'TypeScript',
    '.tsx': 'React TSX',
}
_FRAMEWORK_CANDIDATES = (
    ('Flask', 'framework:flask'),
    ('FastAPI', 'framework:fastapi'),
    ('Django', 'framework:django'),
    ('React', 'framework:react'),
    ('Express', 'framework:express'),
    ('Vite', 'framework:vite'),
    ('Pytest', 'framework:pytest'),
    ('Vitest', 'framework:vitest'),
    ('Playwright', 'framework:playwright'),
)
_DEFAULT_LIMITS = {
    'LEARNING_MAX_ARCHIVE_BYTES': 40 * 1024 * 1024,
    'LEARNING_MAX_EXTRACTED_BYTES': 120 * 1024 * 1024,
    'LEARNING_MAX_ANALYZED_FILES': 4000,
    'LEARNING_MAX_FILE_BYTES': 512 * 1024,
}
_PY_ENTRY_NAMES = {
    '__main__.py', 'main.py', 'app.py', 'manage.py', 'wsgi.py', 'asgi.py',
    'server.py', 'cli.py', 'run.py', '__init__.py',
}
_JS_ENTRY_NAMES = {
    'index.ts', 'index.tsx', 'index.js', 'index.jsx', 'main.ts', 'main.tsx',
    'main.js', 'main.jsx', 'server.ts', 'server.js', 'app.ts', 'app.js',
}
_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+[^'"]*?from\s+|import\s*\(|export\s+[^'"]*?from\s+|require\(\s*)"""
    r"""(?P<quote>['"])(?P<path>\.\.?/[^'"]+)(?P=quote)"""
)
_PY_FROM_RE = re.compile(
    r"""^\s*from\s+(?P<mod>\.*[\w.]*)\s+import\s+(?P<names>[^\n#]+)""", re.MULTILINE
)
_PY_IMPORT_RE = re.compile(
    r"""^\s*import\s+(?P<mods>[\w.]+(?:\s*,\s*[\w.]+)*)""", re.MULTILINE
)
_RENDER_TEMPLATE_RE = re.compile(r"""render_template\(\s*['"](?P<template>[^'"]+)['"]""")
_ROUTE_RE = re.compile(r"""@\w+\.route\(\s*['"](?P<route>[^'"]+)['"]""")
_DATA_ISLAND_RE = re.compile(r"""data-island=['"](?P<name>[^'"]+)['"]""")
_ISLAND_REGISTRY_RE = re.compile(
    r"""(?P<quote>['"]?)(?P<name>[\w-]+)(?P=quote)\s*:\s*\(\)\s*=>\s*import\(\s*['"](?P<path>[^'"]+)['"]\s*\)"""
)


@dataclass(frozen=True)
class RepositoryRef:
    """Normalized repository identity."""

    owner: str
    repo: str
    url: str
    default_branch: str
    source: str


@dataclass(frozen=True)
class AnalyzedFile:
    """Text file loaded from an archive or fixture repository."""

    path: str
    content: str
    size: int


class RepositoryAnalysisError(ValueError):
    """Raised when a repository cannot be safely analyzed."""


def analyze_repository(repository_url: str) -> tuple[JSONDict, JSONDict]:
    """Analyze a repository URL into learner-safe payload and answer keys."""
    repo_ref = _normalize_repository_url(repository_url)
    files = _load_repository_files(repo_ref)
    return _build_analysis(repo_ref, files)


def score_flow(answer_keys: JSONDict, flow_id: str, ordered_step_ids: list[str]) -> JSONDict:
    """Score a student's ordered execution-flow answer against the snapshot."""
    flows: JSONDict = answer_keys.get('flows', {})
    flow = flows.get(flow_id)
    if flow is None:
        raise RepositoryAnalysisError('Unknown flow requested for scoring.')

    correct_order: list[str] = flow['orderedStepIds']
    step_lookup: dict[str, JSONDict] = flow['stepLookup']

    correct_positions = sum(
        1
        for index, step_id in enumerate(correct_order)
        if index < len(ordered_step_ids) and ordered_step_ids[index] == step_id
    )
    max_score = len(correct_order)
    is_correct = (
        len(ordered_step_ids) == max_score and correct_positions == max_score
    )

    if is_correct:
        feedback = 'Correct — that is the execution order for this flow.'
    elif correct_positions == 0:
        feedback = (
            'None of the steps are in the right position yet. Start from the '
            'code that runs first when this flow is triggered.'
        )
    else:
        feedback = (
            f'{correct_positions} of {max_score} steps are in the right place. '
            'Follow each connection from the entry point outward.'
        )

    return {
        'flowId': flow_id,
        'score': correct_positions,
        'maxScore': max_score,
        'isCorrect': is_correct,
        'feedback': feedback,
        'correctOrder': [step_lookup[step_id] for step_id in correct_order],
    }


def _normalize_repository_url(repository_url: str) -> RepositoryRef:
    parsed = urlparse(repository_url.strip())
    if parsed.scheme != 'https' or parsed.netloc != _GITHUB_ROOT:
        raise RepositoryAnalysisError(
            'Use a root GitHub repository URL in the form https://github.com/{owner}/{repo}.'
        )

    path_parts = [part for part in parsed.path.split('/') if part]
    if len(path_parts) != 2:
        raise RepositoryAnalysisError(
            'Only root GitHub repository URLs are supported in v1.'
        )
    if parsed.query or parsed.fragment:
        raise RepositoryAnalysisError(
            'Query strings and fragments are not supported in repository URLs.'
        )

    owner, repo = path_parts
    repo = repo.removesuffix('.git')
    default_branch = 'main'
    source = 'github'
    if _allow_fixture_repos() and owner == _FIXTURE_OWNER and _fixture_root_for(repo).exists():
        source = 'fixture'
    else:
        default_branch = _fetch_default_branch(owner, repo)

    return RepositoryRef(
        owner=owner,
        repo=repo,
        url=f'https://github.com/{owner}/{repo}',
        default_branch=default_branch,
        source=source,
    )


def _fetch_default_branch(owner: str, repo: str) -> str:
    metadata_url = f'https://api.github.com/repos/{owner}/{repo}'
    request = Request(
        metadata_url,
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'GitHub-Copilot-CLI',
        },
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except HTTPError as error:
        raise RepositoryAnalysisError(
            'The repository could not be fetched from GitHub.'
        ) from error
    except URLError as error:
        raise RepositoryAnalysisError(
            'GitHub could not be reached while analyzing that repository.'
        ) from error

    default_branch = payload.get('default_branch')
    if not isinstance(default_branch, str) or not default_branch:
        raise RepositoryAnalysisError('GitHub did not return a usable default branch.')
    return default_branch


def _load_repository_files(repo_ref: RepositoryRef) -> list[AnalyzedFile]:
    if repo_ref.source == 'fixture':
        return _load_fixture_files(repo_ref.repo)
    return _load_archive_files(repo_ref)


def _fixture_root_for(repo: str) -> Path:
    return Path(__file__).resolve().parents[3] / 'tests' / 'fixtures' / 'repositories' / repo


def _load_fixture_files(repo: str) -> list[AnalyzedFile]:
    fixture_root = _fixture_root_for(repo)
    if not fixture_root.exists():
        raise RepositoryAnalysisError('The fixture repository could not be located.')

    files: list[AnalyzedFile] = []
    file_limit = _config_int('LEARNING_MAX_ANALYZED_FILES')
    total_size = 0
    size_limit = _config_int('LEARNING_MAX_EXTRACTED_BYTES')

    for path in sorted(fixture_root.rglob('*')):
        if not path.is_file():
            continue
        relative_path = path.relative_to(fixture_root).as_posix()
        if _should_skip_path(relative_path):
            continue
        total_size += path.stat().st_size
        if total_size > size_limit:
            raise RepositoryAnalysisError('The repository is too large to analyze safely.')
        files.append(
            AnalyzedFile(
                path=relative_path,
                content=path.read_text(encoding='utf-8'),
                size=path.stat().st_size,
            )
        )
        if len(files) > file_limit:
            raise RepositoryAnalysisError('The repository has too many files to analyze safely.')
    return files


def _load_archive_files(repo_ref: RepositoryRef) -> list[AnalyzedFile]:
    archive_url = (
        f'https://codeload.github.com/{repo_ref.owner}/{repo_ref.repo}/tar.gz/'
        f'refs/heads/{repo_ref.default_branch}'
    )
    request = Request(archive_url, headers={'User-Agent': 'GitHub-Copilot-CLI'})
    max_archive_bytes = _config_int('LEARNING_MAX_ARCHIVE_BYTES')
    try:
        with urlopen(request, timeout=30) as response:
            archive_bytes = response.read(max_archive_bytes + 1)
    except HTTPError as error:
        raise RepositoryAnalysisError(
            'GitHub did not provide a source archive for that repository.'
        ) from error
    except URLError as error:
        raise RepositoryAnalysisError(
            'GitHub could not be reached while downloading the source archive.'
        ) from error

    if len(archive_bytes) > max_archive_bytes:
        raise RepositoryAnalysisError(
            'The repository is too large to analyze in v1. Try a smaller repository.'
        )

    file_limit = _config_int('LEARNING_MAX_ANALYZED_FILES')
    max_total_bytes = _config_int('LEARNING_MAX_EXTRACTED_BYTES')
    max_file_bytes = _config_int('LEARNING_MAX_FILE_BYTES')
    files: list[AnalyzedFile] = []
    extracted_bytes = 0

    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            path = PurePosixPath(member.name)
            relative_path = PurePosixPath(*path.parts[1:]).as_posix()
            if not relative_path or _should_skip_path(relative_path):
                continue
            if member.size > max_file_bytes:
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            data = extracted.read(max_file_bytes + 1)
            if len(data) > max_file_bytes or b'\x00' in data:
                continue
            extracted_bytes += len(data)
            if extracted_bytes > max_total_bytes:
                raise RepositoryAnalysisError(
                    'The repository is too large to analyze in v1. Try a smaller repository.'
                )
            text = data.decode('utf-8', errors='ignore')
            files.append(AnalyzedFile(path=relative_path, content=text, size=len(data)))
            if len(files) > file_limit:
                raise RepositoryAnalysisError(
                    'The repository has too many files to analyze in v1.'
                )
    return files


def _should_skip_path(relative_path: str) -> bool:
    parts = PurePosixPath(relative_path).parts
    if any(part in _SKIP_DIRECTORIES for part in parts):
        return True
    if any(part.startswith('.') and len(part) > 1 for part in parts[:-1]):
        return True
    return PurePosixPath(relative_path).suffix not in _TEXT_SUFFIXES


def _config_int(name: str) -> int:
    if has_app_context():  # type: ignore[no-untyped-call]
        return int(current_app.config[name])
    return _DEFAULT_LIMITS[name]


def _allow_fixture_repos() -> bool:
    if has_app_context():  # type: ignore[no-untyped-call]
        return bool(current_app.config.get('LEARNING_ALLOW_FIXTURE_REPOS', False))
    return True


def _build_analysis(repo_ref: RepositoryRef, files: list[AnalyzedFile]) -> tuple[JSONDict, JSONDict]:
    file_map = {file.path: file for file in files}
    languages = _detect_languages(files)
    frameworks = _detect_frameworks(files)

    flows = _build_execution_flows(file_map)
    graph = build_execution_graph(flows)

    learner_flows = [
        {
            'id': flow['id'],
            'title': flow['title'],
            'trigger': flow['trigger'],
            'prompt': flow['prompt'],
            'steps': sorted(flow['steps'], key=lambda step: step['path']),
        }
        for flow in flows
    ]

    learner_payload = {
        'repository': {
            'owner': repo_ref.owner,
            'repo': repo_ref.repo,
            'url': repo_ref.url,
            'defaultBranch': repo_ref.default_branch,
        },
        'summary': {
            'languages': languages,
            'frameworks': frameworks,
            'fileCount': len(files),
            'flowCount': len(flows),
        },
        'graph': graph,
        'flows': learner_flows,
        'flowsAvailable': bool(flows),
    }

    answer_keys = {
        'flows': {
            flow['id']: {
                'orderedStepIds': [step['id'] for step in flow['steps']],
                'stepLookup': {
                    step['id']: {
                        'id': step['id'],
                        'label': step['label'],
                        'path': step['path'],
                        'kind': step['kind'],
                    }
                    for step in flow['steps']
                },
            }
            for flow in flows
        }
    }
    return learner_payload, answer_keys


def _detect_languages(files: list[AnalyzedFile]) -> list[str]:
    counts: dict[str, int] = {}
    for file in files:
        language = _LANGUAGE_MAP.get(PurePosixPath(file.path).suffix)
        if language is None:
            continue
        counts[language] = counts.get(language, 0) + 1
    return [language for language, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:4]]


def _detect_frameworks(files: list[AnalyzedFile]) -> list[JSONDict]:
    file_map = {file.path: file.content for file in files}
    package_json = file_map.get('frontend/package.json') or file_map.get('package.json', '')
    pyproject = file_map.get('pyproject.toml', '') + file_map.get('setup.py', '')
    joined = '\n'.join(file.content for file in files[:60])
    lowered = (pyproject + package_json).lower()
    detected_ids: set[str] = set()

    if 'flask' in lowered or 'render_template' in joined or 'Flask(' in joined:
        detected_ids.add('framework:flask')
    if 'fastapi' in lowered or 'FastAPI(' in joined:
        detected_ids.add('framework:fastapi')
    if 'django' in lowered or 'django.' in joined:
        detected_ids.add('framework:django')
    if '"react"' in package_json.lower() or "from 'react'" in joined:
        detected_ids.add('framework:react')
    if '"express"' in package_json.lower() or "require('express')" in joined:
        detected_ids.add('framework:express')
    if any(file.path.endswith('vite.config.ts') for file in files):
        detected_ids.add('framework:vite')
    if 'pytest' in lowered or any(file.path.startswith('tests/') for file in files):
        detected_ids.add('framework:pytest')
    if 'vitest' in package_json.lower():
        detected_ids.add('framework:vitest')
    if any(file.path.endswith('playwright.config.ts') for file in files):
        detected_ids.add('framework:playwright')

    return [
        {'id': framework_id, 'label': label}
        for label, framework_id in _FRAMEWORK_CANDIDATES
        if framework_id in detected_ids
    ]


def _node(path: str, kind: str) -> JSONDict:
    return {
        'id': f'file:{path}',
        'label': PurePosixPath(path).name,
        'path': path,
        'kind': kind,
    }


def _build_execution_flows(file_map: dict[str, AnalyzedFile]) -> list[JSONDict]:
    """Detect execution flows, preferring framework request flows then imports."""
    flows: list[JSONDict] = []
    seen_step_sets: list[frozenset[str]] = []

    for flow in _build_request_flows(file_map):
        flows.append(flow)
        seen_step_sets.append(frozenset(step['id'] for step in flow['steps']))
        if len(flows) >= _MAX_FLOWS:
            return flows

    graph = _build_module_graph(file_map)
    longest_chain: list[str] = []
    for entry in _entry_candidates(file_map, graph):
        if len(flows) >= _MAX_FLOWS:
            break
        chain = _chain_from(entry, graph, _MAX_CHAIN_DEPTH)
        if len(chain) > len(longest_chain):
            longest_chain = chain
        if len(chain) < 3:
            continue
        step_ids = frozenset(f'file:{path}' for path in chain)
        if any(_too_similar(step_ids, prev) for prev in seen_step_sets):
            continue
        flows.append(_import_chain_flow(chain))
        seen_step_sets.append(step_ids)

    if not flows and len(longest_chain) >= 2:
        flows.append(_import_chain_flow(longest_chain))
    return flows


def _too_similar(step_ids: frozenset[str], other: frozenset[str]) -> bool:
    """True when two flows share most of their steps (Jaccard > 0.6)."""
    union = step_ids | other
    if not union:
        return True
    return len(step_ids & other) / len(union) > 0.6


def _build_request_flows(file_map: dict[str, AnalyzedFile]) -> list[JSONDict]:
    main_file = file_map.get('frontend/src/main.ts')
    island_registry = _detect_island_registry(main_file)
    template_islands = _detect_template_islands(file_map)

    flows: list[JSONDict] = []
    for file in file_map.values():
        if not file.path.endswith('.py'):
            continue
        routes = _ROUTE_RE.findall(file.content)
        templates = _RENDER_TEMPLATE_RE.findall(file.content)
        if not routes or not templates:
            continue
        flow = _build_request_flow(
            route_path=routes[0],
            view_path=file.path,
            template_name=templates[0],
            file_map=file_map,
            template_islands=template_islands,
            island_registry=island_registry,
        )
        if flow is not None:
            flows.append(flow)
        if len(flows) >= _MAX_FLOWS:
            break
    return flows


def _detect_template_islands(file_map: dict[str, AnalyzedFile]) -> dict[str, list[str]]:
    template_islands: dict[str, list[str]] = {}
    for file in file_map.values():
        if not file.path.endswith('.html'):
            continue
        names = _DATA_ISLAND_RE.findall(file.content)
        if names:
            template_islands[file.path] = names
    return template_islands


def _detect_island_registry(main_file: AnalyzedFile | None) -> dict[str, str]:
    if main_file is None:
        return {}
    registry: dict[str, str] = {}
    for match in _ISLAND_REGISTRY_RE.finditer(main_file.content):
        registry[match.group('name')] = _resolve_frontend_module(match.group('path'))
    return registry


def _resolve_frontend_module(import_path: str) -> str:
    prefix = 'frontend/src/'
    relative = import_path.removeprefix('./')
    if relative.startswith('islands/'):
        return f'{prefix}{relative}/index.tsx'
    return f'{prefix}{relative}.ts'


def _build_request_flow(
    route_path: str,
    view_path: str,
    template_name: str,
    file_map: dict[str, AnalyzedFile],
    template_islands: dict[str, list[str]],
    island_registry: dict[str, str],
) -> JSONDict | None:
    template_path = f'src/app/templates/{template_name}'
    if template_path not in file_map:
        return None

    steps: list[JSONDict] = [_node(view_path, 'route'), _node(template_path, 'template')]
    edges: list[JSONDict] = [{
        'sourceId': f'file:{view_path}',
        'targetId': f'file:{template_path}',
        'label': 'renders',
    }]

    island_names = template_islands.get(template_path, [])
    main_path = 'frontend/src/main.ts'
    if island_names and main_path in file_map:
        steps.append(_node(main_path, 'frontend-entry'))
        edges.append({
            'sourceId': f'file:{template_path}',
            'targetId': f'file:{main_path}',
            'label': f'data-island="{island_names[0]}"',
        })
        module_path = island_registry.get(island_names[0])
        if module_path is not None and module_path in file_map:
            steps.append(_node(module_path, 'component'))
            edges.append({
                'sourceId': f'file:{main_path}',
                'targetId': f'file:{module_path}',
                'label': 'mounts island',
            })

    return {
        'id': f'flow:request:{route_path}',
        'title': f'Request to {route_path}',
        'trigger': f'HTTP GET {route_path}',
        'prompt': (
            f'A browser requests {route_path}. Click the files on the map in the '
            'order they execute, starting from the code that runs first.'
        ),
        'steps': steps,
        'edges': edges,
    }


def _build_module_graph(file_map: dict[str, AnalyzedFile]) -> dict[str, list[str]]:
    file_paths = set(file_map)
    python_modules = _python_module_map(file_paths)
    graph: dict[str, list[str]] = {}
    for path, file in file_map.items():
        suffix = PurePosixPath(path).suffix
        if suffix == '.py':
            targets = _python_import_targets(path, file.content, python_modules)
        elif suffix in _IMPORT_FILE_SUFFIXES:
            targets = _js_import_targets(path, file.content, file_paths)
        else:
            continue
        deduped: list[str] = []
        for target in targets:
            if target != path and target not in deduped:
                deduped.append(target)
        graph[path] = deduped
    return graph


def _python_module_map(file_paths: set[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for path in file_paths:
        if not path.endswith('.py'):
            continue
        parts = path[:-3].split('/')
        if parts[-1] == '__init__':
            parts = parts[:-1]
        if not parts:
            continue
        dotted = '.'.join(parts)
        mapping.setdefault(dotted, path)
        for root in ('src', 'lib'):
            if dotted.startswith(f'{root}.'):
                mapping.setdefault(dotted[len(root) + 1:], path)
    return mapping


def _python_import_targets(
    path: str, content: str, python_modules: dict[str, str]
) -> list[str]:
    targets: list[str] = []
    base_parts = path[:-3].split('/')[:-1]

    for match in _PY_FROM_RE.finditer(content):
        module = match.group('mod')
        names = [
            name.strip().split(' as ')[0].strip()
            for name in match.group('names').replace('(', '').replace(')', '').split(',')
            if name.strip() and name.strip() != '*'
        ]
        targets.extend(_resolve_py_from(base_parts, module, names, python_modules))

    for match in _PY_IMPORT_RE.finditer(content):
        for module in match.group('mods').split(','):
            module = module.strip().split(' as ')[0].strip()
            resolved = _resolve_python_dotted(module, python_modules)
            if resolved is not None:
                targets.append(resolved)
    return targets


def _resolve_py_from(
    base_parts: list[str], module: str, names: list[str], python_modules: dict[str, str]
) -> list[str]:
    level = len(module) - len(module.lstrip('.'))
    suffix = module.lstrip('.')

    if level > 0:
        ascended = base_parts[: len(base_parts) - (level - 1)] if level > 1 else base_parts
        base_dotted = '.'.join(part for part in ascended if part)
        target_base = f'{base_dotted}.{suffix}' if suffix else base_dotted
    else:
        target_base = suffix

    if not target_base:
        return []

    resolved: list[str] = []
    direct = _resolve_python_dotted(target_base, python_modules)
    if direct is not None:
        resolved.append(direct)
    for name in names:
        submodule = _resolve_python_dotted(f'{target_base}.{name}', python_modules)
        if submodule is not None:
            resolved.append(submodule)
    return resolved


def _resolve_python_dotted(dotted: str, python_modules: dict[str, str]) -> str | None:
    parts = [part for part in dotted.split('.') if part]
    while parts:
        candidate = '.'.join(parts)
        if candidate in python_modules:
            return python_modules[candidate]
        parts = parts[:-1]
    return None


def _js_import_targets(path: str, content: str, file_paths: set[str]) -> list[str]:
    base_path = PurePosixPath(path).parent
    targets: list[str] = []
    for match in _JS_IMPORT_RE.finditer(content):
        resolved = (base_path / match.group('path')).as_posix()
        for candidate in _import_candidates(resolved):
            if candidate in file_paths and candidate != path:
                targets.append(candidate)
                break
    return targets


def _import_candidates(resolved: str) -> list[str]:
    candidates = [resolved] if PurePosixPath(resolved).suffix else []
    for suffix in _IMPORT_FILE_SUFFIXES:
        candidates.append(f'{resolved}{suffix}')
        candidates.append(f'{resolved}/index{suffix}')
    return candidates


def _entry_candidates(
    file_map: dict[str, AnalyzedFile], graph: dict[str, list[str]]
) -> list[str]:
    scored: list[tuple[int, int, str]] = []
    for path, file in file_map.items():
        suffix = PurePosixPath(path).suffix
        if suffix not in _CODE_SUFFIXES or _is_excluded_entry(path):
            continue
        name = PurePosixPath(path).name
        content = file.content
        score = 0
        if suffix == '.py':
            if name in _PY_ENTRY_NAMES:
                score += 3
            if "__name__ == '__main__'" in content or '__name__ == "__main__"' in content:
                score += 4
            if 'Flask(' in content or 'FastAPI(' in content or 'create_app' in content:
                score += 3
            if _ROUTE_RE.search(content) or '@router' in content or '@app.' in content:
                score += 2
        else:
            if name in _JS_ENTRY_NAMES:
                score += 3
            if 'createServer' in content or 'app.listen(' in content:
                score += 2
        if graph.get(path):
            score += 1
        if score <= 0:
            continue
        scored.append((score, -path.count('/'), path))

    scored.sort(reverse=True)
    return [path for _, _, path in scored]


def _is_excluded_entry(path: str) -> bool:
    parts = PurePosixPath(path).parts
    if any(part in _EXCLUDED_ENTRY_DIRS for part in parts):
        return True
    name = parts[-1]
    return (
        name.startswith('test_')
        or name.endswith('_test.py')
        or '.test.' in name
        or '.spec.' in name
        or name.startswith('conftest')
    )


def _chain_from(entry: str, graph: dict[str, list[str]], max_depth: int) -> list[str]:
    chain = [entry]
    visited = {entry}
    current = entry
    for _ in range(max_depth):
        candidates = [target for target in graph.get(current, []) if target not in visited]
        if not candidates:
            break
        nxt = next(
            (
                target
                for target in candidates
                if any(child not in visited for child in graph.get(target, []))
            ),
            candidates[0],
        )
        chain.append(nxt)
        visited.add(nxt)
        current = nxt
    return chain


def _import_chain_flow(chain: list[str]) -> JSONDict:
    steps: list[JSONDict] = []
    edges: list[JSONDict] = []
    for index, path in enumerate(chain):
        steps.append(_node(path, 'entry' if index == 0 else 'module'))
        if index > 0:
            edges.append({
                'sourceId': f'file:{chain[index - 1]}',
                'targetId': f'file:{path}',
                'label': 'imports',
            })

    entry = chain[0]
    entry_name = PurePosixPath(entry).name
    return {
        'id': f'flow:imports:{entry}',
        'title': f'Load order from {entry_name}',
        'trigger': f'Module load: {entry}',
        'prompt': (
            f'{entry} is an entry module. Click the files on the map in the order '
            'they are loaded, following each import from the entry outward.'
        ),
        'steps': steps,
        'edges': edges,
    }
