#!/usr/bin/env python3

import sys
import time
from github import Github
import os
import dotenv
from supabase import create_client
import re

dotenv.load_dotenv()

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
    3. Analyze issue and repository content.
    4. Make necessary changes to relevant files.
    5. Open a PR on the upstream repo with the changes.
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
        # sys.exit(1)
        return

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
        # sys.exit(1)
        return

    # Get the issue content to understand what needs to be fixed
    try:
        issue = upstream_repo.get_issue(issue_number)
        issue_title = issue.title
        issue_body = issue.body
        print(f"Analyzing issue #{issue_number}: {issue_title}")
    except Exception as e:
        print(f"Error: Could not fetch issue #{issue_number}.\n{e}")
        # sys.exit(1)
        return

    # Get repository contents to analyze
    try:
        contents = fork_repo.get_contents("")
        files_to_analyze = []
        while contents:
            file_content = contents.pop(0)
            if file_content.type == "dir":
                contents.extend(fork_repo.get_contents(file_content.path))
            else:
                files_to_analyze.append(file_content)
        print(f"Found {len(files_to_analyze)} files to analyze")
    except Exception as e:
        print(f"Error: Could not fetch repository contents.\n{e}")
        # sys.exit(1)
        return

    # TODO: Use embeddings to find relevant files based on issue description
    # This would involve creating embeddings for the issue description and file contents
    # and finding the most similar files that might need changes

    # For now, add hello to the README.md file if it exists
    # Otherwise, create a new README.md file with the word hello
    changes_needed = []
    for file in files_to_analyze:
        if file.path == "README.md":
            try:
                current_content = file.decoded_content.decode()
                new_content = current_content + "\nhello"
            except:
                new_content = "hello"
                
            changes_needed.append({
                'file': file,
                'new_content': new_content
            })

    # Create commits for each changed file
    for change in changes_needed:
        try:
            fork_repo.update_file(
                change['file'].path,
                f"Fix issue #{issue_number}",
                change['new_content'],
                change['file'].sha,
                branch=new_branch_name
            )
            print(f"Updated {change['file'].path}")
        except Exception as e:
            print(f"Error updating {change['file'].path}: {e}")
            continue

    # Create pull request with meaningful description
    pr_title = f"Fixes #{issue_number}: {issue_title}"
    pr_body = (
        f"This PR addresses issue #{issue_number}\n\n"
        f"## Changes Made\n"
        f"The following files were modified:\n"
        + "\n".join([f"- {change['file'].path}" for change in changes_needed])
        + f"\n\n## Original Issue\n{issue_body}\n\n"
        f"`<<SOLVER:0x0543ae55a38fe8bb1041efb7f6135bb23e61d422>>`"
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
        # sys.exit(1)
        return

def solve_bounty():
    """
    Monitors Supabase Issues table for new entries and creates PRs for new issues.
    Runs continuously with a 30-second delay between checks.
    """
    # Initialize Supabase client
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    supabase = create_client(supabase_url, supabase_key)

    # Create/load processed issues file
    processed_issues_file = "processed_issues.txt"
    if not os.path.exists(processed_issues_file):
        with open(processed_issues_file, "w") as f:
            f.write("")

    while True:
        # Load previously processed issues
        with open(processed_issues_file, "r") as f:
            processed_issues = set(f.read().splitlines())

        # Query for new issues
        response = supabase.table('Issues').select("*").execute()
        
        if not response.data:
            print("No issues found in the table")
        else:
            for issue in response.data:
                # Parse the issue link to extract repo name and issue number
                issue_link = issue.get('issue_link')
                if not issue_link:
                    continue

                # Skip if we've already processed this issue
                if issue_link in processed_issues:
                    continue

                # Extract repo name and issue number using regex
                match = re.match(r'https://github.com/([^/]+/[^/]+)/issues/(\d+)', issue_link)
                if not match:
                    print(f"Invalid issue link format: {issue_link}")
                    continue

                repo_name = match.group(1)  # owner/repo
                issue_number = int(match.group(2))
                github_token = os.getenv("GITHUB_TOKEN")

                print(f"Processing issue: {repo_name}#{issue_number}")
                
                try:
                    fork_and_create_pr(
                        repo_name,
                        issue_number,
                        github_token
                    )
                    # Add to processed issues after successful PR creation
                    with open(processed_issues_file, "a") as f:
                        f.write(f"{issue_link}\n")
                except Exception as e:
                    print(f"Error processing issue {issue_link}: {e}")

        print("Waiting 30 seconds before next check...")
        time.sleep(30)

if __name__ == "__main__":
    solve_bounty()

