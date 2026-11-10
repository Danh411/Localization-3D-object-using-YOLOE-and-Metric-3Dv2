from setuptools import find_packages, setup

package_name = "scan_controller"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="loc3d",
    maintainer_email="dev@example.com",
    description="RunScan action server (pan, settle, capture, forward to DB).",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "scan_controller_node = scan_controller.scan_controller_node:main",
        ],
    },
)
