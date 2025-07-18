from pathlib import Path

from setuptools import setup, find_packages


def remove_comment(item: str) -> str:
    if "#" in item:
        item = item[0:item.find("#")]
    return item


def clean_requirements(req_list: list[str]) -> list[str]:
    result = [remove_comment(item).strip() for item in req_list]
    return list(filter(lambda item: len(item) > 0, result))


readme = Path("README.md").read_text()
requirements = clean_requirements(Path("requirements.txt").read_text().split("\n"))
dev_requirements = clean_requirements(Path("dev-requirements.txt").read_text().split("\n"))

setup(name="c2corg_api",
      version="0.0",
      description="c2corg_api",
      long_description=readme,
      classifiers=[
          "Programming Language :: Python",
          "Framework :: Pyramid",
          "Topic :: Internet :: WWW/HTTP",
          "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
      ],
      author="",
      author_email="",
      url="",
      keywords="web wsgi bfg pylons pyramid",
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      test_suite="c2corg_api",
      install_requires=requirements,
      extras_require={"dev": dev_requirements},
      entry_points="""\
      [paste.app_factory]
      main = c2corg_api:main
      [console_scripts]
      initialize_c2corg_api_db = c2corg_api.scripts.initializedb:main
      initialize_c2corg_api_es = c2corg_api.scripts.initializees:main
      fill_es_index = c2corg_api.scripts.es.fill_index:main
      """,
      )
