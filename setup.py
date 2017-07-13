#!/usr/bin/env python

import os
import setuptools

from codecs import open

here = os.path.abspath(os.path.dirname(__file__))

about = {}
with open(os.path.join(here, 'pyrace', '__version__.py'), 'r', 'utf-8') as f:
    exec(f.read(), about)

setuptools.setup(
    name         = about['__title__'],
    description  = about['__description__'],
    url          = about['__url__'],
    version      = about['__version__'],
    author       = about['__author__'],
    author_email = about['__author_email__'],
    license      = about['__license__'],

    packages = ['pyrace'],

    install_requires = [
        'requests>=2.0',
        'six',
    ],

    extras_require = {
        'docs': ["sphinx_rtd_theme"],
    },

    classifiers = [
        'Development Status :: 4 - Beta',
        'Natural Language :: English',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Security',
    ],
)