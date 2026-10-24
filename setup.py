from setuptools import setup, find_packages

with open('requirements.txt') as f:
    install_requires = [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name='finance_ai',
    version='1.0.0',
    description='FinGuard AI – AI-Powered Financial Anomaly Detection for ERPNext',
    author='FinGuard AI',
    author_email='admin@finguard.ai',
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
    python_requires='>=3.10',
)
