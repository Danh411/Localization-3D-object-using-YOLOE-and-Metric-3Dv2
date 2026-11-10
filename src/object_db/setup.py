from setuptools import find_packages, setup

package_name = "object_db"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name, ["object_db/schema.sql"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="loc3d",
    maintainer_email="dev@example.com",
    description="Object DB node + dedupe + approach point.",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "object_db_node = object_db.object_db_node:main",
        ],
    },
)
