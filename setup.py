import setuptools
import subprocess
import sys
from setuptools.command.install import install

def check_and_install_dependency(command, name, initialisation_command: list[str]|None = None, url:str|None = None):
    """Check for the presence of an executable on the system path by calling --version"""
    try:
        subprocess.check_call([command, '--version'])
        if initialisation_command:
            subprocess.check_call(initialisation_command)
    except subprocess.CalledProcessError:
        strout = f"{name} is not installed. Please install it manually."
        if url:
            strout = strout[:-1] + f" at {url}."
        print(strout)
        sys.exit(1)

class DependencyInstallCommand(install):
    """Custom install command that checks for installation of git and git-lfs"""
    def run(self):
        check_and_install_dependency("git","git")
        check_and_install_dependency("git-lfs","git-LFS")
        # proceed with installation as normal
        install.run(self)

def parse_requirements(filename):
    """Load requirements from requirements.txt"""
    with open(filename, 'r') as f:
        lines = f.readlines()
    requirements = []
    for line in lines:
        # Skip comments and empty lines
        if line.startswith('#') or not line.strip():
            continue
        # Add the requirement
        requirements.append(line.strip())
    return requirements

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="RFB-pump-controller",
    version="0.1.0",
    author="Thomas Williams",
    author_email="thomaswilliams3982@gmail.com",
    description="Control RFB diaphragm pumps from a GUI, with options for volume balancing and solvent refill",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Concrete-Slab/RFB-Pump-Controller",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.11',
    install_requires=parse_requirements("requirements.txt")
)