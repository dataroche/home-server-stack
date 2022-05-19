from setuptools import find_packages, setup

setup(
    name='home_server',
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    install_requires=[
        'pydantic',
        'influxdb',
        'pandas',
        'pytelegraf',
        'python-dotenv'
    ],
)