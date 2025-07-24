#!/usr/bin/env python3
"""
GitHub PR Branch Creator

This script takes a GitHub repository URL with a pull request and:
1. Checks if a copy exists in the JulianEgbertMasterThesis organization
2. Creates branches for the PR state and main branch state
"""

import re
import sys
import requests
import os
from typing import Tuple, Optional, Dict, Any


class GitHubPRBranchCreator:
    def __init__(self, github_token: Optional[str] = None):
        """Initialize with optional GitHub token for API access."""
        self.github_token = github_token or os.environ.get('GITHUB_TOKEN')
        if not self.github_token:
            raise ValueError("GitHub token is required. Set GITHUB_TOKEN environment variable.")

        self.target_org = 'JulianEgbertMasterThesis'
        self.headers = {
            'Authorization': f'token {self.github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }

    def _parse_pr_url(self, url: str) -> Tuple[str, str, int, Optional[str]]:
        """
        Parse GitHub PR URL to extract owner, repo, PR number, and optional commit SHA.
        Returns:
            Tuple of (owner, repo, pr_number, commit_sha)
        """
        # Pattern for PR URL with optional commit
        pattern = r'https://github\.com/([^/]+)/([^/]+)/pull/(\d+)(?:/commits/([a-f0-9]+))?'
        match = re.match(pattern, url.strip())

        if not match:
            raise ValueError(f"Invalid GitHub PR URL format: {url}")
        owner, repo, pr_number, commit_sha = match.groups()
        return owner, repo, int(pr_number), commit_sha

    def check_repo_exists(self, owner: str, repo: str) -> bool:
        target_repo_name = f"{owner}-{repo}"
        url = f"https://api.github.com/repos/{self.target_org}/{target_repo_name}"

        try:
            response = requests.get(url, headers=self.headers)
            return response.status_code == 200
        except requests.RequestException as e:
            print(f"Error checking repository existence: {e}")
            return False

    def _get_pr_info(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def _get_commit_repo_info(self, pr_info: Dict[str, Any], target_commit_sha: Optional[str] = None) -> Tuple[str, str, str]:
        """
        Determine which repository contains the target commit (original or fork).

        Args:
            pr_info: PR information from GitHub API
            target_commit_sha: Specific commit SHA to look for, if None uses PR head

        Returns:
            Tuple of (owner, repo, commit_sha) for the repository containing the commit
        """
        # Use the provided commit SHA or fall back to PR head
        commit_sha = target_commit_sha or pr_info['head']['sha']

        # Check if this is a fork-based PR
        head_repo = pr_info['head']['repo']
        base_repo = pr_info['base']['repo']

        if head_repo['full_name'] != base_repo['full_name']:
            # This is a fork-based PR, use the head repository
            print(f"📍 PR is from fork: {head_repo['full_name']} → {base_repo['full_name']}")
            return head_repo['owner']['login'], head_repo['name'], commit_sha
        else:
            # This is a same-repo PR, use the base repository
            print(f"📍 PR is within same repository: {base_repo['full_name']}")
            return base_repo['owner']['login'], base_repo['name'], commit_sha

    def _get_merge_parent_sha(self, owner: str, repo: str, merge_commit_sha: str) -> str:
        """
        Get the parent SHA of a merge commit (the state of main before the merge).
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/commits/{merge_commit_sha}"

        response = requests.get(url, headers=self.headers)
        response.raise_for_status()

        commit_data = response.json()
        parents = commit_data.get('parents', [])

        if not parents:
            raise ValueError(f"Merge commit {merge_commit_sha} has no parents")

        # First parent is typically the main branch state before merge
        return parents[0]['sha']

    def _create_repository(self, owner: str, repo: str) -> bool:
        """
        Create an empty repository in the target organization.
        """
        target_repo_name = f"{owner}-{repo}"
        return self._create_empty_repository(target_repo_name, f"Copy of {owner}/{repo}")

    def _create_empty_repository(self, repo_name: str, description: str) -> bool:
        """
        Create an empty repository in the target organization.

        Args:
            repo_name: Name of the repository to create
            description: Repository description

        Returns:
            True if successful, False otherwise
        """
        url = f"https://api.github.com/orgs/{self.target_org}/repos"

        data = {
            "name": repo_name,
            "description": description,
            "private": True,
            "has_issues": True,
            "has_projects": False,
            "has_wiki": False
        }

        try:
            response = requests.post(url, json=data, headers=self.headers)
            if response.status_code == 201:
                print(f"✓ Created empty repository '{repo_name}' successfully")
                return True
            else:
                print(f"✗ Failed to create repository '{repo_name}': {response.status_code}")
                print(f"Response: {response.text}")
                return False
        except requests.RequestException as e:
            print(f"✗ Error creating repository '{repo_name}': {e}")
            return False

    def _check_branch_exists(self, target_repo: str, branch_name: str) -> bool:
        """
        Check if a branch already exists in the target repository.

        Args:
            target_repo: Target repository name (owner-repo format)
            branch_name: Name of the branch to check

        Returns:
            True if branch exists, False otherwise
        """
        url = f"https://api.github.com/repos/{self.target_org}/{target_repo}/branches/{branch_name}"
        try:
            response = requests.get(url, headers=self.headers)
            return response.status_code == 200
        except requests.RequestException as e:
            print(f"Error checking branch existence: {e}")
            return False

    def _create_pull_request(self, target_repo: str, head_branch: str, base_branch: str, pr_info: Dict[str, Any]) -> bool:
        """
        Create a pull request in the target repository.

        Args:
            target_repo: Target repository name (owner-repo format)
            head_branch: Source branch for the PR (pr-{number})
            base_branch: Target branch for the PR (main-{number})
            pr_info: Original PR information

        Returns:
            True if successful, False otherwise
        """
        url = f"https://api.github.com/repos/{self.target_org}/{target_repo}/pulls"

        # Use original PR title and body
        title = pr_info.get('title', f'PR from {head_branch}')
        body = pr_info.get('body', '') or ''

        # Add metadata about the original PR
        original_pr_url = pr_info.get('html_url', '')
        metadata = f"\n\n---\n**Original PR:** `{original_pr_url}`"

        data = {
            "title": title,
            "body": body + metadata,
            "head": head_branch,
            "base": base_branch
        }

        try:
            print(f"📝 Creating PR: '{title[:50]}{'...' if len(title) > 50 else ''}'")
            print(f"   From: {head_branch} → To: {base_branch}")

            response = requests.post(url, json=data, headers=self.headers)

            if response.status_code == 201:
                pr_data = response.json()
                pr_url = pr_data.get('html_url', '')
                print(f"✅ Pull request created: {pr_url}")
                return True
            elif response.status_code == 422:
                error_data = response.json()
                if 'already exists' in error_data.get('message', '').lower():
                    print("ℹ Pull request already exists")
                    return True
                else:
                    print(f"✗ Failed to create pull request. Error message: {error_data.get('message', 'Unknown error')}")
                    print(f"Response: {response.text}")
                    return False
            else:
                print(f"✗ Failed to create pull request: {response.status_code}")
                print(f"Response: {response.text}")
                return False

        except requests.RequestException as e:
            print(f"✗ Error creating pull request: {e}")
            return False

    def _create_branch_from_base(self, owner: str, repo: str, target_repo: str, branch_name: str, commit_sha: str, base_branch: str) -> bool:
        """
        Create a branch based on an existing branch with content from a specific commit.
        This creates a proper Git history relationship for pull requests.
        """
        import subprocess
        import tempfile

        print(f"\n🌱 Creating branch '{branch_name}' from base '{base_branch}'...")
        print("=" * 50)

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                original_url = f"https://github.com/{owner}/{repo}.git"
                target_url = f"https://github.com/{self.target_org}/{target_repo}.git"
                auth_target_url = target_url.replace('https://', f'https://{self.github_token}@')

                # Clone the target repository
                print("📥 Cloning target repository...")
                clone_result = subprocess.run([
                    'git', 'clone', auth_target_url, 'target'
                ], cwd=temp_dir, capture_output=True, text=True)

                if clone_result.returncode != 0:
                    print(f"✗ Failed to clone target repository: {clone_result.stderr}")
                    return False
                print("✓ Successfully cloned target repository")

                target_dir = os.path.join(temp_dir, 'target')

                # Configure git user
                print("👤 Configuring Git user...")
                subprocess.run(['git', 'config', 'user.name', 'PR Branch Creator'], cwd=target_dir, capture_output=True)
                subprocess.run(['git', 'config', 'user.email', 'pr-branch-creator@example.com'], cwd=target_dir, capture_output=True)
                print("✓ Git user configured")

                # Checkout the base branch
                print(f"🔄 Checking out base branch '{base_branch}'...")
                checkout_result = subprocess.run([
                    'git', 'checkout', base_branch
                ], cwd=target_dir, capture_output=True, text=True)

                if checkout_result.returncode != 0:
                    print(f"✗ Failed to checkout base branch: {checkout_result.stderr}")
                    return False
                print(f"✓ Checked out base branch '{base_branch}'")

                # Create new branch from base
                print(f"🌿 Creating new branch '{branch_name}'...")
                branch_result = subprocess.run([
                    'git', 'checkout', '-b', branch_name
                ], cwd=target_dir, capture_output=True, text=True)

                if branch_result.returncode != 0:
                    print(f"✗ Failed to create branch: {branch_result.stderr}")
                    return False
                print(f"✓ Created branch '{branch_name}'")

                # Clone original repository to get commit content
                print(f"📥 Cloning original repository for commit content from '{original_url}'")
                original_clone_result = subprocess.run([
                    'git', 'clone', original_url, 'original'
                ], cwd=temp_dir, capture_output=True, text=True)

                if original_clone_result.returncode != 0:
                    print(f"✗ Failed to clone original repository: {original_clone_result.stderr}")
                    return False
                print("✓ Successfully cloned original repository")

                original_dir = os.path.join(temp_dir, 'original')

                # Get the commit content from the original repository
                print(f"📦 Extracting commit content from '{commit_sha}'")
                archive_result = subprocess.run([
                    'git', 'archive', '--format=tar', commit_sha
                ], cwd=original_dir, capture_output=True)

                if archive_result.returncode != 0:
                    print(f"✗ Failed to archive commit: {archive_result.stderr}")
                    return False
                print("✓ Successfully archived commit content.")

                # Clear current directory content (except .git)
                print("🧹 Clearing current branch content...")
                for item in os.listdir(target_dir):
                    if item != '.git':
                        item_path = os.path.join(target_dir, item)
                        if os.path.isdir(item_path):
                            import shutil
                            shutil.rmtree(item_path)
                        else:
                            os.remove(item_path)
                print("✓ Cleared current content")

                # Extract the archive to the target directory
                print("📂 Extracting new content...")
                extract_result = subprocess.run([
                    'tar', '-xf', '-'
                ], cwd=target_dir, input=archive_result.stdout, capture_output=True)

                if extract_result.returncode != 0:
                    print(f"✗ Failed to extract archive: {extract_result.stderr}")
                    return False
                print("✓ Successfully extracted new content")

                # Remove .github folder if it exists
                print("🧹 Checking for .github folder...")
                if os.path.exists(os.path.join(target_dir, '.github')):
                    import shutil
                    shutil.rmtree(os.path.join(target_dir, '.github'))
                    print("✓ Removed .github folder")
                else:
                    print("ℹ No .github folder found")

                # Add all changes
                print("➕ Adding changes to Git staging area...")
                add_result = subprocess.run([
                    'git', 'add', '-A'
                ], cwd=target_dir, capture_output=True, text=True)

                if add_result.returncode != 0:
                    print(f"✗ Failed to add changes: {add_result.stderr}")
                    return False
                print("✓ Changes added to staging area")

                commit_message = f"Commit {commit_sha}"
                print(f"✓ Retrieved commit message: {commit_message[:50]}{'...' if len(commit_message) > 50 else ''}")

                # Create the commit
                print("💾 Creating commit with PR changes...")
                commit_result = subprocess.run([
                    'git', 'commit', '-m', f"[PR Changes] {commit_message}"
                ], cwd=target_dir, capture_output=True, text=True)

                if commit_result.returncode != 0:
                    # Check if there are no changes to commit
                    if "nothing to commit" in commit_result.stdout:
                        print("ℹ No changes to commit - content is identical")
                        # Push the branch anyway to ensure it exists
                        print(f"🚀 Pushing branch '{branch_name}' to remote repository...")
                        push_result = subprocess.run([
                            'git', 'push', 'origin', branch_name
                        ], cwd=target_dir, capture_output=True, text=True)

                        if push_result.returncode != 0:
                            print(f"✗ Failed to push branch: {push_result.stderr}")
                            return False
                        print(f"✅ Successfully created branch '{branch_name}' (no content changes)")
                        return True
                    else:
                        print(f"✗ Failed to create commit: {commit_result.stderr}")
                        return False
                print("✓ Created commit successfully")

                # Push the branch
                print(f"🚀 Pushing branch '{branch_name}' to remote repository...")
                push_result = subprocess.run([
                    'git', 'push', 'origin', branch_name
                ], cwd=target_dir, capture_output=True, text=True)

                if push_result.returncode != 0:
                    print(f"✗ Failed to push branch: {push_result.stderr}")
                    return False

                print(f"✅ Successfully created branch '{branch_name}' from base '{base_branch}'")
                return True

        except Exception as e:
            print(f"✗ Error creating branch '{branch_name}': {e}")
            return False

    def _create_orphan_branch_with_commit(self, owner: str, repo: str, target_repo: str, branch_name: str, commit_sha: str) -> bool:
        """
        Create an orphan branch in the target repository with the content of a specific commit.
        """
        import subprocess
        import tempfile

        print(f"\n🌱 Creating orphan branch '{branch_name}'...")
        print("=" * 50)

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                original_url = f"https://github.com/{owner}/{repo}.git"
                target_url = f"https://github.com/{self.target_org}/{target_repo}.git"
                auth_target_url = target_url.replace('https://', f'https://{self.github_token}@')

                # Clone the original repository
                print(f"📥 Cloning original repository for commit {commit_sha[:8]}...")
                clone_result = subprocess.run([
                    'git', 'clone', original_url, 'source'
                ], cwd=temp_dir, capture_output=True, text=True)

                if clone_result.returncode != 0:
                    print(f"✗ Failed to clone repository: {clone_result.stderr}")
                    return False
                else:
                    print("✓ Successfully cloned original repository to temporary directory")

                source_dir = os.path.join(temp_dir, 'source')

                # Create a new repository for the orphan branch
                print("📁 Setting up work directory for orphan branch...")
                work_dir = os.path.join(temp_dir, 'work')
                os.makedirs(work_dir)

                # Initialize new git repository
                print("🔧 Initializing new Git repository...")
                init_result = subprocess.run([
                    'git', 'init'
                ], cwd=work_dir, capture_output=True, text=True)

                if init_result.returncode != 0:
                    print(f"✗ Failed to initialize work repository: {init_result.stderr}")
                    return False
                print("✓ Initialized new Git repository")

                # Configure git user (required for commits)
                print("👤 Configuring Git user...")
                subprocess.run(['git', 'config', 'user.name', 'PR Branch Creator'], cwd=work_dir, capture_output=True)
                subprocess.run(['git', 'config', 'user.email', 'pr-branch-creator@example.com'], cwd=work_dir, capture_output=True)
                print("✓ Git user configured")

                # Get the commit content from the original repository
                print(f"📦 Extracting commit content from {commit_sha[:8]}...")
                archive_result = subprocess.run([
                    'git', 'archive', '--format=tar', commit_sha
                ], cwd=source_dir, capture_output=True)

                if archive_result.returncode != 0:
                    print(f"✗ Failed to archive commit: {archive_result.stderr}")
                    return False
                print("✓ Successfully archived commit content")

                # Extract the archive to the work directory
                print("📂 Extracting files to work directory...")
                extract_result = subprocess.run([
                    'tar', '-xf', '-'
                ], cwd=work_dir, input=archive_result.stdout, capture_output=True)

                if extract_result.returncode != 0:
                    print(f"✗ Failed to extract archive: {extract_result.stderr}")
                    return False
                print("✓ Successfully extracted files")

                # Remove .github folder if it exists
                print("🧹 Checking for .github folder...")
                github_path = os.path.join(work_dir, '.github')
                if os.path.exists(github_path):
                    import shutil
                    shutil.rmtree(github_path)
                    print("✓ Removed .github folder")
                else:
                    print("ℹ No .github folder found")

                # Add all files and create orphan commit
                print("➕ Adding files to Git staging area...")
                add_result = subprocess.run([
                    'git', 'add', '.'
                ], cwd=work_dir, capture_output=True, text=True)

                if add_result.returncode != 0:
                    print(f"✗ Failed to add files: {add_result.stderr}")
                    return False
                print("✓ Files added to staging area")

                commit_message = f"Commit {commit_sha}"

                # Create the commit
                print("💾 Creating orphan commit...")
                commit_result = subprocess.run([
                    'git', 'commit', '-m', f"[Orphan] {commit_message}"
                ], cwd=work_dir, capture_output=True, text=True)

                if commit_result.returncode != 0:
                    print(f"✗ Failed to create commit: {commit_result.stderr}")
                    return False
                print("✓ Created orphan commit successfully")

                # Add remote and push the orphan branch
                print("🔗 Adding remote repository...")
                remote_result = subprocess.run([
                    'git', 'remote', 'add', 'origin', auth_target_url
                ], cwd=work_dir, capture_output=True, text=True)

                if remote_result.returncode != 0:
                    print(f"✗ Failed to add remote: {remote_result.stderr}")
                    return False
                print("✓ Remote repository added")

                # Push as the specified branch name
                print(f"🚀 Pushing orphan branch '{branch_name}' to remote repository...")
                push_result = subprocess.run([
                    'git', 'push', 'origin', f'HEAD:{branch_name}'
                ], cwd=work_dir, capture_output=True, text=True)

                if push_result.returncode != 0:
                    print(f"✗ Failed to push branch: {push_result.stderr}")
                    return False

                print(f"✅ Successfully created orphan branch '{branch_name}'")
                return True

        except Exception as e:
            print(f"✗ Error creating orphan branch '{branch_name}': {e}")
            return False

    def process_pr(self, pr_url: str) -> bool:
        """
        Main processing function to handle the PR and create branches.

        Args:
            pr_url: GitHub PR URL

        Returns:
            True if successful, False otherwise
        """
        try:
            print("🔍 Step 1: Parsing PR URL...")
            # Parse the PR URL
            owner, repo, pr_number, target_commit_sha = self._parse_pr_url(pr_url)
            if target_commit_sha:
                print(f"✓ Parsed URL: {owner}/{repo}/pull/{pr_number} at commit {target_commit_sha[:8]}")
            else:
                print(f"✓ Parsed URL: {owner}/{repo}/pull/{pr_number}")

            print("\n🏢 Step 2: Checking target repository...")
            # Check if target repository exists, create if it doesn't
            target_repo_name = f"{owner}-{repo}"
            print(f"Looking for repository: {self.target_org}/{target_repo_name}")

            if not self.check_repo_exists(owner, repo):
                print(f"❌ Target repository '{self.target_org}/{target_repo_name}' does not exist")
                print("🏗️ Creating new repository...")
                if not self._create_repository(owner, repo):
                    print(f"✗ Failed to create repository '{target_repo_name}'")
                    return False
                print(f"✅ Repository '{target_repo_name}' created successfully")
            else:
                print(f"✓ Target repository '{self.target_org}/{target_repo_name}' exists")

            print("\n📋 Step 3: Fetching PR information...")
            # Get PR information
            pr_info = self._get_pr_info(owner, repo, pr_number)

            pr_state = pr_info['state']
            pr_merged = pr_info.get('merged', False)
            base_branch = pr_info['base']['ref']

            print(f"✓ PR State: {pr_state}")
            print(f"✓ PR Merged: {pr_merged}")
            print(f"✓ Base Branch: {base_branch}")

            print("\n🔗 Step 4: Determining commit SHAs...")

            # Determine the correct repository and commit for PR content
            commit_owner, commit_repo, pr_sha = self._get_commit_repo_info(pr_info, target_commit_sha)
            if target_commit_sha:
                print(f"✓ Using specific commit SHA: {pr_sha}")
                print(f"✓ Commit repository: {commit_owner}/{commit_repo}")
            else:
                print(f"✓ Using PR head SHA: {pr_sha}")
                print(f"✓ Head repository: {commit_owner}/{commit_repo}")

            # Get the SHA for the base branch of the PR
            print("📍 Getting base branch SHA at the time of the PR...")
            # Use the base SHA from the PR - this is the state of the base branch when the PR was created
            main_sha = pr_info['base']['sha']
            print(f"✓ Base branch SHA at PR time: {main_sha}")

            # Create branches
            main_branch_name = f"{pr_info['base']['ref']}-{pr_number}"
            pr_branch_name = f"pr-{pr_number}"
            if target_commit_sha:
                # Include commit SHA in branch name for specific commits
                pr_branch_name += f"-{target_commit_sha[:8]}"

            print("\n🌿 Step 5: Checking and creating orphan branches...")
            print(f"Will check/create branches: '{main_branch_name}' and '{pr_branch_name}'")

            success = True

            # Check if main branch already exists
            print(f"\n🔍 Checking if branch '{main_branch_name}' exists...")
            if self._check_branch_exists(target_repo_name, main_branch_name):
                print(f"ℹ Branch '{main_branch_name}' already exists, skipping creation")
            else:
                print(f"📝 Branch '{main_branch_name}' does not exist, creating...")
                if not self._create_orphan_branch_with_commit(owner, repo, target_repo_name, main_branch_name, main_sha):
                    success = False
                    print(f"❌ Failed to create branch '{main_branch_name}'")
                else:
                    print(f"✅ Branch '{main_branch_name}' created successfully")

            # Check if PR branch already exists
            print(f"\n🔍 Checking if branch '{pr_branch_name}' exists...")
            if self._check_branch_exists(target_repo_name, pr_branch_name):
                print(f"ℹ Branch '{pr_branch_name}' already exists, skipping creation")
            else:
                print(f"📝 Branch '{pr_branch_name}' does not exist, creating...")
                # Use the commit repository info for PR branch creation
                if not self._create_branch_from_base(owner, repo, target_repo_name, pr_branch_name, pr_sha, main_branch_name):
                    success = False
                    print(f"❌ Failed to create branch '{pr_branch_name}'")
                else:
                    print(f"✅ Branch '{pr_branch_name}' created successfully")

            # Create PR from pr-{number} to main-{number}
            if success:
                print("\n🔀 Step 6: Creating pull request...")
                if not self._create_pull_request(target_repo_name, pr_branch_name, main_branch_name, pr_info):
                    print("⚠ Failed to create pull request, but branches were created successfully")
                else:
                    print("✅ Pull request created successfully")

            return success

        except ValueError as e:
            print(f"✗ URL parsing error: {e}")
            return False
        except requests.RequestException as e:
            print(f"✗ GitHub API error: {e}")
            return False
        except Exception as e:
            print(f"✗ Unexpected error: {e}")
            return False


def main():
    """Main function to run the script."""
    print("GitHub PR Branch Creator")
    print("=" * 40)

    # Check for GitHub token
    github_token = os.environ.get('GITHUB_TOKEN')
    if not github_token:
        print("⚠ Warning: No GITHUB_TOKEN environment variable found.")
        print("  Some operations may be rate-limited or fail.")
        print("  Set GITHUB_TOKEN environment variable for better results.")
        print()

    # Get PR URL from user
    pr_url = input("Enter GitHub PR URL (e.g., https://github.com/owner/repo/pull/1234 or https://github.com/owner/repo/pull/1234/commits/sha): ").strip()

    if not pr_url:
        print("✗ No URL provided. Exiting.")
        sys.exit(1)

    # Create processor and run
    processor = GitHubPRBranchCreator(github_token)

    print(f"\nProcessing PR: {pr_url}")
    print("-" * 40)

    success = processor.process_pr(pr_url)

    if success:
        print("\n✓ All operations completed successfully!")
    else:
        print("\n✗ Some operations failed. Check the output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
