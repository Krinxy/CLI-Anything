from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-slack",
    version="1.0.0",
    description="CLI harness for Slack - send messages, read channel history and post via webhooks from the command line",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    install_requires=[
        "click>=8.0.0",
        "prompt-toolkit>=3.0.0",
        "requests>=2.28.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-slack=cli_anything.slack.slack_cli:main",
        ],
    },
    package_data={
        "cli_anything.slack": ["skills/*.md"],
    },
    include_package_data=True,
    python_requires=">=3.10",
)
