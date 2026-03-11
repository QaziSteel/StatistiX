#!/usr/bin/env python
"""
Check which Python environment Streamlit is running in
and which packages are available
"""
import sys
import os

print("=" * 60)
print("Python Environment Check")
print("=" * 60)

print(f"\n📍 Python Executable: {sys.executable}")
print(f"📍 Python Version: {sys.version}")
print(f"📍 Virtual Environment: {sys.prefix}")
print(f"📍 Sys Path: {sys.path[:2]}")  # Show first 2 paths

print("\n" + "=" * 60)
print("Required Packages Check")
print("=" * 60)

packages = {
    'pmdarima': 'AutoARIMA',
    'prophet': 'Prophet forecasting',
    'statsmodels': 'Time series models',
    'streamlit': 'Streamlit app',
    'pandas': 'Data manipulation',
}

missing = []
for pkg, description in packages.items():
    try:
        __import__(pkg)
        print(f"✅ {pkg:20} - {description}")
    except ImportError:
        print(f"❌ {pkg:20} - {description}")
        missing.append(pkg)

if missing:
    print(f"\n⚠️  Missing packages: {', '.join(missing)}")
    print(f"\nFix: Run this in your terminal:")
    print(f"  python -m pip install {' '.join(missing)}")
else:
    print(f"\n✅ All required packages are installed!")
