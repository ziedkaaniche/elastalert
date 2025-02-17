# -*- coding: utf-8 -*-
import os

from setuptools import find_packages
from setuptools import setup


base_dir = os.path.dirname(__file__)
setup(
    name='elastalert',
    version='1.0.0',
    description='Runs custom filters on Elasticsearch and alerts on matches',
    author='Zied KAANICHE',
    author_email='zied.kaaniche@digitus.tech',
    setup_requires='setuptools',
    license='Copyright 2019',
    classifiers=[
        'Programming Language :: Python :: 3.6',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
    ],
    entry_points={
        'console_scripts': ['elastalert-create-index=elastalert.create_index:main',
                            'elastalert-test-rule=elastalert.test_rule:main',
                            'elastalert-rule-from-kibana=elastalert.rule_from_kibana:main',
                            'elastalert=elastalert.elastalert:main']},
    packages=find_packages(),
    package_data={'elastalert': ['schema.yaml', 'es_mappings/**/*.json']},
    install_requires=[
        'apscheduler>=3.3.0',
        'aws-requests-auth>=0.3.0',
        'blist>=1.3.6',
        'boto3>=1.4.4',
        'configparser>=3.5.0',
        'croniter>=0.3.16',
        'elasticsearch>=7.0.0',
        'envparse>=0.2.0',
        'exotel>=0.1.3',
        'jsonschema>=2.6.0,<3.0.0',
        'mock>=2.0.0',
        'PyStaticConfiguration>=0.10.3',
        'python-dateutil>=2.6.0,<2.7.0',
        'PyYAML>=3.12',
        'requests>=2.10.0',
        'stomp.py>=4.1.17',
        'texttable>=0.8.8',
        'twilio>=6.0.0,<6.1',
        'thehive4py>=1.4.4',
        'python-magic>=0.4.15',
        'cffi>=1.11.5'
        'python-dateutil>=2.5.0'
    ]
)
