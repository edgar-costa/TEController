#!/usr/bin/env python

"Setuptools params"

from setuptools import setup, find_packages

VERSION = '0.1a'

modname = distname = 'tecontroller'

setup(
    name=distname,
    version=VERSION,
    description='The set of scripts to run a traffic engineering crontroller that uses fibbing',
    author='Ferran Llamas',
    author_email='lferran@student.ethz.ch',
    packages=find_packages(),
    include_package_data = True,
    classifiers=[
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python",
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "Topic :: System :: Networking",
        ],
    keywords='networking OSPF fibbing loadbalancer',
    license='BSD',
    install_requires=[
        'setuptools',
        'mako',
        'networkx',
        'py2-ipaddress'
    ],
    extras_require={
        'draw': ['matplotlib']
    }
)
