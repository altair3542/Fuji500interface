from setuptools import setup, find_packages

setup(
    name="tuorg.senaite.instruments.fuji500",
    version="0.1.0",
    description="Interfaz de instrumento FUJI 500 para SENAITE (esqueleto)",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    packages=find_packages("src"),
    package_dir={"": "src"},
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "senaite.instruments",
    ],
    entry_points={
        "z3c.autoinclude.plugin": [
            "target = plone"
        ]
    },
    classifiers=["Programming Language :: Python :: 3"],
)
