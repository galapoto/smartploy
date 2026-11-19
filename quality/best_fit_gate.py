#!/usr/bin/env python3
"""BEST-FIT-TECH-001 deterministic evidence and bootstrap gate (stdlib only)."""
import argparse
import json
import pathlib
import sys

POLICY = 'BEST-FIT-TECH-001'
AGENT_PATHS = ('AGENTS.md', 'CLAUDE.md', 'GEMINI.md',
               '.github/copilot-instructions.md', '.cursor/rules/best-fit-tech.mdc')
CHECKS = ('functional', 'security', 'recovery', 'visual', 'accessibility', 'performance')


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
    args = p.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    errors = check_repo(root)
    if args.evidence:
        errors.extend(check_evidence(root, args.evidence))
    elif not args.bootstrap_only:
        errors.append('EVIDENCE_REQUIRED: pass --evidence, or --bootstrap-only for repository adoption')
    print(json.dumps({'policy': POLICY, 'result': 'PASS' if not errors else 'FAIL',
                      'root': str(root), 'errors': errors}, sort_keys=True))
    return 0 if not errors else 1


if __name__ == '__main__':
    sys.exit(main())
