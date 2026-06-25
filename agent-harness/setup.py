from setuptools import find_namespace_packages, setup


setup(
    name="cli-anything-ugreen-nas",
    version="0.1.0",
    description="Agent-friendly CLI harness for UGREEN NAS file operations over WebDAV.",
    python_requires=">=3.11",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    entry_points={
        "console_scripts": [
            "ugnas=cli_anything.ugreen_nas._cli:main",
            "cli-anything-ugreen-nas=cli_anything.ugreen_nas._cli:main",
        ]
    },
)
