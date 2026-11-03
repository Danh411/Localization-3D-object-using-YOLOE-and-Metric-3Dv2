import os
from glob import glob
from setuptools import setup
p = "room_sim"
setup(name=p, version="0.1.0", packages=[p],
      data_files=[("share/ament_index/resource_index/packages", ["resource/" + p]),
                  ("share/" + p, ["package.xml"]),
                  (f"share/{p}/worlds", glob("worlds/*.sdf")),
                  (f"share/{p}/launch", glob("launch/*.py")),
                  (f"share/{p}/config", glob("config/*.yaml"))],
      install_requires=["setuptools"], zip_safe=True,
      entry_points={"console_scripts": ["pan_tf_node = room_sim.pan_tf_node:main"]})
