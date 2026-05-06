from setuptools import setup, find_packages

setup(
    name="x402-financial",
    version="1.0.0",
    description="Python client for x402 Financial Data API — Singapore financial data with USDC payments",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Nebrilis",
    author_email="neb@skyhigh5067.com",
    url="https://github.com/nebmil569/x402-financial-data-api",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "requests>=2.28",
    ],
    extras_require={
        "coinbase": ["coinbase-mdp-sdk"],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Office/Business :: Financial",
    ],
    keywords="x402 coinbase usdc singapore finance cpf sgx tax salary",
)
