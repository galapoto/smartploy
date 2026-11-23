#!/usr/bin/env python3
"""BEST-FIT-TECH-001 deterministic evidence and bootstrap gate (stdlib only)."""
import argparse
import json
import pathlib
import subprocess
import sys

POLICY = 'BEST-FIT-TECH-001'
AGENT_PATHS = ('AGENTS.md', 'CLAUDE.md', 'GEMINI.md',
               '.github/copilot-instructions.md', '.cursor/rules/best-fit-tech.mdc')
CHECKS = ('functional', 'security', 'recovery', 'visual', 'accessibility', 'performance')

CODE_EXTENSIONS = frozenset((
    '.py', '.js', '.mjs', '.cjs', '.jsx', '.ts', '.tsx', '.html', '.css',
    '.go', '.rs', '.c', '.h', '.cpp', '.hpp', '.java', '.kt', '.swift',
    '.vue', '.svelte', '.sql', '.sh', '.tf', '.toml',
))
EXEMPT_PREFIXES = ('docs/', 'quality/', 'tests/', 'templates/',
                   '.github/', '.woodpecker/', '.cursor/', 'test/',
                   'scripts/bootstrap_best_fit.py')
EXEMPT_FILES = frozenset(('AGENTS.md', 'CLAUDE.md', 'GEMINI.md',
                          'README.md', 'LICENSE', '.gitignore'))
CODE_BASENAMES = frozenset(('Dockerfile', 'Containerfile', 'package.json',
                            'package-lock.json', 'go.mod', 'Cargo.toml'))


def is_product_code(value):
    """Exclude policy-only changes but detect actual product/runtime changes."""
    if not isinstance(value, str) or not value or value.startswith('/'):
        return False
    path = pathlib.PurePosixPath(value)
    if '..' in path.parts or value in EXEMPT_FILES:
        return False
    if any(value.startswith(prefix) for prefix in EXEMPT_PREFIXES):
        return False
    return path.suffix.lower() in CODE_EXTENSIONS or path.name in CODE_BASENAMES


def git_changed_files(root, base):
    """Compute full PR source difference; missing/untrusted merge base fails closed."""
    if not isinstance(base, str) or not base or base.startswith('-') or any(c.isspace() for c in base):
        raise ValueError('invalid git base ref')
    cmd = ['git', '-C', str(root), 'diff', '--name-only',
           '--diff-filter=ACMR', base + '...HEAD', '--']
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)
    if result.returncode != 0:
        raise ValueError('git base not available; fetch approved base before gate: ' + result.stderr.strip()[:250])
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def check_changed_components(root, changed, evidence_dir='quality/evidence'):
    """Require complete per-feature evidence for every changed application code path."""
    changes = sorted({path for path in changed if is_product_code(path)})
    if not changes:
        return []
    folder = root / evidence_dir
    if not folder.is_dir():
        return ['PRODUCT_CHANGE_WITHOUT_EVIDENCE_DIR: ' + ', '.join(changes)]
    declared = set()
    errors = []
    for item in sorted(folder.rglob('*.json')):
        rel = item.relative_to(root).as_posix()
        if item.is_symlink():
            errors.append('EVIDENCE_SYMLINK_FORBIDDEN: ' + rel)
            continue
        try:
            doc = json.loads(item.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            errors.append('INVALID_EVIDENCE_JSON: ' + rel + ': ' + str(exc))
            continue
        paths = doc.get('changed_files') if isinstance(doc, dict) else None
        if not isinstance(paths, list) or not paths:
            errors.append('MISSING_CHANGED_FILES: ' + rel)
            continue
        related = [path for path in paths if path in changes]
        if not related:
            continue
        errors.extend(rel + ': ' + problem for problem in check_evidence(root, rel))
        declared.update(related)
    missing = sorted(set(changes) - declared)
    if missing:
        errors.append('PRODUCT_FILES_WITHOUT_VERIFIED_EVIDENCE: ' + ', '.join(missing))
    return errors



def check_repo(root):
    errors = []
    for item in AGENT_PATHS:
        path = root / item
        if not path.is_file():
            errors.append(f'MISSING_AGENT_INSTRUCTIONS: {item}')
        elif POLICY not in path.read_text(encoding='utf-8'):
            errors.append(f'MISSING_POLICY_MARKER: {item}')
    return errors


def file_proof(root, value, key):
    if not isinstance(value, str) or not value.strip():
        return f'{key}: missing evidence path'
    relative = pathlib.PurePosixPath(value)
    if relative.is_absolute() or '..' in relative.parts or '\\' in value:
        return f'{key}: invalid path'
    candidate = (root / value).resolve()
    if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
        return f'{key}: evidence does not exist: {value}'
    if candidate.stat().st_size == 0:
        return f'{key}: evidence is empty: {value}'
    return None


def check_evidence(root, evidence_path):
    errors = []
    problem = file_proof(root, evidence_path, 'evidence')
    if problem:
        return [problem]
    try:
        data = json.loads((root / evidence_path).read_text(encoding='utf-8'))
    except (ValueError, OSError) as exc:
        return [f'evidence invalid JSON: {exc}']
    if not isinstance(data, dict):
        return ['evidence must be an object']
    for key in ('component', 'approved_spec', 'user_outcome', 'source_commit',
                'chosen_technology', 'selection_reason', 'reuse_disposition', 'agent_acknowledgement'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            errors.append(f'MISSING_FIELD: {key}')
    if data.get('policy') != POLICY:
        errors.append('WRONG_POLICY')
    options = data.get('alternatives_considered')
    if not isinstance(options, list) or not options or not all(isinstance(x, str) and x.strip() for x in options):
        errors.append('MISSING_ALTERNATIVES')
    if data.get('reuse_disposition') not in ('COPIED','PORTED','SANITIZED','ADAPTED','INTEGRATED','NEW'):
        errors.append('INVALID_REUSE_DISPOSITION')
    if data.get('reuse_disposition') != 'NEW':
        for key in ('donor_repository', 'donor_commit', 'donor_path', 'license'):
            if not isinstance(data.get(key), str) or not data[key].strip():
                errors.append(f'MISSING_PROVENANCE: {key}')
    elif not data.get('copied_none_reason'):
        errors.append('MISSING_COPIED_NONE_REASON')
    for category in ('skill', 'rea', 'toolchain'):
        record = data.get(category)
        if not isinstance(record, dict):
            errors.append(f'MISSING_SECTION: {category}')
            continue
        if record.get('status') not in ('APPLIED', 'NOT_APPLICABLE', 'BLOCKED'):
            errors.append(f'INVALID_STATUS: {category}')
            continue
        if record['status'] == 'APPLIED':
            problem = file_proof(root, record.get('proof'), f'{category}.proof')
            if problem: errors.append(problem)
            if not record.get('version'):
                errors.append(f'{category}: missing pinned version')
        elif not record.get('reason'):
            errors.append(f'{category}: exception requires reason')
        if record['status'] == 'BLOCKED':
            errors.append(f'{category}: unresolved blocker cannot pass release gate')
    checks = data.get('checks')
    if not isinstance(checks, dict):
        return errors + ['MISSING_SECTION: checks']
    is_ui = data.get('kind') == 'ui'
    if data.get('kind') not in ('ui', 'backend', 'infrastructure', 'document', 'other'):
        errors.append('INVALID_KIND')
    for check in CHECKS:
        record = checks.get(check)
        if not isinstance(record, dict) or record.get('status') not in ('PASS', 'NOT_APPLICABLE'):
            errors.append(f'MISSING_OR_FAILED_CHECK: {check}')
            continue
        if record['status'] == 'PASS':
            problem = file_proof(root, record.get('proof'), f'checks.{check}.proof')
            if problem: errors.append(problem)
        elif not record.get('reason') or (is_ui and check in ('visual','accessibility')):
            errors.append(f'INVALID_CHECK_EXCEPTION: {check}')
    return errors


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default='.')
    p.add_argument('--evidence', help='relative JSON evidence file for one component')
    p.add_argument('--bootstrap-only', action='store_true')
    p.add_argument('--git-base', help='full PR base ref for automatic source-change evidence verification')
    p.add_argument('--changed-file', action='append', default=[], help='additional explicit changed code path')
    args = p.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    errors = check_repo(root)
    if args.evidence:
        errors.extend(check_evidence(root, args.evidence))
    changed = list(args.changed_file)
    if args.git_base:
        try:
            changed.extend(git_changed_files(root, args.git_base))
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            errors.append('UNVERIFIED_GIT_BASE: ' + str(exc))
    if changed:
        errors.extend(check_changed_components(root, changed))
    if not args.evidence and not args.bootstrap_only and not args.git_base and not changed:
        errors.append('EVIDENCE_REQUIRED: pass --evidence, --git-base or --changed-file, or explicitly --bootstrap-only')
    print(json.dumps({'policy': POLICY, 'result': 'PASS' if not errors else 'FAIL',
                      'root': str(root), 'errors': errors}, sort_keys=True))
    return 0 if not errors else 1


if __name__ == '__main__':
    sys.exit(main())
