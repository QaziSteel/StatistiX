#!/usr/bin/env python
"""Test if required packages are installed"""

packages_to_test = ['pmdarima', 'prophet', 'statsmodels', 'pandas', 'numpy']

for package in packages_to_test:
    try:
        __import__(package)
        print(f"✅ {package} is installed")
    except ImportError as e:
        print(f"❌ {package} is NOT installed: {e}")
