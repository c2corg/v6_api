import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.md')) as f:
    README = f.read()

setup(name='c2corg_api',
      version='0.0',
      description='c2corg_api',
      long_description=README,
      classifiers=[
        "Programming Language :: Python",
        "Framework :: Pyramid",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
        ],
      author='',
      author_email='',
      url='',
      keywords='web wsgi bfg pylons pyramid',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      test_suite='c2corg_api',
      install_requires=[],
      entry_points="""\
      [paste.app_factory]
      main = c2corg_api:main
      [console_scripts]
      initialize_c2corg_api_db = c2corg_api.scripts.initializedb:main
      initialize_c2corg_api_es = c2corg_api.scripts.initializees:main
      fill_es_index = c2corg_api.scripts.es.fill_index:main
      """,
      )
