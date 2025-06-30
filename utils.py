import os
import subprocess
import re

def get_version_from_git():
    """
    Generates a version string based on git tags and commit count.
    It looks for the latest tag like 'v0', 'v1', etc.
    The version will be X.YY.ZZ where X is from the tag, and YY.ZZ is based on
    the number of commits since that tag.
    """
    git_dir = os.path.dirname(os.path.abspath(__file__))
    
    try:
        # Get the latest tag that looks like v<number>
        # --sort=-v:refname sorts tags in reverse version order (v1, v0)
        tags_str = subprocess.check_output(
            ['git', 'tag', '-l', 'v[0-9]*', '--sort=-v:refname'],
            stderr=subprocess.STDOUT, cwd=git_dir
        ).decode('utf-8').strip()
        
        latest_tag = tags_str.split('\n')[0] if tags_str else None

        if not latest_tag:
            # No version tag found, use total commit count from beginning
            major_version = 0
            commit_count = int(subprocess.check_output(
                ['git', 'rev-list', '--count', 'HEAD'],
                stderr=subprocess.STDOUT, cwd=git_dir
            ).strip().decode('utf-8'))
        else:
            major_version = int(re.search(r'v(\d+)', latest_tag).group(1))
            # Count commits since the latest version tag
            commit_count = int(subprocess.check_output(
                ['git', 'rev-list', '--count', f'{latest_tag}..HEAD'],
                stderr=subprocess.STDOUT, cwd=git_dir
            ).strip().decode('utf-8'))

        major_updates = (commit_count // 100) % 100
        minor_edits = commit_count % 100
        
        return f"Version - {major_version}.{major_updates:02d}.{minor_edits:02d}"

    except (subprocess.CalledProcessError, FileNotFoundError, ValueError, IndexError):
        # Fallback for no git, no tags, or other errors
        return "Version - N/A"

def get_version_string():
    return get_version_from_git()
