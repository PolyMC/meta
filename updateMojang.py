import json
import os
import zipfile

import requests
from cachecontrol import CacheControl
from cachecontrol.caches import FileCache

from meta.common import upstream_path, ensure_upstream_dir, static_path
from meta.common.http import download_binary_file
from meta.common.mojang import BASE_DIR, VERSION_MANIFEST_FILE, VERSIONS_DIR, ASSETS_DIR, STATIC_EXPERIMENTS_FILE
from meta.model.mojang import MojangIndexWrap, MojangIndex, ExperimentIndex, ExperimentIndexWrap

UPSTREAM_DIR = upstream_path()
STATIC_DIR = static_path()

ensure_upstream_dir(BASE_DIR)
ensure_upstream_dir(VERSIONS_DIR)
ensure_upstream_dir(ASSETS_DIR)

forever_cache = FileCache('caches/http_cache', forever=True)
sess = CacheControl(requests.Session(), forever_cache)


def fetch_zipped_version(path, url):
    zip_path = f"{path}.zip"
    download_binary_file(sess, zip_path, url)
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.filename.endswith(".json"):
                print(f"Found {info.filename} as version json")
                version_json = json.load(z.open(info))
                break

    assert version_json

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(version_json, f, sort_keys=True, indent=4)

    return version_json


def fetch_version(path, url):
    r = sess.get(url)
    r.raise_for_status()
    version_json = r.json()

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(version_json, f, sort_keys=True, indent=4)

    return version_json


def main():
    # get the remote version list
    r = sess.get('https://piston-meta.mojang.com/mc/game/version_manifest_v2.json')
    r.raise_for_status()

    remote_versions = MojangIndexWrap(MojangIndex(**r.json()))
    remote_ids = set(remote_versions.versions.keys())

    version_manifest_path = os.path.join(UPSTREAM_DIR, VERSION_MANIFEST_FILE)

    if os.path.exists(version_manifest_path):
        # get the local version list
        current_versions = MojangIndexWrap(MojangIndex.parse_file(version_manifest_path))
        local_ids = set(current_versions.versions.keys())

        # versions not present locally but present remotely are new
        pending_ids = remote_ids.difference(local_ids)

        for x in local_ids:
            remote_version = remote_versions.versions[x]
            local_version = current_versions.versions[x]
            if remote_version.time > local_version.time:
                pending_ids.add(x)
    else:
        pending_ids = remote_ids

    for x in pending_ids:
        version = remote_versions.versions[x]
        print("Updating " + version.id + " to timestamp " + version.release_time.strftime('%s'))
        fetch_version(os.path.join(UPSTREAM_DIR, VERSIONS_DIR, f"{x}.json"), version.url)

    # deal with experimental snapshots separately
    static_experiments_path = os.path.join(STATIC_DIR, STATIC_EXPERIMENTS_FILE)
    if os.path.exists(static_experiments_path):
        experiments = ExperimentIndexWrap(ExperimentIndex.parse_file(static_experiments_path))
        experiment_ids = set(experiments.versions.keys())

        for x in experiment_ids:
            version = experiments.versions[x]
            experiment_path = os.path.join(UPSTREAM_DIR, VERSIONS_DIR, f"{x}.json")

            print("Updating experiment " + version.id)
            if not os.path.isfile(experiment_path):
                fetch_zipped_version(experiment_path, version.url)
            else:
                print("Already have experiment " + version.id)

    remote_versions.index.write(version_manifest_path)


if __name__ == '__main__':
    main()
