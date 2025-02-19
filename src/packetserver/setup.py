from setuptools import setup, find_packages

setup(
    name='packetserver',
    version='VERSION="0.4.0-alpha',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'click',
        'pyham_pe',
        'msgpack',
        'pyham_ax25',
        'ZODB',
        'ZEO',
        'podman',
        'tabulate'
    ],
    entry_points={
        'console_scripts': [
            'packcli = packetserver.client.cli:cli',
        ],
    },
)