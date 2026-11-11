"""Independent snapshot/diff policy and hidden-test result interpretation."""
import difflib
import hashlib
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

IGNORED_DIRS = {'.git', '__pycache__', '.pytest_cache', '.hypothesis', '.mypy_cache', '.ruff_cache'}


def source_files(root):
    result = {}
    root = Path(root)
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        if any(p in IGNORED_DIRS or p.endswith('.egg-info') for p in relative.parts):
            continue
        if path.is_symlink():
            result[str(relative)] = ('symlink', path.readlink().as_posix().encode())
        elif path.is_file():
            if path.stat().st_size > 10 * 1024**2:
                result[str(relative)] = ('oversize', b'')
            else:
                result[str(relative)] = ('file', path.read_bytes())
    return result


def compare_source(initial, candidate, output):
    before, after = source_files(initial), source_files(candidate)
    names = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
    forbidden, changes, diff = [], [], []
    for name in names:
        old, new = before.get(name), after.get(name)
        allowed = name.startswith('src/') and (new is None or new[0] == 'file')
        if not allowed:
            forbidden.append(name)
        changes.append(dict(path=name, allowed=allowed,
                            before_sha256=None if old is None else hashlib.sha256(old[1]).hexdigest(),
                            after_sha256=None if new is None else hashlib.sha256(new[1]).hexdigest()))
        if (old and old[0] != 'file') or (new and new[0] != 'file'):
            continue
        try:
            oldtext = old[1].decode() if old else ''
            newtext = new[1].decode() if new else ''
        except UnicodeDecodeError:
            forbidden.append(name)
            continue
        if (oldtext and not oldtext.endswith('\n')) or (newtext and not newtext.endswith('\n')):
            # Unified diff handles newline sentinels explicitly.
            pass
        diff.append(f'diff --git a/{name} b/{name}\n')
        lines = list(difflib.unified_diff(oldtext.splitlines(keepends=True), newtext.splitlines(keepends=True),
                                        fromfile='a/' + name if old else '/dev/null',
                                        tofile='b/' + name if new else '/dev/null'))
        for line in lines:
            diff.append(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n')
    patch = ''.join(diff)
    Path(output).write_text(patch)
    return dict(changes=changes, files=len(names), forbidden_paths=sorted(set(forbidden)),
                policy_passed=not forbidden, patch_sha256=hashlib.sha256(patch.encode()).hexdigest(),
                lines_added=sum(line.startswith('+') and not line.startswith('+++') for line in patch.splitlines()),
                lines_removed=sum(line.startswith('-') and not line.startswith('---') for line in patch.splitlines()))


def grading_workspace(initial, candidate, output):
    """Copy only production changes into a pristine tree; no candidate caches/tests."""
    output = Path(output)
    shutil.copytree(initial, output, symlinks=True)
    before, after = source_files(initial), source_files(candidate)
    for name in sorted(before.keys() | after.keys()):
        if not name.startswith('src/') or before.get(name) == after.get(name):
            continue
        target = output / name
        if name not in after:
            target.unlink(missing_ok=True)
        elif after[name][0] == 'file':
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(after[name][1])


def parse_junit(path):
    statuses = {}
    for case in ET.parse(path).getroot().iter('testcase'):
        file = case.get('file')
        classname, name = case.get('classname', ''), case.get('name', '')
        if file:
            prefix = file.removesuffix('.py').replace('/', '.')
            cls = classname.removeprefix(prefix).lstrip('.')
            node = file + ('::' + cls.replace('.', '::') if cls else '') + '::' + name
        else:
            # Without xunit1 file metadata the class/file boundary is ambiguous.
            raise ValueError('JUnit testcase file metadata unavailable')
        if case.find('error') is not None:
            status = 'ERROR'
        elif case.find('failure') is not None:
            status = 'FAILED'
        elif (skip := case.find('skipped')) is not None:
            status = 'XFAIL' if skip.get('type') == 'pytest.xfail' else 'SKIPPED'
        else:
            status = 'PASSED'
        statuses[node] = status
    return statuses


def resolve_status(case, statuses):
    if case in statuses:
        return statuses[case]
    # Historical SWE-bench lists can truncate parametrized ids at whitespace.
    values = [value for name, value in statuses.items() if name.split()[0] == case]
    if values and len(set(values)) == 1:
        return values[0]
    return None


def score(task, statuses):
    result = dict(test_statuses=statuses)
    for group, accepted in [('FAIL_TO_PASS', {'PASSED', 'XFAIL'}),
                            ('PASS_TO_PASS', {'PASSED', 'XFAIL', 'SKIPPED'})]:
        outcomes = [dict(test=case, status=resolve_status(case, statuses)) for case in task[group]]
        success = [v for v in outcomes if v['status'] in accepted]
        result[group] = dict(total=len(outcomes), passed=len(success),
                             missing=sum(v['status'] is None for v in outcomes),
                             outcomes=outcomes)
    result['official_subset_resolved'] = all(result[k]['passed'] == result[k]['total']
                                            for k in ('FAIL_TO_PASS', 'PASS_TO_PASS'))
    return result
