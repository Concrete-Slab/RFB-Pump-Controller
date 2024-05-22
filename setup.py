import setuptools
import subprocess
import sys
from setuptools.command.install import install

def check_and_install_external_dependency(command, name, initialisation_command: list[str]|None = None, url:str|None = None):
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

def install_package(pkg_name: str, opts:list[str]|str|None = None):
    """Install a python package via pip command (with options e.g. -U)"""
    if not opts:
        opts = []
    if isinstance(opts,list):
        if len(opts)>0:
            opts = " ".join(opts)
        else:
            opts = ""
    if not isinstance(opts,str):
        raise ValueError("opts must be a string or list of strings")
    strarg = f"pip install {opts} -yes {pkg_name}"
    subprocess.check_call(strarg)

class DependencyInstallCommand(install):
    """Custom install command that checks for installation of git and git-lfs"""
    def run(self):
        check_and_install_external_dependency("git","git",url="https://git-scm.com/downloads")
        check_and_install_external_dependency("git-lfs","git-LFS",initialisation_command=["git-lfs","install"],url="https://git-lfs.com/")
        # install albumentations without opencv-python-headless
        install_package("albumentations",opts="-U")
        # proceed with installation as normal
        install.run(self)

def get_install_requires():
    """Get the list of required packages, excluding albumentations and opencv-python-headless"""
    from pkg_resources import parse_requirements
    with open("requirements.txt") as f:
        requires = [str(req.name) for req in parse_requirements(f) if req.name not in ("albumentations","opencv-python-headless")]
    return requires

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="rfb-controller",
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
    install_requires=get_install_requires(),
    cmdclass={
        'install': DependencyInstallCommand,
    },
    py_modules=["main"]
)