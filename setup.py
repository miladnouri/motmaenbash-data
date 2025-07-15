#!/usr/bin/env python3
"""
Setup script for MotmaenBash Data Repository Security Tools
Installs and configures data optimization and API management tools

@version 2.0.0
@author محمدحسین نوروزی (Mohammad Hossein Norouzi)
"""

from setuptools import setup, find_packages
import os
import sys

# Read version from file
def get_version():
    version_file = os.path.join(os.path.dirname(__file__), 'VERSION')
    if os.path.exists(version_file):
        with open(version_file, 'r') as f:
            return f.read().strip()
    return '2.0.0'

# Read long description from README
def get_long_description():
    readme_file = os.path.join(os.path.dirname(__file__), 'README.md')
    if os.path.exists(readme_file):
        with open(readme_file, 'r', encoding='utf-8') as f:
            return f.read()
    return ''

# Read requirements
def get_requirements():
    requirements_file = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    if os.path.exists(requirements_file):
        with open(requirements_file, 'r') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    return []

# Check Python version
if sys.version_info < (3, 8):
    print("Error: Python 3.8 or higher is required")
    sys.exit(1)

setup(
    name='motmaenbash-data-tools',
    version=get_version(),
    description='Security tools for MotmaenBash data repository management',
    long_description=get_long_description(),
    long_description_content_type='text/markdown',
    author='محمدحسین نوروزی (Mohammad Hossein Norouzi)',
    author_email='hosein.norozi434@gmail.com',
    url='https://github.com/MohammadHNdev/motmaenbash-data-secure',
    project_urls={
        'Bug Reports': 'https://github.com/MohammadHNdev/motmaenbash-data-secure/issues',
        'Source': 'https://github.com/MohammadHNdev/motmaenbash-data-secure',
        'Documentation': 'https://motmaenbash.ir/docs',
    },
    
    packages=find_packages(),
    py_modules=[
        'validate_data',
        'data_optimizer',
        'api_manager'
    ],
    
    install_requires=get_requirements(),
    
    extras_require={
        'dev': [
            'pytest>=6.2.0',
            'pytest-asyncio>=0.18.0',
            'pytest-cov>=3.0.0',
            'black>=22.0.0',
            'flake8>=4.0.0',
            'mypy>=0.910',
            'isort>=5.10.0',
        ],
        'monitoring': [
            'prometheus-client>=0.12.0',
            'opencensus>=0.8.0',
            'structlog>=21.5.0',
        ],
        'performance': [
            'cachetools>=4.2.0',
            'memory-profiler>=0.60.0',
            'psutil>=5.8.0',
            'lz4>=4.0.0',
            'zstandard>=0.17.0',
        ]
    },
    
    entry_points={
        'console_scripts': [
            'motmaenbash-validate=validate_data:main',
            'motmaenbash-optimize=data_optimizer:main',
            'motmaenbash-api-manager=api_manager:main',
        ],
    },
    
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: Security',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: System :: Monitoring',
        'Topic :: System :: Systems Administration',
    ],
    
    keywords='security phishing api optimization rate-limiting motmaenbash',
    
    python_requires='>=3.8',
    
    include_package_data=True,
    
    package_data={
        '': ['*.json', '*.yaml', '*.yml', '*.md', '*.txt', '*.cfg'],
    },
    
    zip_safe=False,
    
    platforms=['any'],
    
    # Security-related metadata
    license='MIT',
    
    # Additional metadata
    maintainer='محمدحسین نوروزی (Mohammad Hossein Norouzi)',
    maintainer_email='hosein.norozi434@gmail.com',
    
    # Custom commands
    cmdclass={},
    
    # Test configuration
    test_suite='tests',
    tests_require=[
        'pytest>=6.2.0',
        'pytest-asyncio>=0.18.0',
        'pytest-cov>=3.0.0',
        'pytest-mock>=3.6.0',
    ],
)