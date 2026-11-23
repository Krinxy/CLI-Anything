from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-x64dbg",
    version="1.0.0",
    description="CLI harness for x64dbg - drive the real headless debugger: breakpoints, stepping, registers and memory",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    install_requires=[
        "click>=8.0.0",
        "prompt-toolkit>=3.0.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-x64dbg=cli_anything.x64dbg.x64dbg_cli:main",
        ],
    },
    package_data={
        "cli_anything.x64dbg": ["skills/*.md"],
    },
    include_package_data=True,
    python_requires=">=3.10",
)
