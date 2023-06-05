import setuptools
import adless

with open("readme.md", "r") as fh:
    long_description = fh.read()

with open("requirements.txt", "r") as fh:
    install_requires = fh.read().splitlines()

setuptools.setup(
    name='adless',
    version=adless.__version__,
    scripts=[],
    author="Benny Clams",
    author_email="benny@bennycla.ms",
    description="A library downloading youtube videos and playlists.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/bennyclams/untube",
    packages=setuptools.find_packages(),
    install_requires=install_requires,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
    ],
)
