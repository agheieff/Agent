import asyncio
import os
import logging
import sys
import re
from typing import Tuple, Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class PackageManager:
    """
    Provides functionality for managing software packages.
    Supports multiple package managers (pip, npm, apt, etc.)
    and provides a unified interface for installing and managing packages.
    """
    
    def __init__(self):
        self.pip_executable = self._find_pip_executable()
        self.npm_executable = self._find_executable("npm")
        self.apt_executable = self._find_executable("apt-get")
        self.yarn_executable = self._find_executable("yarn")
        self.pacman_executable = self._find_executable("pacman")
        
    def _find_pip_executable(self) -> str:
        """Find the appropriate pip executable for the current Python environment"""
        pip_candidates = [
            "pip",
            f"pip{sys.version_info.major}",
            f"pip{sys.version_info.major}.{sys.version_info.minor}",
            "python -m pip",
            f"python{sys.version_info.major} -m pip",
            f"python{sys.version_info.major}.{sys.version_info.minor} -m pip"
        ]
        
        for candidate in pip_candidates:
            try:
                cmd = f"{candidate} --version"
                result = os.system(f"{cmd} > /dev/null 2>&1")
                if result == 0:
                    return candidate
            except:
                pass
                
        # Default to basic pip if nothing else works
        return "pip"
        
    def _find_executable(self, name: str) -> Optional[str]:
        """Find a system executable by name"""
        try:
            cmd = f"command -v {name}"
            result = os.system(f"{cmd} > /dev/null 2>&1")
            if result == 0:
                return name
        except:
            pass
        return None
        
    async def install_python_package(self, package_name: str, version: Optional[str] = None, 
                                     upgrade: bool = False, requirements_file: Optional[str] = None) -> str:
        """
        Install a Python package using pip.
        
        Args:
            package_name: The name of the package to install
            version: Optional version specification
            upgrade: Whether to upgrade the package if already installed
            requirements_file: Path to a requirements.txt file
            
        Returns:
            Installation result message
        """
        try:
            cmd_parts = [self.pip_executable, "install"]
            
            if upgrade:
                cmd_parts.append("--upgrade")
                
            if requirements_file:
                cmd_parts.extend(["-r", requirements_file])
            elif package_name:
                if version:
                    cmd_parts.append(f"{package_name}=={version}")
                else:
                    cmd_parts.append(package_name)
            else:
                return "Error: No package name or requirements file specified"
                
            cmd = " ".join(cmd_parts)
            logger.info(f"Installing Python package with command: {cmd}")
            
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                return f"Successfully installed {package_name or requirements_file}"
            else:
                return f"Failed to install package. Error: {stderr.decode('utf-8', errors='replace')}"
                
        except Exception as e:
            logger.error(f"Error installing Python package: {e}")
            return f"Error installing package: {str(e)}"
            
    async def install_npm_package(self, package_name: str, version: Optional[str] = None,
                                  global_install: bool = False, upgrade: bool = False) -> str:
        """
        Install a Node.js package using npm.
        
        Args:
            package_name: The name of the package to install
            version: Optional version specification
            global_install: Whether to install the package globally
            upgrade: Whether to upgrade the package if already installed
            
        Returns:
            Installation result message
        """
        if not self.npm_executable:
            return "Error: npm is not installed or not found in PATH"
            
        try:
            cmd_parts = [self.npm_executable, "install"]
            
            if global_install:
                cmd_parts.append("-g")
                
            if upgrade:
                cmd_parts.append("--upgrade")
                
            if version:
                cmd_parts.append(f"{package_name}@{version}")
            else:
                cmd_parts.append(package_name)
                
            cmd = " ".join(cmd_parts)
            logger.info(f"Installing npm package with command: {cmd}")
            
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                return f"Successfully installed {package_name}"
            else:
                return f"Failed to install npm package. Error: {stderr.decode('utf-8', errors='replace')}"
                
        except Exception as e:
            logger.error(f"Error installing npm package: {e}")
            return f"Error installing npm package: {str(e)}"
            
    async def install_system_package(self, package_name: str) -> str:
        """
        Install a system package using apt-get on Ubuntu/Debian systems.
        
        Args:
            package_name: The name of the package to install
            
        Returns:
            Installation result message
        """
        if not self.apt_executable:
            return "Error: apt-get is not installed or not found in PATH"
            
        try:
            # First update package list
            update_cmd = f"{self.apt_executable} update"
            process = await asyncio.create_subprocess_shell(
                update_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            # Then install the package
            install_cmd = f"{self.apt_executable} install -y {package_name}"
            logger.info(f"Installing system package with command: {install_cmd}")
            
            process = await asyncio.create_subprocess_shell(
                install_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                return f"Successfully installed system package {package_name}"
            else:
                return f"Failed to install system package. Error: {stderr.decode('utf-8', errors='replace')}"
                
        except Exception as e:
            logger.error(f"Error installing system package: {e}")
            return f"Error installing system package: {str(e)}"
            
    async def install_pacman_package(self, package_name: str, noconfirm: bool = True, 
                                 refresh: bool = True, needed: bool = False) -> str:
        """
        Install a system package using pacman on Arch Linux and derivatives.
        
        Args:
            package_name: The name of the package to install
            noconfirm: Whether to skip confirmation prompts
            refresh: Whether to refresh package databases before installing
            needed: Whether to not reinstall already up-to-date packages
            
        Returns:
            Installation result message
        """
        if not self.pacman_executable:
            return "Error: pacman is not installed or not found in PATH"
            
        try:
            cmd_parts = [self.pacman_executable, "-S"]
            
            if noconfirm:
                cmd_parts.append("--noconfirm")
                
            if refresh:
                cmd_parts.append("--refresh")
                
            if needed:
                cmd_parts.append("--needed")
                
            cmd_parts.append(package_name)
            
            cmd = " ".join(cmd_parts)
            logger.info(f"Installing system package with pacman: {cmd}")
            
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                return f"Successfully installed package {package_name}"
            else:
                return f"Failed to install package. Error: {stderr.decode('utf-8', errors='replace')}"
                
        except Exception as e:
            logger.error(f"Error installing package with pacman: {e}")
            return f"Error installing package: {str(e)}"
    
    async def check_pacman_package(self, package_name: str) -> Dict[str, Any]:
        """
        Check if a package is installed and get its version using pacman.
        
        Args:
            package_name: The name of the package to check
            
        Returns:
            Dictionary with package information
        """
        if not self.pacman_executable:
            return {
                "installed": False,
                "name": package_name,
                "error": "Pacman is not installed or not found in PATH"
            }
            
        try:
            # Query for the package information
            cmd = f"{self.pacman_executable} -Qi {package_name}"
            
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                output = stdout.decode('utf-8', errors='replace')
                
                # Parse the output to extract package information
                info = {}
                for line in output.split('\n'):
                    if ':' in line:
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            key, value = parts
                            info[key.strip().lower()] = value.strip()
                
                # Parse dependencies if available
                dependencies = []
                if 'depends on' in info:
                    deps = info.get('depends on', '')
                    dependencies = [dep.strip() for dep in re.split(r'[,\s]+', deps) if dep.strip() and dep.strip() != 'None']
                
                return {
                    "installed": True,
                    "name": info.get("name", package_name),
                    "version": info.get("version", "Unknown"),
                    "description": info.get("description", ""),
                    "architecture": info.get("architecture", ""),
                    "url": info.get("url", ""),
                    "licenses": info.get("licenses", ""),
                    "groups": info.get("groups", ""),
                    "provides": info.get("provides", ""),
                    "dependencies": dependencies,
                    "install_date": info.get("install date", ""),
                    "install_reason": info.get("install reason", ""),
                    "install_script": info.get("install script", ""),
                    "size": info.get("installed size", "")
                }
            else:
                # Check if the package exists in repositories
                cmd = f"{self.pacman_executable} -Si {package_name}"
                process = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                if process.returncode == 0:
                    # Package exists in repos but not installed
                    return {
                        "installed": False,
                        "available": True,
                        "name": package_name
                    }
                else:
                    # Package not found
                    return {
                        "installed": False,
                        "available": False,
                        "name": package_name,
                        "error": stderr.decode('utf-8', errors='replace')
                    }
                    
        except Exception as e:
            logger.error(f"Error checking pacman package: {e}")
            return {
                "installed": False,
                "name": package_name,
                "error": str(e)
            }
    
    async def check_python_package(self, package_name: str) -> Dict[str, Any]:
        """
        Check if a Python package is installed and get its version.
        
        Args:
            package_name: The name of the package to check
            
        Returns:
            Dictionary with package information
        """
        try:
            cmd = f"{self.pip_executable} show {package_name}"
            
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                output = stdout.decode('utf-8', errors='replace')
                
                # Parse the output to extract package information
                info = {}
                for line in output.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        info[key.strip().lower()] = value.strip()
                        
                return {
                    "installed": True,
                    "name": info.get("name", package_name),
                    "version": info.get("version", "Unknown"),
                    "location": info.get("location", "Unknown"),
                    "requires": info.get("requires", "").split(', ') if info.get("requires") else []
                }
            else:
                return {
                    "installed": False,
                    "name": package_name,
                    "error": stderr.decode('utf-8', errors='replace')
                }
                
        except Exception as e:
            logger.error(f"Error checking Python package: {e}")
            return {
                "installed": False,
                "name": package_name,
                "error": str(e)
            }
