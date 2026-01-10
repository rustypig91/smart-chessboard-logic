import os
from setuptools import setup, find_packages

setup(
    name="chessboard",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        line.strip() for line in open("requirements.txt") if line.strip() and not line.startswith("#")
    ],
    python_requires=">=3.10",
    author="Christoffer Zakrisson",
    author_email="rustypig91@gmail.com",
    description="Chessboard API and Web Interface for my raspberry pi chessboard project not intended for public use",
    long_description=open("README.md").read(
    ) if os.path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    url="https://github.com/rustypig91/smart-chessboard-rpi-image",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: POSIX :: Linux",
        "License :: Free for non-commercial use",
        "Private :: Do Not Upload"
    ],
    include_package_data=True,
)
