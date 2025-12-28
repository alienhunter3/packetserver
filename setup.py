from setuptools import setup, find_packages

setup(
    name='packetserver',
    version='0.4.1',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "fastapi",
        "uvicorn[standard]",
        "jinja2",
        "argon2-cffi",
        "ZODB",
        "ZEO",
        'click',
        'pyham_pe',
        'msgpack',
        'pyham_ax25',
        'ZODB',
        'ZEO',
        'podman',
        'tabulate',
        'pydantic',
        'pydantic_settings'
    ],
    entry_points={
        'console_scripts': [
            'packcli = packetserver.client.cli:cli',
            'packcfg = packetserver.server.cli:config',
            "packetserver-http-users = packetserver.runners.http_user_manager:main",
            "packetserver-http-server = packetserver.runners.http_server:main",
        ],
    },
)