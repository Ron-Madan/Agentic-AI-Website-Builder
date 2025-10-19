"""Git operations tool implementation using Git CLI."""

import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

from ..tools.interfaces import GitTool
from ..models.project import Repository


logger = logging.getLogger(__name__)


class GitCLITool(GitTool):
    """Git operations tool using Git CLI commands."""
    
    def __init__(self):
        self._verify_git_installation()
    
    def _verify_git_installation(self) -> None:
        """Verify that Git is installed and accessible."""
        try:
            result = subprocess.run(
                ["git", "--version"], 
                capture_output=True, 
                text=True, 
                check=True
            )
            logger.info(f"Git version: {result.stdout.strip()}")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise RuntimeError(f"Git is not installed or not accessible: {e}")
    
    async def _run_git_command(
        self, 
        command: List[str], 
        cwd: Optional[str] = None,
        check: bool = True
    ) -> subprocess.CompletedProcess:
        """Run a Git command asynchronously."""
        full_command = ["git"] + command
        logger.debug(f"Running Git command: {' '.join(full_command)} in {cwd or 'current directory'}")
        
        try:
            # Run the command in a subprocess
            process = await asyncio.create_subprocess_exec(
                *full_command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            result = subprocess.CompletedProcess(
                args=full_command,
                returncode=process.returncode,
                stdout=stdout.decode('utf-8'),
                stderr=stderr.decode('utf-8')
            )
            
            if check and result.returncode != 0:
                logger.error(f"Git command failed: {result.stderr}")
                raise subprocess.CalledProcessError(
                    result.returncode, 
                    full_command, 
                    result.stdout, 
                    result.stderr
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Error running Git command {' '.join(full_command)}: {e}")
            raise
    
    async def initialize_repository(self, project_path: str, remote_url: Optional[str] = None) -> Repository:
        """Initialize a new Git repository."""
        project_path = os.path.abspath(project_path)
        
        # Create directory if it doesn't exist
        Path(project_path).mkdir(parents=True, exist_ok=True)
        
        try:
            # Initialize Git repository
            await self._run_git_command(["init"], cwd=project_path)
            logger.info(f"Initialized Git repository in {project_path}")
            
            # Set up initial configuration
            await self._run_git_command(
                ["config", "user.name", "Agentic Web App Builder"], 
                cwd=project_path
            )
            await self._run_git_command(
                ["config", "user.email", "builder@agentic-webapp.dev"], 
                cwd=project_path
            )
            
            # Create initial branch (main)
            await self._run_git_command(["checkout", "-b", "main"], cwd=project_path)
            
            # Add remote if provided
            if remote_url:
                await self._run_git_command(
                    ["remote", "add", "origin", remote_url], 
                    cwd=project_path
                )
                logger.info(f"Added remote origin: {remote_url}")
            
            # Get current status
            status_result = await self._run_git_command(["status", "--porcelain"], cwd=project_path)
            status = "clean" if not status_result.stdout.strip() else "modified"
            
            # Get list of branches
            branches_result = await self._run_git_command(["branch"], cwd=project_path)
            branches = [
                branch.strip().replace("* ", "") 
                for branch in branches_result.stdout.split('\n') 
                if branch.strip()
            ]
            
            return Repository(
                path=project_path,
                remote_url=remote_url,
                current_branch="main",
                last_commit=None,
                status=status,
                branches=branches
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize repository: {e}")
            raise
    
    async def commit_changes(self, repository: Repository, message: str, files: List[str] = None) -> str:
        """Commit changes to the repository."""
        try:
            # Add files to staging area
            if files:
                for file in files:
                    await self._run_git_command(["add", file], cwd=repository.path)
            else:
                # Add all changes
                await self._run_git_command(["add", "."], cwd=repository.path)
            
            # Check if there are changes to commit
            status_result = await self._run_git_command(
                ["status", "--porcelain", "--cached"], 
                cwd=repository.path
            )
            
            if not status_result.stdout.strip():
                logger.info("No changes to commit")
                return repository.last_commit or ""
            
            # Commit changes
            commit_result = await self._run_git_command(
                ["commit", "-m", message], 
                cwd=repository.path
            )
            
            # Get the commit hash
            hash_result = await self._run_git_command(
                ["rev-parse", "HEAD"], 
                cwd=repository.path
            )
            commit_hash = hash_result.stdout.strip()
            
            # Update repository object
            repository.last_commit = commit_hash
            repository.status = "clean"
            
            logger.info(f"Committed changes with hash: {commit_hash}")
            return commit_hash
            
        except Exception as e:
            logger.error(f"Failed to commit changes: {e}")
            raise
    
    async def create_branch(self, repository: Repository, branch_name: str) -> str:
        """Create a new branch."""
        try:
            # Create and checkout new branch
            await self._run_git_command(
                ["checkout", "-b", branch_name], 
                cwd=repository.path
            )
            
            # Update repository object
            repository.current_branch = branch_name
            if branch_name not in repository.branches:
                repository.branches.append(branch_name)
            
            logger.info(f"Created and switched to branch: {branch_name}")
            return branch_name
            
        except Exception as e:
            logger.error(f"Failed to create branch {branch_name}: {e}")
            raise
    
    async def merge_branch(self, repository: Repository, source_branch: str, target_branch: str) -> bool:
        """Merge branches with conflict resolution."""
        try:
            # Switch to target branch
            await self._run_git_command(
                ["checkout", target_branch], 
                cwd=repository.path
            )
            
            # Attempt to merge
            try:
                merge_result = await self._run_git_command(
                    ["merge", source_branch], 
                    cwd=repository.path
                )
                
                # Update repository object
                repository.current_branch = target_branch
                
                logger.info(f"Successfully merged {source_branch} into {target_branch}")
                return True
                
            except subprocess.CalledProcessError as e:
                # Check if it's a merge conflict
                if "CONFLICT" in e.stderr or "CONFLICT" in e.stdout:
                    logger.warning(f"Merge conflict detected between {source_branch} and {target_branch}")
                    
                    # Get conflicted files
                    status_result = await self._run_git_command(
                        ["status", "--porcelain"], 
                        cwd=repository.path,
                        check=False
                    )
                    
                    conflicted_files = [
                        line.split()[1] for line in status_result.stdout.split('\n')
                        if line.startswith('UU') or line.startswith('AA')
                    ]
                    
                    if conflicted_files:
                        logger.error(f"Merge conflicts in files: {conflicted_files}")
                        # For now, abort the merge - in a real implementation,
                        # we might want to implement automatic conflict resolution
                        await self._run_git_command(["merge", "--abort"], cwd=repository.path)
                        return False
                
                raise
                
        except Exception as e:
            logger.error(f"Failed to merge branches: {e}")
            return False
    
    async def push_changes(self, repository: Repository, branch: str = "main") -> bool:
        """Push changes to remote repository."""
        if not repository.remote_url:
            logger.warning("No remote URL configured, cannot push changes")
            return False
        
        try:
            # Push to remote
            await self._run_git_command(
                ["push", "origin", branch], 
                cwd=repository.path
            )
            
            logger.info(f"Successfully pushed {branch} to remote")
            return True
            
        except subprocess.CalledProcessError as e:
            # Handle common push errors
            if "rejected" in e.stderr:
                logger.warning("Push rejected, attempting to pull and merge first")
                try:
                    # Pull latest changes
                    await self._run_git_command(
                        ["pull", "origin", branch], 
                        cwd=repository.path
                    )
                    
                    # Try pushing again
                    await self._run_git_command(
                        ["push", "origin", branch], 
                        cwd=repository.path
                    )
                    
                    logger.info(f"Successfully pushed {branch} after pull")
                    return True
                    
                except Exception as pull_error:
                    logger.error(f"Failed to pull and push: {pull_error}")
                    return False
            else:
                logger.error(f"Push failed: {e.stderr}")
                return False
        
        except Exception as e:
            logger.error(f"Failed to push changes: {e}")
            return False
    
    async def get_repository_status(self, repository: Repository) -> Dict[str, Any]:
        """Get detailed repository status."""
        try:
            # Get status
            status_result = await self._run_git_command(
                ["status", "--porcelain"], 
                cwd=repository.path
            )
            
            # Get current branch
            branch_result = await self._run_git_command(
                ["branch", "--show-current"], 
                cwd=repository.path
            )
            
            # Get last commit
            try:
                commit_result = await self._run_git_command(
                    ["rev-parse", "HEAD"], 
                    cwd=repository.path
                )
                last_commit = commit_result.stdout.strip()
            except subprocess.CalledProcessError:
                last_commit = None
            
            # Parse status
            modified_files = []
            untracked_files = []
            staged_files = []
            
            for line in status_result.stdout.split('\n'):
                if not line.strip():
                    continue
                
                status_code = line[:2]
                filename = line[3:]
                
                if status_code[0] in ['M', 'A', 'D', 'R', 'C']:
                    staged_files.append(filename)
                if status_code[1] in ['M', 'D']:
                    modified_files.append(filename)
                elif status_code == '??':
                    untracked_files.append(filename)
            
            # Update repository object
            repository.current_branch = branch_result.stdout.strip()
            repository.last_commit = last_commit
            repository.status = "clean" if not status_result.stdout.strip() else "modified"
            
            return {
                "current_branch": repository.current_branch,
                "last_commit": last_commit,
                "status": repository.status,
                "modified_files": modified_files,
                "untracked_files": untracked_files,
                "staged_files": staged_files
            }
            
        except Exception as e:
            logger.error(f"Failed to get repository status: {e}")
            raise
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """Validate Git operation parameters."""
        # Basic validation - specific commands may need additional validation
        return isinstance(parameters, dict)
    
    async def execute(self, command: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a Git command."""
        if command == "init":
            project_path = parameters.get("project_path", ".")
            remote_url = parameters.get("remote_url")
            result = await self.initialize_repository(project_path, remote_url)
            return {"repository": result.dict()}
        
        elif command == "commit":
            repository = Repository(**parameters.get("repository", {}))
            message = parameters.get("message", "Automated commit")
            files = parameters.get("files")
            commit_hash = await self.commit_changes(repository, message, files)
            return {"commit_hash": commit_hash}
        
        elif command == "create_branch":
            repository = Repository(**parameters.get("repository", {}))
            branch_name = parameters.get("branch_name")
            branch = await self.create_branch(repository, branch_name)
            return {"branch": branch}
        
        elif command == "merge":
            repository = Repository(**parameters.get("repository", {}))
            source_branch = parameters.get("source_branch")
            target_branch = parameters.get("target_branch")
            success = await self.merge_branch(repository, source_branch, target_branch)
            return {"merge_success": success}
        
        elif command == "push":
            repository = Repository(**parameters.get("repository", {}))
            branch = parameters.get("branch", "main")
            success = await self.push_changes(repository, branch)
            return {"push_success": success}
        
        elif command == "status":
            repository = Repository(**parameters.get("repository", {}))
            status = await self.get_repository_status(repository)
            return {"status": status}
        
        else:
            raise ValueError(f"Unknown Git command: {command}")