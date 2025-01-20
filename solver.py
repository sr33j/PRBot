#!/usr/bin/env python3

import sys
import time
from github import Github

def fork_and_create_pr(
    upstream_repo_name: str,
    issue_number: int,
    github_token: str,
    branch_prefix: str = "issue-fix",
    base_branch: str = "main"
):
    """
    1. Fork the upstream repo if not already forked.
    2. Create a branch on the fork.
    3. Commit changes.
    4. Open a PR on the upstream repo referencing the fork's branch.
    """

    # Authenticate to GitHub
    g = Github(github_token)

    # Get user (to find or create the fork)
    user = g.get_user()
    
    # Get the "upstream" repository object (the repository you do NOT own)
    try:
        upstream_repo = g.get_repo(upstream_repo_name)
    except Exception as e:
        print(f"Error: Could not access upstream repository '{upstream_repo_name}'.\n{e}")
        sys.exit(1)

    # Check if user already has a fork of this repo
    fork_full_name = f"{user.login}/{upstream_repo.name}"  # e.g., "YourUsername/RepoName"
    try:
        fork_repo = g.get_repo(fork_full_name)
        print(f"Found existing fork: {fork_full_name}")
    except Exception:
        print(f"No existing fork found for {fork_full_name}. Creating a new fork...")
        fork_repo = upstream_repo.create_fork()
        # Some forks take time to be created (especially large repos). We can wait a bit.
        time.sleep(3)  # waiting a few seconds; adjust or add retry logic if needed
        # Re-fetch the fork
        fork_repo = g.get_repo(fork_full_name)
        print(f"Fork created: {fork_full_name}")

    # Ensure the fork has the base branch reference
    try:
        base_ref = fork_repo.get_git_ref(f"heads/{base_branch}")
        print(f"Found base branch '{base_branch}' on fork.")
    except Exception as e:
        # If the fork's default branch wasn't updated or isn't named `main`, 
        # you can handle that or use the upstream default branch name
        print(f"Could not find base branch '{base_branch}' on fork. Attempting to create it from upstream...")
        # Create a ref on fork from the upstream main branch's SHA
        upstream_base_ref = upstream_repo.get_git_ref(f"heads/{base_branch}")
        fork_repo.create_git_ref(ref=f"refs/heads/{base_branch}", sha=upstream_base_ref.object.sha)
        base_ref = fork_repo.get_git_ref(f"heads/{base_branch}")
        print(f"Created branch '{base_branch}' on fork from upstream's '{base_branch}'.")

    # Create the new branch name
    new_branch_name = f"{branch_prefix}-{issue_number}"
    new_branch_ref = f"refs/heads/{new_branch_name}"

    # Create new branch from base_branch on the fork
    try:
        fork_repo.create_git_ref(ref=new_branch_ref, sha=base_ref.object.sha)
        print(f"Created branch '{new_branch_name}' on fork.")
    except Exception as e:
        print(f"Error: Could not create branch '{new_branch_name}' on fork.\n{e}")
        sys.exit(1)

    # Commit a small change to README.md on the new branch
    file_path = "README.md"
    commit_message = f"Fix issue #{issue_number}"
    new_content_text = (
        f"\n\n---\n\n"
        f"This PR addresses issue #{issue_number}\n\n"
        f"<<SOLVER:0x0543ae55a38fe8bb1041efb7f6135bb23e61d422>>"
    )

    try:
        file_contents = fork_repo.get_contents(file_path, ref=new_branch_name)
        # If README.md exists, update it
        updated_content = file_contents.decoded_content.decode("utf-8") + new_content_text
        fork_repo.update_file(
            file_contents.path,
            commit_message,
            updated_content,
            file_contents.sha,
            branch=new_branch_name
        )
        print(f"Updated existing '{file_path}' in branch '{new_branch_name}'")
    except Exception:
        # If README.md does not exist, create it
        fork_repo.create_file(
            file_path,
            commit_message,
            f"# README\n{new_content_text}",
            branch=new_branch_name
        )
        print(f"Created new '{file_path}' in branch '{new_branch_name}'")

    # Now create a pull request on the upstream repo
    pr_title = f"Fixes #{issue_number}"
    pr_body = (
        f"This PR fixes issue #{issue_number}.\n\n"
        f"<<SOLVER:0x0543ae55a38fe8bb1041efb7f6135bb23e61d422>>"
    )

    # head should be <your-fork-owner>:<branch-name>
    head_with_owner = f"{user.login}:{new_branch_name}"

    try:
        pr = upstream_repo.create_pull(
            title=pr_title,
            body=pr_body,
            head=head_with_owner,
            base=base_branch,
        )
        print(f"Pull Request created successfully: {pr.html_url}")
    except Exception as e:
        print("Error creating pull request in upstream repo.")
        print(str(e))
        sys.exit(1)


if __name__ == "__main__":
    """
    Usage:
        python fork_and_create_pr.py <upstream_repo_name> <issue_number> <github_token>

    Example:
        python fork_and_create_pr.py "octocat/Hello-World" 42 MY_GITHUB_TOKEN
    """
    if len(sys.argv) < 4:
        print("Usage: python fork_and_create_pr.py <upstream_repo_name> <issue_number> <github_token>")
        sys.exit(1)

    upstream_repo_name = sys.argv[1]  # e.g. "octocat/Hello-World"
    issue_number = int(sys.argv[2])
    github_token = sys.argv[3]

    fork_and_create_pr(upstream_repo_name, issue_number, github_token)
