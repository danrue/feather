#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Always prefer setuptools over distutils
from setuptools import setup, find_packages

with open('README.md') as readme_file:
    readme = readme_file.read()

setup(
    name='tarsnap-feather',

    version='v1.2.0',

    description=('Feather is a tarsnap backup scheduler that performs ',
                 'and maintains a set of backups as defined by a yaml ',
                 'configuration file.'),
    long_description=readme,
    url='https://github.com/danrue/feather',
    author='Dan Rue',
    author_email='drue@therub.org',
    license='Beerware',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: System Administrators',
        'Topic :: System :: Archiving :: Backup',
        'License :: Beerware',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],

    keywords='tarsnap backups',
    packages=['feather'],
    package_dir={'feather': 'feather'},
    include_package_data=True,
    install_requires=['pyyaml', 'future'],
    package_data={
        'tarsnap-feather': ['examples/feather.yaml.dist',
                            'examples/feather.cron.d.example'],
    },

    entry_points={
        'console_scripts': [
            'tarsnap-feather=feather.feather:main',
        ],
    },
)
