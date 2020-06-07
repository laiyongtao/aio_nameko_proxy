import os
from setuptools import setup, find_packages

DIR = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(DIR, "README.md")) as f:
    long_desc = f.read()

desc = '''A standalone nameko rpc proxy for asyncio and a wrapper for using nameko rpc proxy with Sanic. '''


setup(
    name="aio-nameko-proxy",
    version="1.1.0",
    author="laiyongtao",
    author_email="laiyongtao6908@163.com",
    url="https://github.com/laiyongtao/aio_nameko_proxy" ,
    license="Apache License, Version 2.0",
    description=desc,
    long_description=long_desc,
    long_description_content_type="text/markdown",
    platforms="all",
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
    keywords = ("nameko", "sanic", "asyncio", "rpc"),
    packages=find_packages(exclude=["demos"]),
    install_requires=[
        "aio-pika>=6.6.0",
        "aiotask-context>=0.6.1",
    ],
    python_requires=">3.5.*, <4",
)
