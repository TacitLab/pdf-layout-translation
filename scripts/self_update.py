#!/usr/bin/env python3
"""Check GitHub for a newer version of this skill and sync from it.

Default mode is a read-only check. With --apply, the local skill directory is
hard-reset to the remote branch: remote content always wins over local changes.
Untracked files (for example local work/output directories) are left untouched.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_REPO = "git@github.com:TacitLab/pdf-layout-translation.git"
DEFAULT_BRANCH = "main"

SKILL_ROOT = Path(__file__).resolve().parent.parent


def run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=SKILL_ROOT,
        capture_output=True,
        text=True,
        check=check,
    )


def git_output(args: list[str]) -> str:
    return run_git(args).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Sync local files from the remote (remote wins)")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="Git remote URL of the skill repository")
    parser.add_argument("--branch", default=DEFAULT_BRANCH, help="Branch to track")
    args = parser.parse_args()

    if not shutil.which("git"):
        print(json.dumps({"status": "error", "detail": "git is not installed"}, indent=2))
        return 2

    is_repo = (SKILL_ROOT / ".git").is_dir()
    linked = False
    if not is_repo:
        run_git(["init", "-b", args.branch])
        run_git(["remote", "add", "origin", args.repo])
        linked = True
    else:
        remotes = git_output(["remote"])
        if "origin" not in remotes.split():
            run_git(["remote", "add", "origin", args.repo])
            linked = True
        else:
            current_url = git_output(["remote", "get-url", "origin"])
            if current_url != args.repo:
                run_git(["remote", "set-url", "origin", args.repo])
                linked = True

    fetch = run_git(["fetch", "origin", args.branch], check=False)
    if fetch.returncode != 0:
        print(json.dumps({
            "status": "error",
            "detail": "failed to fetch from remote; check network and repository access",
            "stderr": fetch.stderr.strip(),
        }, indent=2))
        return 2

    remote_ref = f"origin/{args.branch}"
    remote_head = git_output(["rev-parse", remote_ref])
    local_head_proc = run_git(["rev-parse", "HEAD"], check=False)
    local_head = local_head_proc.stdout.strip() if local_head_proc.returncode == 0 else None

    if local_head == remote_head:
        status, detail = "up-to-date", "local skill already matches the remote"
    elif not local_head:
        status, detail = "not-linked", "no local commit yet; apply to adopt the remote version"
    else:
        base_proc = run_git(["merge-base", "HEAD", remote_ref], check=False)
        base = base_proc.stdout.strip() if base_proc.returncode == 0 else ""
        behind = base == local_head
        status = "update-available" if behind else "diverged"
        detail = (
            "remote has newer commits"
            if behind
            else "local history differs from remote; apply will overwrite local changes with the remote version"
        )

    report = {
        "status": status,
        "detail": detail,
        "repo": args.repo,
        "branch": args.branch,
        "skill_root": str(SKILL_ROOT),
        "local_head": local_head,
        "remote_head": remote_head,
        "linked_repository": linked,
    }

    if not args.apply or status == "up-to-date":
        if not args.apply and status != "up-to-date":
            report["next_step"] = "re-run with --apply after the user approves overwriting local changes with the remote version"
        print(json.dumps(report, indent=2))
        return 0 if status == "up-to-date" else 1

    reset = run_git(["reset", "--hard", remote_ref], check=False)
    if reset.returncode != 0:
        report["status"] = "error"
        report["detail"] = "git reset failed"
        report["stderr"] = reset.stderr.strip()
        print(json.dumps(report, indent=2))
        return reset.returncode

    report["status"] = "updated"
    report["detail"] = "local files now match the remote; untracked local files were left untouched"
    report["local_head"] = remote_head
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
