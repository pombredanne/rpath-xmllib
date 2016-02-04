#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
# Copyright (c) 2015 nexB Inc. http://www.nexb.com/ - All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import, print_function

from setuptools import find_packages
from setuptools import setup


setup(
    name='xmllib',
    version='1.3.0',
    license='Apache 2.0',
    description='An XML utility library',
    author='nexB Inc. (based on code from SAS Software Inc.)',
    author_email='info@nexb.com',
    url='https://github.com/pombredanne/xmllib',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    classifiers=[],
    install_requires=[
        'lxml',
    ]
)
