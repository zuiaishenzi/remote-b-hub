"""Create release checksum metadata for the two tested desktop binaries."""
import hashlib
import json
import os
from pathlib import Path
import re


def write_manifest(directory, tag, source_commit):
    if not re.fullmatch(r'desktop-\d+-\d+', tag) or not re.fullmatch('[0-9a-f]{40}', source_commit):
        raise ValueError('Invalid release identity')
    directory = Path(directory)
    assets = {}
    for name in ('RemoteBClient.exe', 'RemoteBHub.exe'):
        data = (directory / name).read_bytes()
        if data[:2] != b'MZ' or len(data) < 1000:
            raise ValueError('Missing/invalid tested EXE: ' + name)
        assets[name] = {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    result = {'schema': 1, 'repository': 'zuiaishenzi/remote-b-hub', 'tag': tag,
              'source_commit': source_commit, 'assets': assets}
    (directory / 'update-manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    tag = 'desktop-' + os.environ['GITHUB_RUN_NUMBER'] + '-' + os.environ['GITHUB_RUN_ATTEMPT']
    write_manifest('dist', tag, os.environ['GITHUB_SHA'])
