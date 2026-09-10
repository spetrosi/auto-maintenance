#!/usr/bin/python3
"""Remove old versions of a collection from Ansible Galaxy.

Keeps the newest N versions (by semantic version) and deletes the rest using
the Galaxy v3 REST API. Authentication uses a Galaxy API token.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from packaging.version import InvalidVersion, Version

DEFAULT_SERVER = "https://galaxy.ansible.com"
LIST_PATH = (
    "/api/v3/plugin/ansible/content/published/collections/index/"
    "{namespace}/{name}/versions/"
)


def api_request(url, token, method="GET"):
    """Perform an authenticated request against the Galaxy API."""
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", "Token " + token)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode("utf-8")
        return resp.status, body


def list_versions(server, token, namespace, name):
    """Return a list of all version strings for the collection."""
    versions = []
    path = LIST_PATH.format(namespace=namespace, name=name) + "?limit=100&offset=0"
    while path:
        _, body = api_request(server + path, token)
        data = json.loads(body)
        versions.extend(item["version"] for item in data["data"])
        path = data.get("links", {}).get("next")
    return versions


def sort_versions(versions):
    """Sort version strings newest-first, tolerating non-PEP440 versions."""

    def key(ver):
        try:
            return (1, Version(ver))
        except InvalidVersion:
            return (0, Version("0"))

    # Non-parseable versions sort last (oldest) so they are pruned first.
    return sorted(versions, key=key, reverse=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default="fedora")
    parser.add_argument("--name", default="linux_system_roles")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument(
        "--keep",
        type=int,
        default=20,
        help="Number of newest versions to keep (default: 20)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GALAXY_API_KEY"),
        help="Galaxy API token (default: $GALAXY_API_KEY)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print which versions would be deleted",
    )
    args = parser.parse_args()

    if not args.token:
        sys.exit("No Galaxy token provided (use --token or $GALAXY_API_KEY)")

    versions = sort_versions(list_versions(args.server, args.token, args.namespace, args.name))
    print("Found %d versions of %s.%s" % (len(versions), args.namespace, args.name))

    to_delete = versions[args.keep :]
    if not to_delete:
        print("Nothing to delete - %d versions <= keep limit %d" % (len(versions), args.keep))
        return

    print("Keeping newest %d, deleting %d older versions" % (args.keep, len(to_delete)))
    base = args.server + LIST_PATH.format(namespace=args.namespace, name=args.name)
    for version in to_delete:
        url = base + version + "/"
        if args.dry_run:
            print("Would delete %s" % version)
            continue
        try:
            status, _ = api_request(url, args.token, method="DELETE")
            print("Deleted %s (status %s)" % (version, status))
        except urllib.error.HTTPError as err:
            print("Failed to delete %s: %s %s" % (version, err.code, err.reason))


if __name__ == "__main__":
    main()
